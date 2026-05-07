"""
Broker API — CTBC TWS trading endpoints.

All routes require X-Internal-Secret header matching INTERNAL_API_SECRET.
The CTBC Playwright client runs in a thread pool (never blocks the event loop).

Routes:
  GET  /api/broker/status          — connection status + dry-run flag
  GET  /api/broker/balance         — live account balance from CTBC
  GET  /api/broker/positions       — live open positions from CTBC
  GET  /api/broker/orders          — recent orders from CTBC (?days=7)
  POST /api/broker/order           — place order → record in trades table
  GET  /api/broker/trades          — trade history from DB (?limit&ticker&status&days)
  GET  /api/broker/trades/{ticker} — trade history for one ticker
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.config import settings
from api.db import Trade, get_db
from api.services.broker_service import (
    ctbc_call, ctbc_is_configured, ctbc_is_dry_run, get_ctbc,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["broker"])


# ── Auth guard ────────────────────────────────────────────────────────────────

def _require_internal(request: Request) -> None:
    key = request.headers.get("X-Internal-Secret", "")
    if key != settings.INTERNAL_API_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")


# ── Request / response models ──────────────────────────────────────────────────

class PlaceOrderRequest(BaseModel):
    ticker:        str
    side:          str          # "buy" | "sell"
    qty:           float
    limit_price:   float
    signal_source: Optional[str] = "manual"


class TradeOut(BaseModel):
    id:              int
    broker:          str
    ticker:          str
    market:          str
    side:            str
    qty:             float
    order_type:      Optional[str]
    limit_price:     Optional[float]
    broker_order_id: Optional[str]
    status:          Optional[str]
    filled_qty:      Optional[float]
    filled_price:    Optional[float]
    commission:      Optional[float]
    realized_pnl:    Optional[float]
    signal_source:   Optional[str]
    executed_at:     Optional[str]
    created_at:      Optional[str]

    @classmethod
    def from_orm(cls, t: Trade) -> "TradeOut":
        return cls(
            id              = t.id,
            broker          = t.broker,
            ticker          = t.ticker,
            market          = t.market,
            side            = t.side,
            qty             = t.qty,
            order_type      = t.order_type,
            limit_price     = t.limit_price,
            broker_order_id = t.broker_order_id,
            status          = t.status,
            filled_qty      = t.filled_qty,
            filled_price    = t.filled_price,
            commission      = t.commission,
            realized_pnl    = t.realized_pnl,
            signal_source   = t.signal_source,
            executed_at     = t.executed_at.isoformat() if t.executed_at else None,
            created_at      = t.created_at.isoformat() if t.created_at else None,
        )


# ── GET /status ───────────────────────────────────────────────────────────────

@router.get("/status")
def broker_status(_: None = Depends(_require_internal)):
    """Returns connection configuration — does NOT open a browser session."""
    return {
        "broker":      "CTBC",
        "configured":  ctbc_is_configured(),
        "dry_run":     ctbc_is_dry_run(),
        "connected":   False,   # lightweight — actual connect is lazy on first data call
    }


# ── GET /balance ──────────────────────────────────────────────────────────────

@router.get("/balance")
async def broker_balance(_: None = Depends(_require_internal)):
    if not ctbc_is_configured():
        raise HTTPException(503, "CTBC credentials not configured")
    try:
        client = get_ctbc()
        balance = await ctbc_call(client.get_balance)
        return balance or {"cash": 0, "total_value": 0, "unrealized_pnl": 0, "currency": "TWD"}
    except Exception as exc:
        logger.warning("broker_balance error: %s", exc)
        raise HTTPException(503, f"CTBC unavailable: {exc}")


# ── GET /positions ────────────────────────────────────────────────────────────

@router.get("/positions")
async def broker_positions(_: None = Depends(_require_internal)):
    if not ctbc_is_configured():
        raise HTTPException(503, "CTBC credentials not configured")
    try:
        client = get_ctbc()
        df = await ctbc_call(client.get_positions)
        if df is None or df.empty:
            return []
        return df.to_dict(orient="records")
    except Exception as exc:
        logger.warning("broker_positions error: %s", exc)
        raise HTTPException(503, f"CTBC unavailable: {exc}")


# ── GET /orders ───────────────────────────────────────────────────────────────

@router.get("/orders")
async def broker_orders(
    days: int = Query(default=7, ge=1, le=90),
    _: None = Depends(_require_internal),
):
    if not ctbc_is_configured():
        raise HTTPException(503, "CTBC credentials not configured")
    try:
        client = get_ctbc()
        df = await ctbc_call(client.get_orders, days)
        if df is None or df.empty:
            return []
        return df.to_dict(orient="records")
    except Exception as exc:
        logger.warning("broker_orders error: %s", exc)
        raise HTTPException(503, f"CTBC unavailable: {exc}")


# ── POST /order ───────────────────────────────────────────────────────────────

@router.post("/order")
async def broker_place_order(
    body: PlaceOrderRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_internal),
):
    if not ctbc_is_configured():
        raise HTTPException(503, "CTBC credentials not configured")

    side = body.side.lower()
    if side not in ("buy", "sell"):
        raise HTTPException(400, "side must be 'buy' or 'sell'")
    if body.qty <= 0:
        raise HTTPException(400, "qty must be positive")
    if body.limit_price <= 0:
        raise HTTPException(400, "limit_price must be positive")

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    try:
        client = get_ctbc()
        result = await ctbc_call(
            client.place_order,
            body.ticker,
            side.upper(),
            body.qty,
            "LIMIT",
            body.limit_price,
        )
    except Exception as exc:
        logger.warning("broker_place_order CTBC call failed: %s", exc)
        raise HTTPException(503, f"CTBC unavailable: {exc}")

    # Determine status from CTBC result
    success = result.get("success", False)
    order_id = result.get("order_id", "") or None
    is_dry = "DRY" in (order_id or "")

    trade = Trade(
        broker          = "CTBC",
        ticker          = body.ticker.upper(),
        market          = "TW",
        side            = side,
        qty             = body.qty,
        order_type      = "LIMIT",
        limit_price     = body.limit_price,
        broker_order_id = order_id if not is_dry else None,
        status          = "pending" if success else "rejected",
        signal_source   = body.signal_source or "manual",
        executed_at     = now if success else None,
        created_at      = now,
    )
    db.add(trade)
    db.commit()
    db.refresh(trade)

    return {
        "trade":   TradeOut.from_orm(trade),
        "message": result.get("message", ""),
        "dry_run": is_dry,
    }


# ── GET /trades ───────────────────────────────────────────────────────────────

@router.get("/trades")
def broker_trades(
    limit:  int            = Query(default=50, ge=1, le=500),
    ticker: Optional[str]  = Query(default=None),
    status: Optional[str]  = Query(default=None),
    days:   int            = Query(default=90, ge=1, le=730),
    db:     Session        = Depends(get_db),
    _:      None           = Depends(_require_internal),
):
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    q = db.query(Trade).filter(Trade.created_at >= since)
    if ticker:
        q = q.filter(Trade.ticker == ticker.upper())
    if status:
        q = q.filter(Trade.status == status)
    rows = q.order_by(Trade.created_at.desc()).limit(limit).all()
    return [TradeOut.from_orm(r) for r in rows]


# ── GET /trades/{ticker} ──────────────────────────────────────────────────────

@router.get("/trades/{ticker}")
def broker_ticker_trades(
    ticker: str,
    limit:  int     = Query(default=50, ge=1, le=200),
    db:     Session = Depends(get_db),
    _:      None    = Depends(_require_internal),
):
    rows = (
        db.query(Trade)
        .filter(Trade.ticker == ticker.upper())
        .order_by(Trade.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "ticker":  ticker.upper(),
        "count":   len(rows),
        "trades":  [TradeOut.from_orm(r) for r in rows],
    }
