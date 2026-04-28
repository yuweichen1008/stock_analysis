"""
Options screener API — daily RSI + PCR + IV Rank signals for US stocks.

Endpoints:
  GET /api/options/screener                    — latest options signals (filtered)
  GET /api/options/screener/{ticker}/history   — signal history for one ticker
  GET /api/options/overview                    — market-wide summary (VIX, PCR, breadth)
"""
from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.db import OptionsSignal, get_db

router = APIRouter(prefix="/api/options", tags=["options"])

_cache_screener:  dict = {"data": None, "ts": 0.0}
_cache_overview:  dict = {"data": None, "ts": 0.0}
_SCREENER_TTL = 300.0   # 5 min — options flow changes within sessions
_OVERVIEW_TTL = 600.0   # 10 min


def _row_dict(r: OptionsSignal) -> dict:
    return {
        "id":              r.id,
        "ticker":          r.ticker,
        "snapshot_at":     r.snapshot_at.isoformat() if r.snapshot_at else None,
        "price":           r.price,
        "price_change_1d": r.price_change_1d,
        "rsi_14":          r.rsi_14,
        "pcr":             r.pcr,
        "pcr_label":       r.pcr_label,
        "put_volume":      r.put_volume,
        "call_volume":     r.call_volume,
        "avg_iv":          r.avg_iv,
        "iv_rank":         r.iv_rank,
        "total_oi":        r.total_oi,
        "volume_oi_ratio": r.volume_oi_ratio,
        "signal_type":     r.signal_type,
        "signal_score":    r.signal_score,
        "signal_reason":   r.signal_reason,
        "executed":        r.executed,
        "created_at":      r.created_at.isoformat() if r.created_at else None,
    }


@router.get("/screener")
def get_options_screener(
    signal_only: bool          = Query(True,  description="Only return signal tickers"),
    signal_type: Optional[str] = Query("",    description="buy_signal | sell_signal | unusual_activity"),
    pcr_label:   Optional[str] = Query("",    description="extreme_fear | fear | neutral | greed | extreme_greed"),
    rsi_zone:    Optional[str] = Query("",    description="oversold | overbought | neutral"),
    limit:       int           = Query(20,    ge=1, le=200),
    offset:      int           = Query(0,     ge=0),
    db: Session = Depends(get_db),
):
    """Latest options signals — one row per ticker from the most recent pipeline run."""
    cache_key = f"{signal_only}|{signal_type}|{pcr_label}|{rsi_zone}|{limit}|{offset}"
    now = time.time()
    if (
        _cache_screener["data"] is not None
        and now - _cache_screener["ts"] < _SCREENER_TTL
        and _cache_screener.get("key") == cache_key
    ):
        return _cache_screener["data"]

    # Subquery: latest snapshot_at per ticker
    latest_sub = (
        db.query(
            OptionsSignal.ticker,
            func.max(OptionsSignal.snapshot_at).label("latest_snap"),
        )
        .group_by(OptionsSignal.ticker)
        .subquery()
    )

    q = (
        db.query(OptionsSignal)
        .join(
            latest_sub,
            (OptionsSignal.ticker == latest_sub.c.ticker)
            & (OptionsSignal.snapshot_at == latest_sub.c.latest_snap),
        )
    )

    if signal_only:
        q = q.filter(OptionsSignal.signal_type.isnot(None))
    if signal_type:
        q = q.filter(OptionsSignal.signal_type == signal_type)
    if pcr_label:
        q = q.filter(OptionsSignal.pcr_label == pcr_label)
    if rsi_zone == "oversold":
        q = q.filter(OptionsSignal.rsi_14 < 35)
    elif rsi_zone == "overbought":
        q = q.filter(OptionsSignal.rsi_14 > 65)

    rows = (
        q.order_by(OptionsSignal.signal_score.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    latest_snap = (
        db.query(func.max(OptionsSignal.snapshot_at)).scalar()
    )

    result = {
        "snapshot_at": latest_snap.isoformat() if latest_snap else None,
        "count":       len(rows),
        "signals":     [_row_dict(r) for r in rows],
    }
    _cache_screener["data"] = result
    _cache_screener["ts"]   = now
    _cache_screener["key"]  = cache_key
    return result


@router.get("/screener/{ticker}/history")
def get_options_history(ticker: str, db: Session = Depends(get_db)):
    """All options signal history for one ticker (last 30 days)."""
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(days=30)
    rows = (
        db.query(OptionsSignal)
        .filter(
            OptionsSignal.ticker == ticker.upper(),
            OptionsSignal.created_at >= cutoff,
        )
        .order_by(OptionsSignal.snapshot_at.desc())
        .all()
    )
    return {"ticker": ticker.upper(), "history": [_row_dict(r) for r in rows]}


@router.get("/overview")
def get_options_overview(db: Session = Depends(get_db)):
    """Market-wide options summary: VIX, average PCR, signal breadth, top 3."""
    now = time.time()
    if _cache_overview["data"] is not None and now - _cache_overview["ts"] < _OVERVIEW_TTL:
        return _cache_overview["data"]

    # VIX
    vix = None
    try:
        import yfinance as yf
        vix_hist = yf.Ticker("^VIX").history(period="2d", progress=False)
        if not vix_hist.empty:
            vix = round(float(vix_hist["Close"].iloc[-1]), 2)
    except Exception:
        pass

    # Latest snapshot stats
    latest_snap = db.query(func.max(OptionsSignal.snapshot_at)).scalar()
    market_pcr   = None
    buy_count    = 0
    sell_count   = 0
    unusual_count= 0
    top_signals: list[dict] = []

    if latest_snap:
        snap_rows = (
            db.query(OptionsSignal)
            .filter(OptionsSignal.snapshot_at == latest_snap)
            .all()
        )
        pcr_vals = [r.pcr for r in snap_rows if r.pcr is not None]
        if pcr_vals:
            market_pcr = round(sum(pcr_vals) / len(pcr_vals), 3)

        for r in snap_rows:
            if r.signal_type == "buy_signal":
                buy_count += 1
            elif r.signal_type == "sell_signal":
                sell_count += 1
            elif r.signal_type == "unusual_activity":
                unusual_count += 1

        top_rows = (
            db.query(OptionsSignal)
            .filter(
                OptionsSignal.snapshot_at == latest_snap,
                OptionsSignal.signal_type.isnot(None),
            )
            .order_by(OptionsSignal.signal_score.desc())
            .limit(3)
            .all()
        )
        top_signals = [_row_dict(r) for r in top_rows]

    result = {
        "vix":           vix,
        "market_pcr":    market_pcr,
        "buy_count":     buy_count,
        "sell_count":    sell_count,
        "unusual_count": unusual_count,
        "top_signals":   top_signals,
        "snapshot_at":   latest_snap.isoformat() if latest_snap else None,
    }
    _cache_overview["data"] = result
    _cache_overview["ts"]   = now
    return result
