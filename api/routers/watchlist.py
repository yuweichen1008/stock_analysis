"""
Personal watchlist endpoints — all require JWT auth.

GET    /api/watchlist          → list saved tickers
POST   /api/watchlist          → add ticker
DELETE /api/watchlist/{ticker} → remove ticker  (?market=US)
GET    /api/watchlist/alerts   → today's signals matching saved tickers
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from api.auth import get_current_user
from api.db import User, Watchlist, get_db
from api.routers.signals import _load_csv

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class WatchlistAddBody(BaseModel):
    ticker: str
    market: str   # "TW" | "US"
    notes:  Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _item_dict(item: Watchlist) -> dict:
    return {
        "id":       item.id,
        "ticker":   item.ticker,
        "market":   item.market,
        "notes":    item.notes,
        "added_at": item.added_at.isoformat() if item.added_at else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/alerts")
def get_alerts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return today's signal rows for all tickers in the user's watchlist."""
    items = db.query(Watchlist).filter(Watchlist.user_id == current_user.id).all()
    if not items:
        return []

    saved = {(i.ticker.upper(), i.market.upper()) for i in items}

    tw_rows = _load_csv(BASE_DIR / "current_trending.csv")
    us_rows = _load_csv(BASE_DIR / "data_us" / "current_trending.csv")

    alerts = []
    for row in tw_rows:
        key = (str(row.get("ticker", "")).upper(), "TW")
        if key in saved:
            alerts.append({**row, "market": "TW", "alert": True})
    for row in us_rows:
        key = (str(row.get("ticker", "")).upper(), "US")
        if key in saved:
            alerts.append({**row, "market": "US", "alert": True})

    return alerts


@router.get("/")
def list_watchlist(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items = db.query(Watchlist).filter(Watchlist.user_id == current_user.id).all()
    return [_item_dict(i) for i in items]


@router.post("/")
def add_to_watchlist(
    body: WatchlistAddBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = Watchlist(
        user_id=current_user.id,
        ticker=body.ticker.upper(),
        market=body.market.upper(),
        notes=body.notes,
        added_at=datetime.now(timezone.utc),
    )
    db.add(item)
    try:
        db.commit()
        db.refresh(item)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"{body.ticker.upper()} already in watchlist")
    return _item_dict(item)


@router.delete("/{ticker}")
def remove_from_watchlist(
    ticker: str,
    market: str = "US",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = (
        db.query(Watchlist)
        .filter(
            Watchlist.user_id == current_user.id,
            Watchlist.ticker  == ticker.upper(),
            Watchlist.market  == market.upper(),
        )
        .first()
    )
    if not item:
        raise HTTPException(404, "Ticker not in watchlist")
    db.delete(item)
    db.commit()
    return {"ok": True, "ticker": ticker.upper(), "market": market.upper()}
