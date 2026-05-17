"""
Broker API — CTBC (TW) and Moomoo (US) trading endpoints.

All routes require X-Internal-Secret header matching INTERNAL_API_SECRET.
Live-data routes accept ?market=TW (CTBC) or ?market=US (Moomoo).

Routes:
  GET  /api/broker/status          — status for both brokers
  GET  /api/broker/balance         — live account balance (?market=TW|US)
  GET  /api/broker/positions       — live open positions (?market=TW|US)
  GET  /api/broker/orders          — recent broker orders (?market=TW|US, ?days=7)
  POST /api/broker/order           — place order → record in trades table
  GET  /api/broker/trades          — trade history from DB (?limit&ticker&status&days&market)
  GET  /api/broker/trades/{ticker} — trade history for one ticker
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.auth import get_optional_user
from api.config import settings
from api.db import AccountSnapshot, Trade, User, get_db
from api.services.broker_service import (
    ctbc_call, ctbc_is_configured, ctbc_is_dry_run, get_ctbc, make_ctbc_for_user,
)
from api.services.moomoo_service import (
    moomoo_call, moomoo_is_configured, moomoo_is_simulate, get_moomoo,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["broker"])


# ── Auth guards ───────────────────────────────────────────────────────────────

def _require_internal(request: Request) -> None:
    key = request.headers.get("X-Internal-Secret", "")
    if key != settings.INTERNAL_API_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _require_user_or_internal(
    request: Request,
    user: Optional[User] = Depends(get_optional_user),
) -> Optional[User]:
    """Allow either an authenticated user (JWT) or an internal pipeline call (X-Internal-Secret)."""
    key = request.headers.get("X-Internal-Secret", "")
    if key == settings.INTERNAL_API_SECRET:
        return None   # internal caller — no user context
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


# ── Request / response models ──────────────────────────────────────────────────

class PlaceOrderRequest(BaseModel):
    ticker:        str
    side:          str           # "buy" | "sell"
    qty:           float
    limit_price:   float
    market:        str = "TW"   # "TW" → CTBC, "US" → Moomoo
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
    """Returns configuration status for both brokers — no browser/socket opened."""
    return {
        "brokers": [
            {
                "broker":     "CTBC",
                "market":     "TW",
                "configured": ctbc_is_configured(),
                "dry_run":    ctbc_is_dry_run(),
                "connected":  False,  # lazy connect — actual check on first data call
                "note":       "Taiwan stocks — Playwright browser automation",
            },
            {
                "broker":     "Moomoo",
                "market":     "US",
                "configured": moomoo_is_configured(),
                "simulate":   moomoo_is_simulate(),
                "connected":  False,
                "note":       "US stocks — requires Moomoo OpenD running locally",
            },
        ]
    }


# ── Helpers: route market to broker ──────────────────────────────────────────

def _assert_tw():
    if not ctbc_is_configured():
        raise HTTPException(503, "CTBC credentials not configured — set CTBC_ID + CTBC_PASSWORD in .env")

def _assert_us():
    if not moomoo_is_configured():
        raise HTTPException(
            503,
            "Moomoo not configured — set MOOMOO_PORT=11111 in .env and start Moomoo OpenD. "
            "Download from https://www.moomoo.com/openapi/"
        )


# ── GET /balance ──────────────────────────────────────────────────────────────

def _save_snapshot(db: Session, market: str, balance: dict) -> None:
    """Upsert a daily balance snapshot; silently ignores conflicts and errors."""
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        existing = (
            db.query(AccountSnapshot)
            .filter(AccountSnapshot.market == market, AccountSnapshot.snapshot_date == today)
            .first()
        )
        if not existing:
            db.add(AccountSnapshot(
                market         = market,
                snapshot_date  = today,
                cash           = balance.get("cash"),
                total_value    = balance.get("total_value"),
                unrealized_pnl = balance.get("unrealized_pnl"),
                currency       = balance.get("currency"),
            ))
            db.commit()
    except Exception as exc:
        logger.warning("account snapshot write failed: %s", exc)
        db.rollback()


@router.get("/balance")
async def broker_balance(
    market: str              = Query(default="TW", description="TW = CTBC, US = Moomoo"),
    user:   Optional[User]   = Depends(_require_user_or_internal),
    db:     Session          = Depends(get_db),
):
    if market.upper() == "US":
        _assert_us()
        try:
            client = get_moomoo()
            balance = await moomoo_call(client.get_balance)
            balance = balance or {"cash": 0, "total_value": 0, "unrealized_pnl": 0, "currency": "USD"}
            _save_snapshot(db, "US", balance)
            return balance
        except Exception as exc:
            logger.warning("moomoo balance error: %s", exc)
            raise HTTPException(503, f"Moomoo unavailable: {exc}")
    else:
        if user and (user.ctbc_id_enc or user.ctbc_pass_enc):
            # User has stored credentials — use them
            try:
                client = make_ctbc_for_user(user)
                balance = await ctbc_call(client.get_balance)
                balance = balance or {"cash": 0, "total_value": 0, "unrealized_pnl": 0, "currency": "TWD"}
                _save_snapshot(db, "TW", balance)
                return balance
            except Exception as exc:
                logger.warning("ctbc (user %s) balance error: %s", user.id, exc)
                raise HTTPException(503, f"CTBC unavailable: {exc}")
        _assert_tw()
        try:
            client = get_ctbc()
            balance = await ctbc_call(client.get_balance)
            balance = balance or {"cash": 0, "total_value": 0, "unrealized_pnl": 0, "currency": "TWD"}
            _save_snapshot(db, "TW", balance)
            return balance
        except Exception as exc:
            logger.warning("ctbc balance error: %s", exc)
            raise HTTPException(503, f"CTBC unavailable: {exc}")


# ── GET /positions ────────────────────────────────────────────────────────────

@router.get("/positions")
async def broker_positions(
    market: str            = Query(default="TW", description="TW = CTBC, US = Moomoo"),
    user:   Optional[User] = Depends(_require_user_or_internal),
):
    if market.upper() == "US":
        _assert_us()
        try:
            client = get_moomoo()
            df = await moomoo_call(client.get_positions)
            return [] if df is None or df.empty else df.to_dict(orient="records")
        except Exception as exc:
            logger.warning("moomoo positions error: %s", exc)
            raise HTTPException(503, f"Moomoo unavailable: {exc}")
    else:
        if user and (user.ctbc_id_enc or user.ctbc_pass_enc):
            try:
                client = make_ctbc_for_user(user)
                df = await ctbc_call(client.get_positions)
                return [] if df is None or df.empty else df.to_dict(orient="records")
            except Exception as exc:
                logger.warning("ctbc (user %s) positions error: %s", user.id, exc)
                raise HTTPException(503, f"CTBC unavailable: {exc}")
        _assert_tw()
        try:
            client = get_ctbc()
            df = await ctbc_call(client.get_positions)
            return [] if df is None or df.empty else df.to_dict(orient="records")
        except Exception as exc:
            logger.warning("ctbc positions error: %s", exc)
            raise HTTPException(503, f"CTBC unavailable: {exc}")


# ── GET /orders ───────────────────────────────────────────────────────────────

@router.get("/orders")
async def broker_orders(
    market: str            = Query(default="TW", description="TW = CTBC, US = Moomoo"),
    days:   int            = Query(default=7, ge=1, le=90),
    user:   Optional[User] = Depends(_require_user_or_internal),
):
    if market.upper() == "US":
        _assert_us()
        try:
            client = get_moomoo()
            df = await moomoo_call(client.get_orders, days)
            return [] if df is None or df.empty else df.to_dict(orient="records")
        except Exception as exc:
            logger.warning("moomoo orders error: %s", exc)
            raise HTTPException(503, f"Moomoo unavailable: {exc}")
    else:
        if user and (user.ctbc_id_enc or user.ctbc_pass_enc):
            try:
                client = make_ctbc_for_user(user)
                df = await ctbc_call(client.get_orders, days)
                return [] if df is None or df.empty else df.to_dict(orient="records")
            except Exception as exc:
                logger.warning("ctbc (user %s) orders error: %s", user.id, exc)
                raise HTTPException(503, f"CTBC unavailable: {exc}")
        _assert_tw()
        try:
            client = get_ctbc()
            df = await ctbc_call(client.get_orders, days)
            return [] if df is None or df.empty else df.to_dict(orient="records")
        except Exception as exc:
            logger.warning("ctbc orders error: %s", exc)
            raise HTTPException(503, f"CTBC unavailable: {exc}")


# ── POST /order ───────────────────────────────────────────────────────────────

@router.post("/order")
async def broker_place_order(
    body: PlaceOrderRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_internal),
):
    side = body.side.lower()
    if side not in ("buy", "sell"):
        raise HTTPException(400, "side must be 'buy' or 'sell'")
    if body.qty <= 0:
        raise HTTPException(400, "qty must be positive")
    if body.limit_price <= 0:
        raise HTTPException(400, "limit_price must be positive")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    market = body.market.upper()

    if market == "US":
        _assert_us()
        broker_name = "Moomoo"
        try:
            client = get_moomoo()
            result = await moomoo_call(
                client.place_order, body.ticker, side.upper(),
                body.qty, "LIMIT", body.limit_price,
            )
        except Exception as exc:
            logger.warning("moomoo place_order failed: %s", exc)
            raise HTTPException(503, f"Moomoo unavailable: {exc}")
    else:
        _assert_tw()
        broker_name = "CTBC"
        try:
            client = get_ctbc()
            result = await ctbc_call(
                client.place_order, body.ticker, side.upper(),
                body.qty, "LIMIT", body.limit_price,
            )
        except Exception as exc:
            logger.warning("ctbc place_order failed: %s", exc)
            raise HTTPException(503, f"CTBC unavailable: {exc}")

    success  = result.get("success", False)
    order_id = result.get("order_id", "") or None
    is_dry   = not success or (order_id and "DRY" in str(order_id))

    trade = Trade(
        broker          = broker_name,
        ticker          = body.ticker.upper(),
        market          = market,
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
    market: Optional[str]  = Query(default=None, description="TW or US"),
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
    if market:
        q = q.filter(Trade.market == market.upper())
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
        "ticker": ticker.upper(),
        "count":  len(rows),
        "trades": [TradeOut.from_orm(r) for r in rows],
    }


# ── GET /asset-history ────────────────────────────────────────────────────────

@router.get("/asset-history")
def broker_asset_history(
    market: str     = Query(default="TW", description="TW = CTBC, US = Moomoo"),
    days:   int     = Query(default=90, ge=1, le=365),
    db:     Session = Depends(get_db),
    _:      None    = Depends(_require_internal),
):
    """Return daily balance snapshots (builds passively as user opens the platform)."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = (
        db.query(AccountSnapshot)
        .filter(AccountSnapshot.market == market.upper(), AccountSnapshot.snapshot_date >= since)
        .order_by(AccountSnapshot.snapshot_date.asc())
        .all()
    )
    return [
        {
            "date":          r.snapshot_date,
            "total_value":   r.total_value,
            "cash":          r.cash,
            "unrealized_pnl": r.unrealized_pnl,
            "currency":      r.currency,
        }
        for r in rows
    ]


# ── GET /options-chain ────────────────────────────────────────────────────────

@router.get("/options-chain")
async def broker_options_chain(
    ticker: str            = Query(...,      description="US stock ticker e.g. AAPL"),
    expiry: Optional[str]  = Query(default=None, description="YYYY-MM-DD; default=nearest expiry"),
    _:      None           = Depends(_require_internal),
):
    """Fetch Moomoo options chain for a US stock via OpenQuoteContext."""
    _assert_us()
    try:
        client = get_moomoo()
        contracts = await moomoo_call(client.get_options_chain, ticker, expiry)
        return {"ticker": ticker.upper(), "expiry": expiry, "contracts": contracts or []}
    except Exception as exc:
        logger.warning("options-chain error for %s: %s", ticker, exc)
        raise HTTPException(503, f"Moomoo unavailable: {exc}")
