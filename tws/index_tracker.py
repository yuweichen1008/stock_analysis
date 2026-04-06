"""
TAIEX Market Oracle — daily bull/bear prediction with scoring.

Prediction algorithm: weighted vote across 5 factors.
Scoring: |TAIEX change in pts| × 10 → +score if correct, −score if wrong.

History file: data/index/oracle_history.csv
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

_HISTORY_FILE = Path("data") / "index" / "oracle_history.csv"

_COLS = [
    "date", "direction", "confidence_pct", "factors_json",
    "taiex_open", "taiex_close", "taiex_change_pts",
    "score_pts", "cumulative_score", "is_correct", "status",
]

_FACTOR_WEIGHTS = {
    "spx_overnight":  0.30,
    "taiex_momentum": 0.25,
    "vix_fear":       0.20,
    "signal_count":   0.15,
    "tw_win_rate":    0.10,
}


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _history_path(base_dir: str) -> Path:
    p = Path(base_dir) / _HISTORY_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_history(base_dir: str) -> pd.DataFrame:
    path = _history_path(base_dir)
    if not path.exists():
        return pd.DataFrame(columns=_COLS)
    try:
        df = pd.read_csv(path)
        for col in _COLS:
            if col not in df.columns:
                df[col] = None
        return df
    except Exception:
        return pd.DataFrame(columns=_COLS)


def _save_history(base_dir: str, df: pd.DataFrame) -> None:
    df[_COLS].to_csv(_history_path(base_dir), index=False)


def _fetch_yf_close(ticker: str, period: str = "2d", interval: str = "1d") -> list[float]:
    """Return list of close prices (oldest first) for a yfinance ticker."""
    try:
        hist = yf.Ticker(ticker).history(period=period, interval=interval)
        if hist.empty:
            return []
        return hist["Close"].dropna().tolist()
    except Exception as e:
        logger.warning("yfinance fetch failed for %s: %s", ticker, e)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_taiex_live() -> dict:
    """
    Fetch current TAIEX level via yfinance (15-min delayed).

    Returns dict:
      current_level   float
      change_pts      float
      change_pct      float
      last_updated    str (HH:MM)
      intraday_df     pd.DataFrame (5-min OHLCV, may be empty)
    """
    result = {
        "current_level": None,
        "change_pts": None,
        "change_pct": None,
        "last_updated": None,
        "intraday_df": pd.DataFrame(),
    }
    try:
        intraday = yf.Ticker("^TWII").history(period="1d", interval="5m")
        if not intraday.empty:
            result["current_level"] = float(intraday["Close"].iloc[-1])
            result["last_updated"]  = intraday.index[-1].strftime("%H:%M")
            result["intraday_df"]   = intraday

        # Yesterday close for day-change calculation
        daily = _fetch_yf_close("^TWII", period="5d", interval="1d")
        if len(daily) >= 2 and result["current_level"] is not None:
            prev_close = daily[-2]
            result["change_pts"] = result["current_level"] - prev_close
            result["change_pct"] = result["change_pts"] / prev_close * 100
    except Exception as e:
        logger.warning("get_taiex_live error: %s", e)

    return result


def compute_prediction(base_dir: str) -> dict:
    """
    Compute today's Bull/Bear prediction using a 5-factor weighted vote.

    Returns dict matching oracle_history schema (status="pending", actuals=None).
    """
    today = datetime.now().strftime("%Y-%m-%d")
    factors: dict = {}
    bull_score = 0.0

    # ── Factor 1: SPX overnight return (weight 0.30) ─────────────────────────
    spx_closes = _fetch_yf_close("^GSPC", period="5d", interval="1d")
    if len(spx_closes) >= 2:
        spx_ret = (spx_closes[-1] - spx_closes[-2]) / spx_closes[-2] * 100
        spx_bull = spx_ret > 0.3
        factors["spx_overnight"] = {"value": round(spx_ret, 2), "bull": spx_bull}
        if spx_bull:
            bull_score += _FACTOR_WEIGHTS["spx_overnight"]
    else:
        factors["spx_overnight"] = {"value": None, "bull": False}

    # ── Factor 2: TAIEX prev-day momentum (weight 0.25) ──────────────────────
    twii_closes = _fetch_yf_close("^TWII", period="5d", interval="1d")
    if len(twii_closes) >= 2:
        tw_mom = (twii_closes[-1] - twii_closes[-2]) / twii_closes[-2] * 100
        tw_bull = tw_mom > 0.5
        factors["taiex_momentum"] = {"value": round(tw_mom, 2), "bull": tw_bull}
        if tw_bull:
            bull_score += _FACTOR_WEIGHTS["taiex_momentum"]
    else:
        factors["taiex_momentum"] = {"value": None, "bull": False}

    # ── Factor 3: VIX fear gauge (weight 0.20) ────────────────────────────────
    vix_closes = _fetch_yf_close("^VIX", period="5d", interval="1d")
    if vix_closes:
        vix = vix_closes[-1]
        vix_bull = vix < 20
        factors["vix_fear"] = {"value": round(vix, 1), "bull": vix_bull}
        if vix_bull:
            bull_score += _FACTOR_WEIGHTS["vix_fear"]
    else:
        factors["vix_fear"] = {"value": None, "bull": False}

    # ── Factor 4: TW mean-reversion signal count (weight 0.15) ───────────────
    sig_count = 0
    try:
        trending_file = os.path.join(base_dir, "current_trending.csv")
        if os.path.exists(trending_file):
            df_tr = pd.read_csv(trending_file, dtype={"ticker": str})
            if "category" in df_tr.columns:
                sig_count = int((df_tr["category"] == "mean_reversion").sum())
            else:
                sig_count = len(df_tr)
    except Exception:
        pass
    sig_bull = sig_count >= 3
    factors["signal_count"] = {"value": sig_count, "bull": sig_bull}
    if sig_bull:
        bull_score += _FACTOR_WEIGHTS["signal_count"]

    # ── Factor 5: Recent TW open-day win rate (weight 0.10) ──────────────────
    tw_wr = 0.0
    try:
        hist_file = os.path.join(base_dir, "data", "predictions", "prediction_history.csv")
        if os.path.exists(hist_file):
            ph = pd.read_csv(hist_file)
            ph_tw = ph[(ph["market"] == "TW") & (ph["status"] == "resolved")]
            if len(ph_tw) >= 5:
                recent = ph_tw.sort_values("signal_date").tail(20)
                tw_wr  = float(recent["win_open"].mean() * 100)
    except Exception:
        pass
    wr_bull = tw_wr > 55
    factors["tw_win_rate"] = {"value": round(tw_wr, 1), "bull": wr_bull}
    if wr_bull:
        bull_score += _FACTOR_WEIGHTS["tw_win_rate"]

    # ── Final vote ────────────────────────────────────────────────────────────
    direction      = "Bull" if bull_score >= 0.5 else "Bear"
    confidence_pct = round(max(bull_score, 1 - bull_score) * 100, 1)

    return {
        "date":            today,
        "direction":       direction,
        "confidence_pct":  confidence_pct,
        "factors_json":    json.dumps(factors),
        "taiex_open":      None,
        "taiex_close":     None,
        "taiex_change_pts": None,
        "score_pts":       None,
        "cumulative_score": None,
        "is_correct":      None,
        "status":          "pending",
    }


def save_prediction(base_dir: str, pred: dict) -> None:
    """
    Append prediction to oracle_history.csv.
    Skips silently if today's date already has a row.
    """
    df = _load_history(base_dir)
    today = pred["date"]
    if not df.empty and today in df["date"].values:
        logger.info("Oracle prediction for %s already saved — skipping.", today)
        return
    new_row = pd.DataFrame([pred])
    if df.empty:
        df = new_row.copy()
    else:
        df = pd.concat([df, new_row], ignore_index=True)
    _save_history(base_dir, df)
    print(f"[Oracle] Prediction saved: {pred['direction']} (conf {pred['confidence_pct']}%)")


def resolve_today_prediction(base_dir: str) -> bool:
    """
    Fetch TAIEX EOD data and resolve today's pending prediction.
    Recalculates cumulative_score for all rows.

    Returns True if a prediction was resolved, False otherwise.
    """
    df = _load_history(base_dir)
    if df.empty:
        return False

    today = datetime.now().strftime("%Y-%m-%d")
    mask  = (df["date"] == today) & (df["status"] == "pending")
    if not mask.any():
        return False

    # Fetch today's TAIEX OHLCV — daily first, fall back to intraday
    try:
        taiex_open  = None
        taiex_close = None

        # Try daily data
        hist = yf.Ticker("^TWII").history(period="7d", interval="1d")
        if not hist.empty:
            hist.index = hist.index.tz_localize(None) if hist.index.tzinfo else hist.index
            today_rows = hist[hist.index.strftime("%Y-%m-%d") == today]
            if not today_rows.empty:
                taiex_open  = float(today_rows["Open"].iloc[0])
                taiex_close = float(today_rows["Close"].iloc[0])

        # Fall back: use intraday if daily doesn't have today yet
        if taiex_open is None:
            intra = yf.Ticker("^TWII").history(period="1d", interval="5m")
            if not intra.empty:
                taiex_open  = float(intra["Open"].iloc[0])
                taiex_close = float(intra["Close"].iloc[-1])

        if taiex_open is None:
            logger.warning("No TWII data available for resolution on %s.", today)
            return False
    except Exception as e:
        logger.error("TAIEX resolution fetch error: %s", e)
        return False

    change_pts = taiex_close - taiex_open
    idx        = df.index[mask][0]
    direction  = df.at[idx, "direction"]

    is_correct = (
        (direction == "Bull" and change_pts > 0) or
        (direction == "Bear" and change_pts < 0)
    )
    score_pts = abs(change_pts) * 10 * (1 if is_correct else -1)

    df.at[idx, "taiex_open"]      = round(taiex_open, 1)
    df.at[idx, "taiex_close"]     = round(taiex_close, 1)
    df.at[idx, "taiex_change_pts"] = round(change_pts, 1)
    df.at[idx, "score_pts"]       = round(score_pts, 1)
    df.at[idx, "is_correct"]      = str(is_correct)
    df.at[idx, "status"]          = "resolved"

    # Recompute cumulative_score in chronological order
    df_sorted = df.sort_values("date").reset_index(drop=True)
    cumulative = 0.0
    for i, row in df_sorted.iterrows():
        if row["status"] == "resolved" and pd.notna(row["score_pts"]):
            cumulative += float(row["score_pts"])
            df_sorted.at[i, "cumulative_score"] = round(cumulative, 1)

    _save_history(base_dir, df_sorted)
    outcome = "✅ 正確" if is_correct else "❌ 錯誤"
    print(
        f"[Oracle] Resolved {today}: {direction} → {outcome}  "
        f"TAIEX {change_pts:+.0f}pts  Score {score_pts:+.0f}  Cumulative {cumulative:+.0f}"
    )
    return True


def oracle_stats(base_dir: str) -> dict:
    """
    Aggregate stats from resolved predictions.

    Returns dict:
      total, wins, losses, win_rate_pct,
      cumulative_score, avg_score_per_day, streak (consecutive correct from latest)
    """
    df = _load_history(base_dir)
    resolved = df[df["status"] == "resolved"].copy()

    if resolved.empty:
        return {
            "total": 0, "wins": 0, "losses": 0, "win_rate_pct": 0.0,
            "cumulative_score": 0.0, "avg_score_per_day": 0.0, "streak": 0,
        }

    resolved = resolved.sort_values("date")
    total    = len(resolved)
    wins     = int((resolved["is_correct"] == True).sum())
    losses   = total - wins

    # Cumulative score from last resolved row
    cum_score_series = pd.to_numeric(resolved["cumulative_score"], errors="coerce")
    cumulative_score  = float(cum_score_series.iloc[-1]) if cum_score_series.notna().any() else 0.0

    # Streak: consecutive correct from latest
    streak = 0
    for correct in reversed(resolved["is_correct"].tolist()):
        if correct is True or correct == "True":
            streak += 1
        else:
            break

    return {
        "total":             total,
        "wins":              wins,
        "losses":            losses,
        "win_rate_pct":      round(wins / total * 100, 1) if total else 0.0,
        "cumulative_score":  round(cumulative_score, 1),
        "avg_score_per_day": round(cumulative_score / total, 1) if total else 0.0,
        "streak":            streak,
    }
