"""
Fetch options chain metrics for a single US ticker.

For each ticker:
  - RSI(14) from 30-day price history
  - PCR, put/call volumes from two nearest expiries
  - Average IV, total OI, volume/OI ratio
  - IV Rank from accumulated options_iv_snapshots history

Returns a metrics dict or None on any failure.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import numpy as np
import yfinance as yf

from news.pcr import _pcr_label

logger = logging.getLogger(__name__)


def _compute_rsi(closes: "pd.Series", period: int = 14) -> float | None:
    """Wilder-smoothed RSI(period). Returns None when insufficient data."""
    if len(closes) < period + 1:
        return None
    delta = closes.diff().dropna()
    gains = delta.clip(lower=0)
    losses = (-delta).clip(lower=0)
    # Wilder smoothing (exponential with alpha=1/period)
    avg_gain = gains.ewm(alpha=1 / period, adjust=False).mean().iloc[-1]
    avg_loss = losses.ewm(alpha=1 / period, adjust=False).mean().iloc[-1]
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _iv_rank(ticker: str, today_iv: float, db) -> float | None:
    """Compute IV Rank from accumulated snapshot history. Returns None if < 30 rows."""
    try:
        from api.db import OptionsIvSnapshot
        rows = (
            db.query(OptionsIvSnapshot.avg_iv)
            .filter(
                OptionsIvSnapshot.ticker == ticker,
                OptionsIvSnapshot.avg_iv.isnot(None),
            )
            .order_by(OptionsIvSnapshot.snapshot_at.desc())
            .limit(730)  # ~365 days × 2 runs/day
            .all()
        )
        ivs = [r.avg_iv for r in rows]
        if len(ivs) < 30:
            return None
        iv_low  = min(ivs)
        iv_high = max(ivs)
        if iv_high <= iv_low:
            return 50.0
        return round((today_iv - iv_low) / (iv_high - iv_low) * 100, 1)
    except Exception as exc:
        logger.debug("iv_rank(%s) error: %s", ticker, exc)
        return None


def _store_iv_snapshot(ticker: str, avg_iv: float | None, snapshot_at: datetime, db) -> None:
    from api.db import OptionsIvSnapshot
    try:
        db.add(OptionsIvSnapshot(
            ticker=ticker,
            snapshot_at=snapshot_at,
            avg_iv=avg_iv,
        ))
    except Exception as exc:
        logger.debug("iv_snapshot store error for %s: %s", ticker, exc)


def fetch_options_metrics(ticker: str, db, snapshot_at: datetime) -> dict | None:
    """
    Fetch and compute all options metrics for one ticker.
    Also writes an OptionsIvSnapshot row unconditionally (IV history accumulation).
    Returns None on any error or if ticker has no options.
    """
    if not ticker or ticker.isdigit():
        return None

    try:
        t = yf.Ticker(ticker)

        # ── Price + RSI ───────────────────────────────────────────────────────
        hist = t.history(period="30d", auto_adjust=True)
        if hist.empty or len(hist) < 2:
            return None
        closes = hist["Close"].dropna()
        price = round(float(closes.iloc[-1]), 4)
        price_prev = float(closes.iloc[-2])
        price_change_1d = round((price - price_prev) / price_prev * 100, 2) if price_prev > 0 else None
        rsi_14 = _compute_rsi(closes)

        # ── Options chain (two nearest expiries) ──────────────────────────────
        exps = t.options
        if not exps:
            _store_iv_snapshot(ticker, None, snapshot_at, db)
            return None

        target_exps = exps[:2]  # nearest + second-nearest
        put_vol_total  = 0
        call_vol_total = 0
        oi_total       = 0
        iv_values: list[float] = []

        for exp in target_exps:
            try:
                chain = t.option_chain(exp)
                put_vol_total  += int(chain.puts["volume"].fillna(0).sum())
                call_vol_total += int(chain.calls["volume"].fillna(0).sum())
                oi_total       += int(chain.puts["openInterest"].fillna(0).sum())
                oi_total       += int(chain.calls["openInterest"].fillna(0).sum())
                # Collect IV from liquid options only
                for df in [chain.puts, chain.calls]:
                    mask = (df["volume"].fillna(0) > 0) & (df["impliedVolatility"].fillna(0) > 0)
                    iv_values.extend(df.loc[mask, "impliedVolatility"].tolist())
                time.sleep(0.1)
            except Exception:
                continue

        if call_vol_total == 0:
            _store_iv_snapshot(ticker, None, snapshot_at, db)
            return None

        pcr = round(put_vol_total / call_vol_total, 3)
        avg_iv = round(float(np.mean(iv_values)), 4) if iv_values else None
        volume_oi_ratio = round((put_vol_total + call_vol_total) / oi_total, 3) if oi_total > 0 else None

        # ── IV Rank (uses stored history) ─────────────────────────────────────
        iv_rank = _iv_rank(ticker, avg_iv, db) if avg_iv is not None else None

        # Store IV snapshot for history accumulation
        _store_iv_snapshot(ticker, avg_iv, snapshot_at, db)

        return {
            "ticker":          ticker,
            "snapshot_at":     snapshot_at,
            "price":           price,
            "price_change_1d": price_change_1d,
            "rsi_14":          rsi_14,
            "pcr":             pcr,
            "pcr_label":       _pcr_label(pcr),
            "put_volume":      put_vol_total,
            "call_volume":     call_vol_total,
            "avg_iv":          avg_iv,
            "iv_rank":         iv_rank,
            "total_oi":        oi_total,
            "volume_oi_ratio": volume_oi_ratio,
        }

    except Exception as exc:
        logger.warning("fetch_options_metrics(%s) error: %s", ticker, exc)
        return None
