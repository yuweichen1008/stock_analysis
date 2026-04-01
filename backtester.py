import os
import pandas as pd
import numpy as np
import glob
from datetime import timedelta

from tws.taiwan_trending import apply_filters


class Backtester:
    """
    Mean-reversion day-trade backtester.

    Entry : next-day open after signal fires
    Exit  : stop-loss | take-profit | time-stop (close of last holding day)
    """

    def __init__(self, start_date, end_date):
        self.start_date = pd.to_datetime(start_date)
        self.end_date   = pd.to_datetime(end_date)
        self.ohlcv_dir  = os.path.join(os.path.dirname(__file__), "data", "ohlcv")

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def run(
        self,
        tickers,
        holding_days    = 5,
        stop_loss_pct   = 0.05,
        take_profit_pct = 0.10,
        commission_pct  = 0.001425,
    ):
        """
        Run backtest across all tickers.

        Returns
        -------
        trades_df : pd.DataFrame  — one row per trade
        summary   : dict          — aggregate performance metrics
        """
        all_trades = []
        for ticker in tickers:
            df = self._load_data(ticker)
            if df is None:
                print(f"  No data for {ticker}")
                continue
            trades = self._run_ticker_backtest(
                df, ticker, holding_days, stop_loss_pct, take_profit_pct
            )
            all_trades.extend(trades)

        if not all_trades:
            print("No trades were generated during the backtest period.")
            return pd.DataFrame(), {}

        trades_df = pd.DataFrame(all_trades)

        # Apply commission (round-trip: buy + sell)
        round_trip = commission_pct * 2
        trades_df["commission"] = (
            trades_df["entry_price"] + trades_df["exit_price"]
        ) * round_trip
        trades_df["net_profit"]        = trades_df["profit"]        - trades_df["commission"]
        trades_df["net_profit_pct"]    = (
            trades_df["net_profit"] / trades_df["entry_price"] * 100
        )

        summary = self._build_summary(trades_df)
        self._print_summary(summary)
        return trades_df, summary

    # ─────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _load_data(self, ticker):
        pattern = os.path.join(self.ohlcv_dir, f"{ticker}_*.csv")
        files   = glob.glob(pattern)
        if not files:
            return None
        df = pd.read_csv(files[0], index_col=0, parse_dates=True)
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["Open", "High", "Low", "Close"])
        return df

    def _run_ticker_backtest(self, df, ticker, holding_days, stop_loss_pct, take_profit_pct):
        trades = []
        try:
            start_idx = df.index.searchsorted(self.start_date, side="left")
            end_idx   = df.index.searchsorted(self.end_date,   side="right")
        except Exception:
            return []

        last_exit_i = -1

        for i in range(start_idx, end_idx + 1):
            if i <= last_exit_i or i < 120:
                continue

            is_signal, _, metrics = apply_filters(df.iloc[:i].copy())
            if not is_signal:
                continue

            entry_loc = i + 1
            if entry_loc >= len(df):
                continue

            entry_date  = df.index[entry_loc]
            entry_price = float(df["Open"].iloc[entry_loc])

            sl_price = entry_price * (1 - stop_loss_pct)
            tp_price = entry_price * (1 + take_profit_pct)

            exit_date  = None
            exit_price = None
            exit_loc   = -1
            exit_reason = "time"

            for j in range(1, holding_days + 1):
                cur = entry_loc + j
                if cur >= len(df):
                    break
                lo = float(df["Low"].iloc[cur])
                hi = float(df["High"].iloc[cur])
                if lo <= sl_price:
                    exit_date   = df.index[cur]
                    exit_price  = sl_price
                    exit_loc    = cur
                    exit_reason = "stop_loss"
                    break
                if hi >= tp_price:
                    exit_date   = df.index[cur]
                    exit_price  = tp_price
                    exit_loc    = cur
                    exit_reason = "take_profit"
                    break

            if exit_date is None:
                exit_loc    = min(entry_loc + holding_days, len(df) - 1)
                exit_date   = df.index[exit_loc]
                exit_price  = float(df["Close"].iloc[exit_loc])
                exit_reason = "time"

            profit     = exit_price - entry_price
            profit_pct = profit / entry_price * 100

            trades.append({
                "ticker":       ticker,
                "entry_date":   entry_date.strftime("%Y-%m-%d"),
                "exit_date":    exit_date.strftime("%Y-%m-%d"),
                "entry_price":  round(entry_price, 2),
                "exit_price":   round(exit_price,  2),
                "profit":       round(profit,     2),
                "profit_pct":   round(profit_pct, 2),
                "exit_reason":  exit_reason,
                "signal_rsi":   round(metrics.get("RSI",  0), 1),
                "signal_bias":  round(metrics.get("bias", 0), 1),
                "signal_score": round(metrics.get("score",0), 1),
            })
            last_exit_i = exit_loc

        return trades

    def _build_summary(self, df: pd.DataFrame) -> dict:
        n     = len(df)
        wins  = int((df["net_profit"] > 0).sum())
        total = float(df["net_profit"].sum())
        avg   = float(df["net_profit_pct"].mean())

        # Annualised Sharpe on net_profit_pct
        ret_series = df["net_profit_pct"] / 100
        sharpe = 0.0
        if ret_series.std() > 0:
            sharpe = float(ret_series.mean() / ret_series.std() * (252 ** 0.5))

        # Max drawdown
        capital        = 100_000.0
        invest_per_trade = capital / 10
        cap_hist       = [capital]
        for _, row in df.sort_values("exit_date").iterrows():
            shares  = invest_per_trade / row["entry_price"]
            capital += row["net_profit"] * shares
            cap_hist.append(capital)
        s    = pd.Series(cap_hist)
        peak = s.expanding().max()
        dd   = ((s - peak) / peak).min()

        # By exit reason
        reason_counts = df["exit_reason"].value_counts().to_dict()

        return {
            "total_trades":   n,
            "wins":           wins,
            "losses":         n - wins,
            "win_rate":       round(wins / n, 4) if n else 0,
            "avg_profit_pct": round(avg, 2),
            "total_profit":   round(total, 2),
            "sharpe":         round(sharpe, 2),
            "max_drawdown":   round(float(dd), 4),
            "stop_loss_exits":   reason_counts.get("stop_loss",   0),
            "take_profit_exits": reason_counts.get("take_profit", 0),
            "time_exits":        reason_counts.get("time",        0),
        }

    def _print_summary(self, s: dict):
        print("\n─── Backtest Results ───────────────────────────")
        print(f"  Trades : {s['total_trades']}  (W {s['wins']} / L {s['losses']})")
        print(f"  Win Rate       : {s['win_rate']*100:.1f}%")
        print(f"  Avg Net P&L    : {s['avg_profit_pct']:+.2f}%")
        print(f"  Total Profit   : {s['total_profit']:+,.0f}")
        print(f"  Sharpe         : {s['sharpe']:.2f}")
        print(f"  Max Drawdown   : {s['max_drawdown']*100:.1f}%")
        print(f"  Exits  SL:{s['stop_loss_exits']}  TP:{s['take_profit_exits']}  Time:{s['time_exits']}")
        print("────────────────────────────────────────────────\n")


if __name__ == "__main__":
    TICKERS_DIR = os.path.join(os.path.dirname(__file__), "data", "ohlcv")
    all_files   = glob.glob(os.path.join(TICKERS_DIR, "*.csv"))
    tickers     = list({os.path.basename(f).split("_")[0] for f in all_files})[:10]

    bt = Backtester(start_date="2025-01-01", end_date="2026-04-01")
    trades_df, summary = bt.run(
        tickers,
        holding_days    = 5,
        stop_loss_pct   = 0.05,
        take_profit_pct = 0.10,
        commission_pct  = 0.001425 * 2,
    )
    if not trades_df.empty:
        print(trades_df[["ticker", "entry_date", "exit_date",
                          "profit_pct", "net_profit_pct", "exit_reason"]].to_string(index=False))
