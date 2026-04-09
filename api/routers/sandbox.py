"""
Sandbox betting game endpoints.
Users bet virtual coins on daily Bull/Bear Oracle predictions.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from api.db import Bet, User, get_db
from tws.index_tracker import _load_history

router = APIRouter(prefix="/api/sandbox", tags=["sandbox"])

STARTING_COINS = 10_000
MIN_BET        = 100
MAX_BET        = 2_000
COIN_FLOOR     = 100      # can never drop below this


# ── Helper ────────────────────────────────────────────────────────────────────

def _today_tst() -> str:
    return datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d")


def _market_locked() -> bool:
    """True after 09:00 TST — no new bets allowed."""
    now = datetime.now(ZoneInfo("Asia/Taipei"))
    return now.weekday() < 5 and now.hour >= 9


# ── Schemas ───────────────────────────────────────────────────────────────────

class RegisterBody(BaseModel):
    device_id: str
    nickname:  Optional[str] = None


class BetBody(BaseModel):
    device_id:  str
    direction:  str        # "Bull" or "Bear"
    bet_amount: int = Field(ge=MIN_BET, le=MAX_BET)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register")
def register(body: RegisterBody, db: Session = Depends(get_db)):
    """Register a new device. Returns existing user if already registered."""
    user = db.get(User, body.device_id)
    if user:
        return {"device_id": user.device_id, "coins": user.coins, "created": False}

    user = User(
        device_id=body.device_id,
        coins=STARTING_COINS,
        nickname=body.nickname,
    )
    db.add(user)
    db.commit()
    return {"device_id": user.device_id, "coins": STARTING_COINS, "created": True}


@router.get("/me/{device_id}")
def get_me(device_id: str, db: Session = Depends(get_db)):
    """User balance, today's bet status, and aggregate stats."""
    user = db.get(User, device_id)
    if not user:
        raise HTTPException(404, "Device not registered. Call /register first.")

    today = _today_tst()
    today_bet = (
        db.query(Bet)
        .filter(Bet.device_id == device_id, Bet.date == today)
        .first()
    )
    all_bets = db.query(Bet).filter(Bet.device_id == device_id).all()
    settled  = [b for b in all_bets if b.status == "settled"]
    wins     = sum(1 for b in settled if b.is_correct)

    return {
        "device_id":   device_id,
        "nickname":    user.nickname,
        "coins":       user.coins,
        "total_bets":  len(all_bets),
        "wins":        wins,
        "losses":      len(settled) - wins,
        "win_rate_pct": round(wins / len(settled) * 100, 1) if settled else 0.0,
        "today_bet":   {
            "direction":  today_bet.direction,
            "amount":     today_bet.bet_amount,
            "status":     today_bet.status,
            "payout":     today_bet.payout,
        } if today_bet else None,
    }


@router.post("/bet")
def place_bet(body: BetBody, db: Session = Depends(get_db)):
    """Place today's Bull/Bear bet. One bet per day, locked after 09:00 TST."""
    if body.direction not in ("Bull", "Bear"):
        raise HTTPException(400, "direction must be 'Bull' or 'Bear'")

    user = db.get(User, body.device_id)
    if not user:
        raise HTTPException(404, "Device not registered.")

    today = _today_tst()

    # Check for duplicate bet
    existing = (
        db.query(Bet)
        .filter(Bet.device_id == body.device_id, Bet.date == today)
        .first()
    )
    if existing:
        raise HTTPException(409, f"Already placed a bet today: {existing.direction} {existing.bet_amount} coins")

    # Market lock check
    if _market_locked():
        raise HTTPException(423, "Market is open — bets locked after 09:00 TST")

    # Sufficient coins check
    if user.coins < body.bet_amount:
        raise HTTPException(400, f"Insufficient coins: have {user.coins}, need {body.bet_amount}")
    if user.coins - body.bet_amount < COIN_FLOOR:
        max_allowed = max(MIN_BET, user.coins - COIN_FLOOR)
        raise HTTPException(400, f"Cannot go below {COIN_FLOOR} coins. Max bet: {max_allowed}")

    bet = Bet(
        device_id=body.device_id,
        date=today,
        direction=body.direction,
        bet_amount=body.bet_amount,
    )
    db.add(bet)
    db.commit()
    db.refresh(bet)

    return {
        "bet_id":          bet.id,
        "direction":       bet.direction,
        "amount":          bet.bet_amount,
        "coins_remaining": user.coins,  # coins unchanged until settlement
        "status":          "pending",
        "potential_win":   bet.bet_amount,
        "potential_loss":  bet.bet_amount // 2,
    }


@router.post("/settle")
def settle_bets(db: Session = Depends(get_db)):
    """
    Internal endpoint: called by pipeline after Oracle resolution.
    Settles all pending bets for today using the Oracle outcome.
    """
    today = _today_tst()
    history = _load_history(str(BASE_DIR))
    if history.empty:
        return {"settled": 0, "error": "no oracle history"}

    today_oracle = history[(history["date"] == today) & (history["status"] == "resolved")]
    if today_oracle.empty:
        return {"settled": 0, "error": "oracle not resolved yet"}

    oracle_direction = today_oracle.iloc[-1]["direction"]
    oracle_correct   = str(today_oracle.iloc[-1].get("is_correct", "")).lower() in ("true", "1")

    # The "correct" direction for the oracle
    correct_direction = oracle_direction  # oracle predicted this and was right
    # But user wins if their bet matches the ACTUAL market direction
    # actual = oracle_direction if oracle_correct, else the opposite
    if oracle_correct:
        actual_direction = oracle_direction
    else:
        actual_direction = "Bear" if oracle_direction == "Bull" else "Bull"

    pending = (
        db.query(Bet)
        .filter(Bet.date == today, Bet.status == "pending")
        .all()
    )

    settled_count = 0
    for bet in pending:
        user = db.get(User, bet.device_id)
        if not user:
            continue

        bet.is_correct = (bet.direction == actual_direction)
        if bet.is_correct:
            payout        = bet.bet_amount
            user.coins   += payout
        else:
            payout        = -(bet.bet_amount // 2)
            user.coins    = max(COIN_FLOOR, user.coins + payout)

        bet.payout = payout
        bet.status = "settled"
        settled_count += 1

    db.commit()
    return {
        "settled":          settled_count,
        "actual_direction": actual_direction,
        "oracle_direction": oracle_direction,
        "oracle_correct":   oracle_correct,
    }


@router.get("/history/{device_id}")
def get_bet_history(device_id: str, limit: int = 30, db: Session = Depends(get_db)):
    """User's personal bet history, newest first."""
    user = db.get(User, device_id)
    if not user:
        raise HTTPException(404, "Device not registered.")

    bets = (
        db.query(Bet)
        .filter(Bet.device_id == device_id)
        .order_by(Bet.date.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "date":       b.date,
            "direction":  b.direction,
            "amount":     b.bet_amount,
            "is_correct": b.is_correct,
            "payout":     b.payout,
            "status":     b.status,
        }
        for b in bets
    ]


@router.get("/leaderboard")
def get_leaderboard(limit: int = 20, db: Session = Depends(get_db)):
    """Top players ranked by coins."""
    users = (
        db.query(User)
        .order_by(User.coins.desc())
        .limit(limit)
        .all()
    )
    result = []
    for rank, u in enumerate(users, start=1):
        settled = db.query(Bet).filter(
            Bet.device_id == u.device_id, Bet.status == "settled"
        ).all()
        wins = sum(1 for b in settled if b.is_correct)
        result.append({
            "rank":       rank,
            "device_id":  u.device_id,
            "nickname":   u.nickname or u.device_id[:8],
            "coins":      u.coins,
            "total_bets": len(settled),
            "wins":       wins,
            "win_rate":   round(wins / len(settled) * 100, 1) if settled else 0.0,
        })
    return result
