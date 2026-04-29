"""
TAIEX Market Oracle — daily bull/bear prediction with scoring.

Prediction algorithm: weighted vote across 5 factors.
Scoring: fixed game points (SCORE_WIN if correct, SCORE_LOSE if wrong).

History file: data/index/oracle_history.csv
"""
from __future__ import annotations

import io
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
_GCS_ORACLE_OBJECT = "data/index/oracle_history.csv"

_COLS = [
    "date", "direction", "confidence_pct", "factors_json",
    "taiex_open", "taiex_close", "taiex_change_pts",
    "score_pts", "cumulative_score", "is_correct", "status",
]

# Game scoring — fixed points regardless of TAIEX movement magnitude
SCORE_WIN  =  100   # points for a correct prediction
SCORE_LOSE =  -50   # points for a wrong prediction

_FACTOR_WEIGHTS = {
    # Overnight US session — tech-heavy weights because TAIEX ~60% tech
    "sox_overnight":   0.25,   # Philadelphia Semiconductor Index (SOXX proxy)
    "spx_overnight":   0.20,   # S&P 500 broad market
    "ndx_overnight":   0.15,   # Nasdaq 100 (QQQ) tech sentiment
    # Local / structural
    "taiex_momentum":  0.15,   # TAIEX prev-day direction
    "vix_direction":   0.10,   # VIX falling = risk-on (direction > level)
    "usdtwd_fx":       0.10,   # USD/TWD: stronger USD → foreign selling of TAIEX
    "signal_count":    0.05,   # TW mean-reversion signal breadth
}


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _history_path(base_dir: str) -> Path:
    p = Path(base_dir) / _HISTORY_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _gcs_upload_history(df: pd.DataFrame) -> None:
    """Upload oracle_history.csv to GCS when GCS_BUCKET is configured."""
    try:
        from api.config import settings
        if not settings.GCS_BUCKET:
            return
        from google.cloud import storage
        client = storage.Client()
        blob = client.bucket(settings.GCS_BUCKET).blob(_GCS_ORACLE_OBJECT)
        blob.upload_from_string(df[_COLS].to_csv(index=False), content_type="text/csv")
        logger.info("Oracle history uploaded to GCS: gs://%s/%s", settings.GCS_BUCKET, _GCS_ORACLE_OBJECT)
    except Exception as e:
        logger.warning("GCS oracle history upload failed: %s", e)


def _gcs_download_history() -> Optional[pd.DataFrame]:
    """Download oracle_history.csv from GCS. Returns None if unavailable."""
    try:
        from api.config import settings
        if not settings.GCS_BUCKET:
            return None
        from google.cloud import storage
        client = storage.Client()
        blob = client.bucket(settings.GCS_BUCKET).blob(_GCS_ORACLE_OBJECT)
        if not blob.exists():
            return None
        df = pd.read_csv(io.StringIO(blob.download_as_text()))
        for col in _COLS:
            if col not in df.columns:
                df[col] = None
        return df
    except Exception as e:
        logger.warning("GCS oracle history download failed: %s", e)
        return None


def _load_history(base_dir: str) -> pd.DataFrame:
    """Load oracle history — GCS first (production), local disk fallback (dev)."""
    gcs_df = _gcs_download_history()
    if gcs_df is not None:
        return gcs_df
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
    """Save oracle history to local disk and upload to GCS."""
    df[_COLS].to_csv(_history_path(base_dir), index=False)
    _gcs_upload_history(df)


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

    # ── Factor 1: SOX overnight return (weight 0.25) ─────────────────────────
    # Philadelphia Semiconductor Index — strongest single predictor of TAIEX
    # because TSMC + semiconductor stocks are ~60% of the index.
    sox_closes = _fetch_yf_close("SOXX", period="5d", interval="1d")   # iShares SOXX ETF
    if len(sox_closes) >= 2:
        sox_ret = (sox_closes[-1] - sox_closes[-2]) / sox_closes[-2] * 100
        sox_bull = sox_ret > 0.2
        factors["sox_overnight"] = {"value": round(sox_ret, 2), "bull": sox_bull}
        if sox_bull:
            bull_score += _FACTOR_WEIGHTS["sox_overnight"]
    else:
        factors["sox_overnight"] = {"value": None, "bull": False}

    # ── Factor 2: SPX overnight return (weight 0.20) ─────────────────────────
    spx_closes = _fetch_yf_close("^GSPC", period="5d", interval="1d")
    if len(spx_closes) >= 2:
        spx_ret = (spx_closes[-1] - spx_closes[-2]) / spx_closes[-2] * 100
        spx_bull = spx_ret > 0.3
        factors["spx_overnight"] = {"value": round(spx_ret, 2), "bull": spx_bull}
        if spx_bull:
            bull_score += _FACTOR_WEIGHTS["spx_overnight"]
    else:
        factors["spx_overnight"] = {"value": None, "bull": False}

    # ── Factor 3: Nasdaq 100 overnight return (weight 0.15) ──────────────────
    ndx_closes = _fetch_yf_close("QQQ", period="5d", interval="1d")
    if len(ndx_closes) >= 2:
        ndx_ret = (ndx_closes[-1] - ndx_closes[-2]) / ndx_closes[-2] * 100
        ndx_bull = ndx_ret > 0.2
        factors["ndx_overnight"] = {"value": round(ndx_ret, 2), "bull": ndx_bull}
        if ndx_bull:
            bull_score += _FACTOR_WEIGHTS["ndx_overnight"]
    else:
        factors["ndx_overnight"] = {"value": None, "bull": False}

    # ── Factor 4: TAIEX prev-day momentum (weight 0.15) ──────────────────────
    twii_closes = _fetch_yf_close("^TWII", period="5d", interval="1d")
    if len(twii_closes) >= 2:
        tw_mom = (twii_closes[-1] - twii_closes[-2]) / twii_closes[-2] * 100
        tw_bull = tw_mom > 0.5
        factors["taiex_momentum"] = {"value": round(tw_mom, 2), "bull": tw_bull}
        if tw_bull:
            bull_score += _FACTOR_WEIGHTS["taiex_momentum"]
    else:
        factors["taiex_momentum"] = {"value": None, "bull": False}

    # ── Factor 5: VIX direction (weight 0.10) ────────────────────────────────
    # Direction beats level: falling VIX = risk-on regardless of absolute value.
    vix_closes = _fetch_yf_close("^VIX", period="5d", interval="1d")
    if len(vix_closes) >= 2:
        vix_now  = vix_closes[-1]
        vix_prev = vix_closes[-2]
        vix_fall = vix_now < vix_prev          # falling = risk-on
        vix_low  = vix_now < 20               # absolute calm
        vix_bull = vix_fall or vix_low
        factors["vix_direction"] = {
            "value": round(vix_now, 1),
            "change": round(vix_now - vix_prev, 2),
            "bull": vix_bull,
        }
        if vix_bull:
            bull_score += _FACTOR_WEIGHTS["vix_direction"]
    else:
        factors["vix_direction"] = {"value": None, "bull": False}

    # ── Factor 6: USD/TWD exchange rate (weight 0.10) ────────────────────────
    # Stronger USD (rising USDTWD) means foreign selling pressure on TAIEX.
    # Bull if TWD is stable or strengthening (USDTWD falling or flat).
    usdtwd_closes = _fetch_yf_close("TWD=X", period="5d", interval="1d")
    if len(usdtwd_closes) >= 2:
        fx_change = (usdtwd_closes[-1] - usdtwd_closes[-2]) / usdtwd_closes[-2] * 100
        fx_bull = fx_change < 0.2   # USD not strengthening materially
        factors["usdtwd_fx"] = {"value": round(usdtwd_closes[-1], 3), "change_pct": round(fx_change, 3), "bull": fx_bull}
        if fx_bull:
            bull_score += _FACTOR_WEIGHTS["usdtwd_fx"]
    else:
        factors["usdtwd_fx"] = {"value": None, "bull": True}  # default bull if unavailable

    # ── Factor 7: TW mean-reversion signal count (weight 0.05) ───────────────
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
    score_pts = SCORE_WIN if is_correct else SCORE_LOSE

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


# ─────────────────────────────────────────────────────────────────────────────
# Backtesting
# ─────────────────────────────────────────────────────────────────────────────

def backtest_oracle(
    start_date: str,
    end_date: str,
    weights: dict | None = None,
    score_win: int = SCORE_WIN,
    score_lose: int = SCORE_LOSE,
) -> tuple[pd.DataFrame, dict]:
    """
    Simulate the prediction algorithm on historical TAIEX data.

    Uses 3 market-data factors (SPX overnight, TAIEX momentum, VIX) since
    signal_count and tw_win_rate are not available historically.

    Parameters
    ----------
    start_date, end_date : "YYYY-MM-DD" strings (inclusive)
    weights : dict with keys spx_overnight, taiex_momentum, vix_fear.
              Weights are normalised internally so they don't need to sum to 1.
    score_win / score_lose : game points for correct / wrong predictions.

    Returns
    -------
    results_df : pd.DataFrame — one row per simulated day
    summary    : dict — aggregate stats
    """
    if weights is None:
        weights = {
            "sox_overnight":  0.30,
            "spx_overnight":  0.25,
            "ndx_overnight":  0.20,
            "taiex_momentum": 0.15,
            "vix_direction":  0.10,
        }

    total_w = sum(weights.values()) or 1.0

    # Fetch historical data with a buffer before start for prev-day calculations
    buf_start = (pd.Timestamp(start_date) - pd.Timedelta(days=10)).strftime("%Y-%m-%d")

    def _dl(ticker):
        try:
            h = yf.Ticker(ticker).history(start=buf_start, end=end_date, interval="1d")
            if h.empty:
                return pd.DataFrame()
            h.index = h.index.tz_localize(None) if h.index.tzinfo else h.index
            h.index = pd.DatetimeIndex([pd.Timestamp(str(i.date())) for i in h.index])
            return h
        except Exception as e:
            logger.warning("backtest download failed for %s: %s", ticker, e)
            return pd.DataFrame()

    twii = _dl("^TWII")
    spx  = _dl("^GSPC")
    vix  = _dl("^VIX")
    sox  = _dl("SOXX")
    ndx  = _dl("QQQ")

    if twii.empty:
        return pd.DataFrame(), {}

    # Trading days in range
    range_mask = (twii.index >= pd.Timestamp(start_date)) & (twii.index <= pd.Timestamp(end_date))
    trade_days = twii.index[range_mask]

    results = []
    for date in trade_days:
        twii_pos = twii.index.get_loc(date)
        if twii_pos < 2:
            continue
        prev_date = twii.index[twii_pos - 1]

        def _ret(df, date):
            """Overnight % return into `date` using previous row in df."""
            if df.empty or date not in df.index:
                return None
            pos = df.index.get_loc(date)
            if pos < 1:
                return None
            c0 = float(df["Close"].iloc[pos - 1])
            c1 = float(df["Close"].iloc[pos])
            return round((c1 - c0) / c0 * 100, 2)

        # ── SOX overnight ─────────────────────────────────────────────────────
        sox_val  = _ret(sox, prev_date)
        sox_bull = sox_val is not None and sox_val > 0.2

        # ── SPX overnight ─────────────────────────────────────────────────────
        spx_val  = _ret(spx, prev_date)
        spx_bull = spx_val is not None and spx_val > 0.3

        # ── NDX overnight ─────────────────────────────────────────────────────
        ndx_val  = _ret(ndx, prev_date)
        ndx_bull = ndx_val is not None and ndx_val > 0.2

        # ── TAIEX momentum (prev-day %) ───────────────────────────────────────
        tw_val  = None
        tw_bull = False
        prev2 = twii.index[twii_pos - 2]
        c0    = float(twii.at[prev2,     "Close"])
        c1    = float(twii.at[prev_date, "Close"])
        tw_val  = round((c1 - c0) / c0 * 100, 2)
        tw_bull = tw_val > 0.5

        # ── VIX direction ─────────────────────────────────────────────────────
        vix_val  = None
        vix_bull = False
        if not vix.empty and prev_date in vix.index:
            vix_pos = vix.index.get_loc(prev_date)
            vix_val = round(float(vix["Close"].iloc[vix_pos]), 1)
            if vix_pos >= 1:
                vix_prev_val = float(vix["Close"].iloc[vix_pos - 1])
                vix_bull = (vix_val < vix_prev_val) or (vix_val < 20)
            else:
                vix_bull = vix_val < 20

        # ── Vote ──────────────────────────────────────────────────────────────
        bull_score = 0.0
        if sox_bull: bull_score += weights.get("sox_overnight",  0.30)
        if spx_bull: bull_score += weights.get("spx_overnight",  0.25)
        if ndx_bull: bull_score += weights.get("ndx_overnight",  0.20)
        if tw_bull:  bull_score += weights.get("taiex_momentum", 0.15)
        if vix_bull: bull_score += weights.get("vix_direction",  0.10)
        bull_score /= total_w

        direction      = "Bull" if bull_score >= 0.5 else "Bear"
        confidence_pct = round(max(bull_score, 1.0 - bull_score) * 100, 1)

        # ── Actual ───────────────────────────────────────────────────────────
        taiex_open  = float(twii.at[date, "Open"])
        taiex_close = float(twii.at[date, "Close"])
        change_pts  = taiex_close - taiex_open
        actual_dir  = "Bull" if change_pts > 0 else "Bear"
        is_correct  = direction == actual_dir
        score_pts   = score_win if is_correct else score_lose

        results.append({
            "date":             date.strftime("%Y-%m-%d"),
            "direction":        direction,
            "actual_dir":       actual_dir,
            "confidence_pct":   confidence_pct,
            "sox_ret":          sox_val,
            "spx_ret":          spx_val,
            "ndx_ret":          ndx_val,
            "taiex_mom":        tw_val,
            "vix":              vix_val,
            "taiex_open":       round(taiex_open,  1),
            "taiex_close":      round(taiex_close, 1),
            "taiex_change_pts": round(change_pts,  1),
            "is_correct":       is_correct,
            "score_pts":        score_pts,
        })

    if not results:
        return pd.DataFrame(), {}

    df = pd.DataFrame(results)
    df["cumulative_score"] = df["score_pts"].cumsum()

    total = len(df)
    wins  = int(df["is_correct"].sum())

    # Best streak
    best_streak = cur = 0
    for v in df["is_correct"]:
        cur = cur + 1 if v else 0
        best_streak = max(best_streak, cur)

    summary = {
        "total":             total,
        "wins":              wins,
        "losses":            total - wins,
        "win_rate_pct":      round(wins / total * 100, 1) if total else 0.0,
        "cumulative_score":  round(float(df["cumulative_score"].iloc[-1]), 0),
        "avg_score_per_day": round(float(df["score_pts"].mean()), 1),
        "best_streak":       best_streak,
        "best_day":          float(df["score_pts"].max()),
        "worst_day":         float(df["score_pts"].min()),
    }
    return df, summary
