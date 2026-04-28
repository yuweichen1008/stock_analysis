"""
Weekly contrarian signals — ±5% movers with PCR overlay.

Endpoints:
  GET /api/weekly/signals                     — latest week's signals
  GET /api/weekly/signals/{ticker}/history    — signal history for one ticker
"""
from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.db import WeeklySignal, get_db

router = APIRouter(prefix="/api/weekly", tags=["weekly"])

_cache: dict = {"data": None, "ts": 0.0, "week": ""}
_TTL = 3600.0  # 1 hour — signals only update once per week


def _row_dict(r: WeeklySignal) -> dict:
    return {
        "id":          r.id,
        "ticker":      r.ticker,
        "week_ending": r.week_ending,
        "return_pct":  r.return_pct,
        "signal_type": r.signal_type,
        "last_price":  r.last_price,
        "pcr":         r.pcr,
        "pcr_label":   r.pcr_label,
        "put_volume":  r.put_volume,
        "call_volume": r.call_volume,
        "executed":    r.executed,
        "order_side":  r.order_side,
        "order_qty":   r.order_qty,
    }


@router.get("/signals")
def get_weekly_signals(
    week:        str  = Query("", description="YYYY-MM-DD; defaults to latest available"),
    signal_only: bool = Query(True,  description="Only return ±5% signal tickers"),
    limit:       int  = Query(200,   ge=1, le=1000),
    offset:      int  = Query(0,     ge=0),
    db: Session = Depends(get_db),
):
    """Latest week's ±5% contrarian signals with PCR snapshot."""
    q = db.query(WeeklySignal)

    target_week = week
    if not target_week:
        latest = (
            db.query(WeeklySignal.week_ending)
            .order_by(WeeklySignal.week_ending.desc())
            .scalar()
        )
        target_week = latest or ""

    if target_week:
        q = q.filter(WeeklySignal.week_ending == target_week)

    if signal_only:
        q = q.filter(WeeklySignal.signal_type.isnot(None))

    rows = (
        q.order_by(WeeklySignal.return_pct.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "week_ending": target_week,
        "count":       len(rows),
        "signals":     [_row_dict(r) for r in rows],
    }


@router.get("/signals/{ticker}/history")
def get_signal_history(ticker: str, db: Session = Depends(get_db)):
    """All historical weekly signals for a single ticker (last 52 weeks)."""
    rows = (
        db.query(WeeklySignal)
        .filter(
            WeeklySignal.ticker == ticker.upper(),
            WeeklySignal.signal_type.isnot(None),
        )
        .order_by(WeeklySignal.week_ending.desc())
        .limit(52)
        .all()
    )
    return {"ticker": ticker.upper(), "history": [_row_dict(r) for r in rows]}
