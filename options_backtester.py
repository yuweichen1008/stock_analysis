"""
Options screener strategy backtester.

Validates the RSI+PCR signal rules against existing WeeklySignal history.
WeeklySignal rows have: pcr, pcr_label, return_pct (the week's actual return).

RSI proxy: estimated from return_pct since raw RSI is not stored in WeeklySignal.
  rsi_proxy = clamp(50 + return_pct * 200, 0, 100)
  Negative weekly returns → lower RSI proxy (oversold proxy)
  Positive weekly returns → higher RSI proxy (overbought proxy)

Signal rules (mirroring options/signals.py):
  buy_signal:  rsi_proxy < 40 AND pcr > 1.0
  sell_signal: rsi_proxy > 60 AND pcr < 0.6

Win condition:
  buy_signal wins  when the *next* period's return is positive
  sell_signal wins when the *next* period's return is negative
  (Uses self-referential return_pct as a proxy for next-week outcome per ticker)

Usage:
    python options_backtester.py          → print table to console
    python options_backtester.py --json   → emit JSON to stdout
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def _rsi_proxy(return_pct: float) -> float:
    raw = 50.0 + return_pct * 200.0
    return max(0.0, min(100.0, raw))


def _sharpe(returns: list[float]) -> float | None:
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(variance) if variance > 0 else 0.0
    if std == 0:
        return None
    return round(mean / std * math.sqrt(52), 3)  # annualised (52 weekly periods)


def run_backtest() -> dict:
    from api.db import SessionLocal, WeeklySignal
    from sqlalchemy import asc

    db = SessionLocal()
    rows = (
        db.query(WeeklySignal)
        .filter(
            WeeklySignal.pcr.isnot(None),
            WeeklySignal.return_pct.isnot(None),
        )
        .order_by(WeeklySignal.ticker, asc(WeeklySignal.week_ending))
        .all()
    )
    db.close()

    # Group by ticker so we can look up next-week return
    by_ticker: dict[str, list] = defaultdict(list)
    for r in rows:
        by_ticker[r.ticker].append(r)

    stats: dict[str, list[float]] = {
        "buy_signal":  [],
        "sell_signal": [],
    }

    for ticker, ticker_rows in by_ticker.items():
        for i, r in enumerate(ticker_rows[:-1]):   # skip last (no next-week outcome)
            next_return = ticker_rows[i + 1].return_pct
            rsi_p  = _rsi_proxy(r.return_pct)
            pcr    = r.pcr

            if rsi_p < 40 and pcr > 1.0:
                # buy_signal: win if next week is positive
                stats["buy_signal"].append(next_return)
            elif rsi_p > 60 and pcr < 0.6:
                # sell_signal: win if next week is negative (negate so positive = win)
                stats["sell_signal"].append(-next_return)

    results: dict[str, dict] = {}
    all_returns: list[float] = []

    for sig, returns in stats.items():
        if not returns:
            results[sig] = {"trades": 0}
            continue
        wins = [r for r in returns if r > 0]
        avg  = round(sum(returns) / len(returns) * 100, 2)
        results[sig] = {
            "trades":      len(returns),
            "wins":        len(wins),
            "losses":      len(returns) - len(wins),
            "win_rate_pct": round(len(wins) / len(returns) * 100, 1),
            "avg_return_pct": avg,
            "sharpe":      _sharpe(returns),
        }
        all_returns.extend(returns)

    combined_wins = [r for r in all_returns if r > 0]
    results["combined"] = {
        "trades":      len(all_returns),
        "wins":        len(combined_wins),
        "losses":      len(all_returns) - len(combined_wins),
        "win_rate_pct": round(len(combined_wins) / len(all_returns) * 100, 1) if all_returns else 0,
        "avg_return_pct": round(sum(all_returns) / len(all_returns) * 100, 2) if all_returns else 0,
        "sharpe":      _sharpe(all_returns),
    }

    return results


def _print_table(results: dict) -> None:
    print("\n=== Options Screener — RSI+PCR Strategy Backtest ===\n")
    header = f"{'Signal':<22} {'Trades':>7} {'Win Rate':>10} {'Avg Rtn':>9} {'Sharpe':>8}"
    print(header)
    print("-" * len(header))
    for sig, r in results.items():
        if r.get("trades", 0) == 0:
            print(f"{sig:<22} {'n/a':>7}")
            continue
        print(
            f"{sig:<22} {r['trades']:>7} {r['win_rate_pct']:>9.1f}%"
            f" {r['avg_return_pct']:>8.2f}%"
            f" {str(r['sharpe'] or 'n/a'):>8}"
        )
    print()


if __name__ == "__main__":
    results = run_backtest()
    if "--json" in sys.argv:
        print(json.dumps(results, indent=2))
    else:
        _print_table(results)
