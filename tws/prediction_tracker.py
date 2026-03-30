"""
Prediction Tracker — record signal predictions and resolve outcomes.

Strategy: mean-reversion day trade
  Entry : signal date closing price  (buy at close)
  Exit  : next trading day open      (sell at open)
  WIN   : next_open > entry_price
  LOSS  : next_open <= entry_price

History file: data/predictions/prediction_history.csv

Columns:
  signal_date     — date signal was generated  (YYYY-MM-DD)
  market          — "TW" or "US"
  ticker          — stock code
  entry_price     — closing price on signal_date (=buy price)
  score           — signal quality score (0-10)
  RSI             — RSI on signal_date
  bias            — bias% on signal_date
  vol_ratio       — volume ratio on signal_date
  news_sentiment  — news sentiment score
  target_date     — next trading day after signal_date
  target_open     — actual open on target_date  (filled on resolution)
  target_close    — actual close on target_date (filled on resolution)
  open_return_pct — (target_open  - entry_price) / entry_price * 100
  close_return_pct— (target_close - entry_price) / entry_price * 100
  win_open        — True if open_return_pct > 0
  win_close       — True if close_return_pct > 0
  status          — "pending" | "resolved" | "no_data"
"""

from __future__ import annotations

import glob
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

_HISTORY_COLS = [
    "signal_date", "market", "ticker",
    "entry_price", "score", "RSI", "bias", "vol_ratio", "news_sentiment",
    "target_date",
    "target_open", "target_close",
    "open_return_pct", "close_return_pct",
    "win_open", "win_close",
    "status",
]

_PENDING  = "pending"
_RESOLVED = "resolved"
_NO_DATA  = "no_data"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _history_path(base_dir: str) -> Path:
    p = Path(base_dir) / "data" / "predictions"
    p.mkdir(parents=True, exist_ok=True)
    return p / "prediction_history.csv"


def _load_history(base_dir: str) -> pd.DataFrame:
    path = _history_path(base_dir)
    if not path.exists():
        return pd.DataFrame(columns=_HISTORY_COLS)
    df = pd.read_csv(path, dtype={"ticker": str, "market": str, "status": str})
    for col in _HISTORY_COLS:
        if col not in df.columns:
            df[col] = None
    return df


def _save_history(base_dir: str, df: pd.DataFrame) -> None:
    df[_HISTORY_COLS].to_csv(_history_path(base_dir), index=False, encoding="utf-8-sig")


def _next_trading_date(date_str: str) -> str:
    """Return next Mon–Fri date after date_str (no holiday calendar, conservative)."""
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    d += timedelta(days=1)
    while d.weekday() >= 5:      # skip Sat(5) / Sun(6)
        d += timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def _ohlcv_for_ticker(base_dir: str, ticker: str, market: str) -> Optional[pd.DataFrame]:
    """Load the OHLCV CSV for a ticker (TW or US)."""
    if market == "TW":
        ohlcv_dir = str(Path(base_dir) / "data" / "ohlcv")
    else:
        ohlcv_dir = str(Path(base_dir) / "data_us" / "ohlcv")
    files = glob.glob(os.path.join(ohlcv_dir, f"{ticker}_*.csv"))
    if not files:
        return None
    try:
        df = pd.read_csv(files[0], index_col=0)
        df.index = pd.to_datetime(df.index, errors="coerce")
        df.index = df.index.normalize()          # strip time component
        df["Open"]  = pd.to_numeric(df.get("Open"),  errors="coerce")
        df["Close"] = pd.to_numeric(df.get("Close"), errors="coerce")
        return df
    except Exception as e:
        logger.debug("_ohlcv_for_ticker(%s) failed: %s", ticker, e)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def save_predictions(base_dir: str, signals_df: pd.DataFrame, market: str = "TW") -> int:
    """
    Append today's signals to the prediction history as pending entries.

    Idempotent: skips any (signal_date, market, ticker) combination that is
    already recorded, so it is safe to call multiple times on the same day.

    Returns the number of NEW rows added.
    """
    if signals_df.empty:
        return 0

    history = _load_history(base_dir)

    existing_keys = set(
        zip(
            history["signal_date"].astype(str),
            history["market"].astype(str),
            history["ticker"].astype(str),
        )
    )

    new_rows = []
    for _, row in signals_df.iterrows():
        ticker      = str(row.get("ticker", ""))
        signal_date = str(row.get("last_date", datetime.now().strftime("%Y-%m-%d")))
        key         = (signal_date, market, ticker)
        if key in existing_keys:
            continue

        entry_price = row.get("price")
        try:
            entry_price = float(entry_price)
        except (TypeError, ValueError):
            continue          # can't track without a price

        new_rows.append({
            "signal_date":      signal_date,
            "market":           market,
            "ticker":           ticker,
            "entry_price":      round(entry_price, 4),
            "score":            round(float(row.get("score", 0) or 0), 2),
            "RSI":              round(float(row.get("RSI", 0)   or 0), 2),
            "bias":             round(float(row.get("bias", 0)  or 0), 2),
            "vol_ratio":        row.get("vol_ratio"),
            "news_sentiment":   row.get("news_sentiment"),
            "target_date":      _next_trading_date(signal_date),
            "target_open":      None,
            "target_close":     None,
            "open_return_pct":  None,
            "close_return_pct": None,
            "win_open":         None,
            "win_close":        None,
            "status":           _PENDING,
        })

    if not new_rows:
        return 0

    combined = pd.concat([history, pd.DataFrame(new_rows)], ignore_index=True)
    _save_history(base_dir, combined)
    logger.info("save_predictions: +%d rows → %s", len(new_rows), _history_path(base_dir))
    print(f"[Tracker] {market} predictions saved: {len(new_rows)} new entries")
    return len(new_rows)


def resolve_outcomes(base_dir: str) -> int:
    """
    Scan all pending predictions and fill in actual prices from OHLCV files.

    Call this AFTER sync_daily_data() so the OHLCV files are fresh.
    Returns the number of rows newly resolved.
    """
    history = _load_history(base_dir)
    if history.empty:
        return 0

    pending = history[history["status"] == _PENDING].copy()
    if pending.empty:
        return 0

    today = datetime.now().date().strftime("%Y-%m-%d")
    resolved_count = 0

    for idx, row in pending.iterrows():
        target_date = str(row["target_date"])
        if target_date >= today:
            # Target day hasn't arrived yet — leave pending
            continue

        ticker  = str(row["ticker"])
        market  = str(row["market"])
        ohlcv   = _ohlcv_for_ticker(base_dir, ticker, market)

        if ohlcv is None:
            history.at[idx, "status"] = _NO_DATA
            continue

        # Match the target date row
        target_ts = pd.Timestamp(target_date)
        if target_ts not in ohlcv.index:
            # Might be a holiday — try next available date within 3 days
            for offset in range(1, 4):
                cand = target_ts + pd.Timedelta(days=offset)
                if cand in ohlcv.index:
                    target_ts = cand
                    history.at[idx, "target_date"] = cand.strftime("%Y-%m-%d")
                    break
            else:
                history.at[idx, "status"] = _NO_DATA
                continue

        target_row   = ohlcv.loc[target_ts]
        target_open  = target_row.get("Open")
        target_close = target_row.get("Close")
        entry_price  = float(row["entry_price"])

        if pd.isna(target_open) or pd.isna(target_close) or entry_price == 0:
            history.at[idx, "status"] = _NO_DATA
            continue

        open_ret  = (target_open  - entry_price) / entry_price * 100
        close_ret = (target_close - entry_price) / entry_price * 100

        history.at[idx, "target_open"]     = round(float(target_open),  4)
        history.at[idx, "target_close"]    = round(float(target_close), 4)
        history.at[idx, "open_return_pct"] = round(open_ret,  2)
        history.at[idx, "close_return_pct"]= round(close_ret, 2)
        history.at[idx, "win_open"]        = bool(open_ret  > 0)
        history.at[idx, "win_close"]       = bool(close_ret > 0)
        history.at[idx, "status"]          = _RESOLVED
        resolved_count += 1

    if resolved_count > 0:
        _save_history(base_dir, history)
        logger.info("resolve_outcomes: %d predictions resolved", resolved_count)
        print(f"[Tracker] Resolved {resolved_count} pending predictions")

    return resolved_count


def prediction_summary(base_dir: str) -> dict:
    """
    Return a summary dict with overall and segmented win rates.
    Useful for CLI output or quick health-check.
    """
    history = _load_history(base_dir)
    resolved = history[history["status"] == _RESOLVED]
    if resolved.empty:
        return {"total": 0}

    total     = len(resolved)
    win_open  = int(resolved["win_open"].sum())
    win_close = int(resolved["win_close"].sum())

    return {
        "total":         total,
        "pending":       int((history["status"] == _PENDING).sum()),
        "win_open":      win_open,
        "win_close":     win_close,
        "win_rate_open":  round(win_open  / total * 100, 1),
        "win_rate_close": round(win_close / total * 100, 1),
        "avg_open_ret":   round(resolved["open_return_pct"].mean(),  2),
        "avg_close_ret":  round(resolved["close_return_pct"].mean(), 2),
    }
