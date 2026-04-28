"""
Push notification endpoints — Expo Push token registration + broadcast.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from api.auth import require_internal
from api.db import User, get_db
from api.push_service import send_push
from tws.index_tracker import _load_history, oracle_stats

router = APIRouter(prefix="/api/notify", tags=["notify"])


class RegisterTokenBody(BaseModel):
    device_id:  str
    expo_token: str


class BroadcastBody(BaseModel):
    type: str   # "morning" | "result"


@router.post("/register")
def register_token(body: RegisterTokenBody, db: Session = Depends(get_db)):
    """Store an Expo push token for a device."""
    user = db.query(User).filter(User.device_id == body.device_id).first()
    if not user:
        raise HTTPException(404, "Device not registered. Call /sandbox/register first.")
    user.push_token = body.expo_token
    db.commit()
    return {"ok": True}


@router.post("/broadcast")
def broadcast(body: BroadcastBody, db: Session = Depends(get_db), _: None = Depends(require_internal)):
    """
    Internal endpoint called by master_run.py.
    type='morning' → send today's prediction to all users.
    type='result'  → send today's resolved result to all users.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d")
    history = _load_history(str(BASE_DIR))
    stats   = oracle_stats(str(BASE_DIR))

    if body.type == "morning":
        tokens = [u.push_token for u in db.query(User).all() if u.push_token]
        if history.empty:
            return {"ok": False, "reason": "no oracle data"}
        today_rows = history[history["date"] == today]
        if today_rows.empty:
            return {"ok": False, "reason": "no prediction for today"}
        row       = today_rows.iloc[-1]
        direction = row.get("direction", "?")
        conf      = float(row.get("confidence_pct") or 0)
        dir_label = "多方 BULL 🟢" if direction == "Bull" else "空方 BEAR 🔴"
        result    = send_push(
            tokens,
            title="🔮 Oracle 今日預測",
            body=f"{dir_label}  信心 {conf:.0f}%\n下注截止 09:00 TST",
            data={"type": "morning", "direction": direction, "date": today},
        )

    elif body.type == "result":
        if history.empty:
            return {"ok": False, "reason": "no oracle data"}
        resolved = history[(history["date"] == today) & (history["status"] == "resolved")]
        if resolved.empty:
            return {"ok": False, "reason": "oracle not resolved yet"}
        row        = resolved.iloc[-1]
        direction  = row.get("direction", "?")
        is_correct = str(row.get("is_correct", "")).lower() in ("true", "1")
        change_pts = float(row.get("taiex_change_pts") or 0)
        score_pts  = float(row.get("score_pts") or 0)
        outcome    = "✅ 命中" if is_correct else "❌ 未命中"
        streak     = stats.get("streak", 0)
        streak_txt = f"  🔥{streak}連勝" if is_correct and streak >= 2 else ""

        from api.db import Bet
        sent = 0
        for u in db.query(User).all():
            if not u.push_token:
                continue
            user_bet = (
                db.query(Bet)
                .filter(Bet.user_id == u.id, Bet.date == today)
                .first()
            )
            if user_bet and user_bet.status == "settled" and user_bet.payout is not None:
                payout = user_bet.payout
                coins  = u.coins
                bet_line = (
                    f"你贏了 {payout:+,} coins 💰 餘額: {coins:,}"
                    if payout >= 0
                    else f"輸了 {payout:,} coins 💰 餘額: {coins:,}"
                )
            else:
                bet_line = f"累計勝率 {stats.get('win_rate_pct', 0):.0f}%  ·  積分 {stats.get('cumulative_score', 0):+,.0f}"

            send_push(
                [u.push_token],
                title=f"📊 Oracle 結算 {outcome}",
                body=(
                    f"大盤 {change_pts:+.0f}pts  Oracle {int(score_pts):+d}pts{streak_txt}\n"
                    f"{bet_line}"
                ),
                data={"type": "result", "is_correct": is_correct, "date": today},
            )
            sent += 1
        result = {"ok": True, "sent": sent}

    elif body.type == "options_signals":
        from api.db import OptionsSignal
        from sqlalchemy import func as sqlfunc

        latest_snap = db.query(sqlfunc.max(OptionsSignal.snapshot_at)).scalar()
        if not latest_snap:
            return {"ok": False, "reason": "no options signals in DB"}

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
        if not top_rows:
            return {"ok": False, "reason": "no option signals in latest snapshot"}

        total_signals = (
            db.query(OptionsSignal)
            .filter(
                OptionsSignal.snapshot_at == latest_snap,
                OptionsSignal.signal_type.isnot(None),
            )
            .count()
        )

        lines: list[str] = []
        for r in top_rows:
            rsi_s = f"RSI={r.rsi_14:.0f}" if r.rsi_14 is not None else "RSI=—"
            pcr_s = f"PCR={r.pcr:.2f}" if r.pcr is not None else "PCR=—"
            lines.append(f"{r.ticker} {r.signal_type.replace('_',' ').upper()} | {rsi_s} {pcr_s}")

        remaining = total_signals - len(top_rows)
        body_text = "\n".join(lines)
        if remaining > 0:
            body_text += f"\n+{remaining} more signals"

        tokens = [u.push_token for u in db.query(User).all() if u.push_token]
        result = send_push(
            tokens,
            title="📊 Oracle Options Screener",
            body=body_text,
            data={
                "type":        "options_signals",
                "count":       total_signals,
                "snapshot_at": latest_snap.isoformat(),
            },
        )

    else:
        raise HTTPException(400, "type must be 'morning', 'result', or 'options_signals'")

    return result


@router.post("/test/{device_id}")
def test_push(device_id: str, db: Session = Depends(get_db)):
    """Send a test push notification to a specific device."""
    user = db.get(User, device_id)
    if not user or not user.push_token:
        raise HTTPException(404, "Device not found or no push token registered.")
    result = send_push(
        [user.push_token],
        title="🔮 Oracle 測試通知",
        body="推播通知設定成功！",
        data={"type": "test"},
    )
    return result
