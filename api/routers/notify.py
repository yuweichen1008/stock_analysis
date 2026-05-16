"""
Push notification endpoints — Expo Push token registration + broadcast.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import os

from api.auth import require_internal
from api.db import User, get_db
from api.push_service import send_push
from tws.index_tracker import _load_history, oracle_stats

router = APIRouter(prefix="/api/notify", tags=["notify"])


def _tg_send_raw(chat_id: str, text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return
    try:
        import urllib.request, json as _json
        payload = _json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=8)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Telegram send failed for %s: %s", chat_id, exc)


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

    elif body.type == "market_insights":
        from api.db import Subscriber, OptionsSignal, WeeklySignal
        from datetime import date
        from sqlalchemy import func as sqlfunc

        now_utc = datetime.now(timezone.utc)  # type: ignore[attr-defined]
        subs = db.query(Subscriber).filter(Subscriber.active == True).all()  # noqa: E712
        if not subs:
            return {"ok": False, "reason": "no active subscribers"}

        # ── options signals summary ──
        latest_snap = db.query(sqlfunc.max(OptionsSignal.snapshot_at)).scalar()
        buy_count = sell_count = unusual_count = 0
        top_opts: list[str] = []
        if latest_snap:
            rows = (
                db.query(OptionsSignal)
                .filter(
                    OptionsSignal.snapshot_at == latest_snap,
                    OptionsSignal.signal_type.isnot(None),
                )
                .order_by(OptionsSignal.signal_score.desc())
                .limit(5)
                .all()
            )
            for r in rows:
                if r.signal_type == "buy_signal":    buy_count += 1
                elif r.signal_type == "sell_signal": sell_count += 1
                else:                                unusual_count += 1
                rsi_s = f"RSI={r.rsi_14:.0f}" if r.rsi_14 is not None else ""
                pcr_s = f"PCR={r.pcr:.2f}"    if r.pcr   is not None else ""
                icon  = "🟢" if r.signal_type == "buy_signal" else ("🔴" if r.signal_type == "sell_signal" else "⚡")
                top_opts.append(f"{icon} {r.ticker}  {rsi_s} {pcr_s}".strip())

        # ── weekly signals summary ──
        this_week = db.query(WeeklySignal).filter(
            WeeklySignal.signal_type.isnot(None)
        ).order_by(WeeklySignal.created_at.desc()).limit(5).all()
        top_weekly: list[str] = []
        for r in this_week:
            icon = "📈" if r.signal_type == "buy" else "📉"
            top_weekly.append(f"{icon} {r.ticker}  {r.return_pct:+.1f}%")

        date_str = now_utc.strftime("%Y-%m-%d")

        def _build_free_msg() -> str:
            lines = [f"📊 *LokiStock 市場速報* — {date_str}\n"]
            if top_opts:
                lines.append("*選擇權訊號*")
                lines.extend(top_opts[:3])
            if top_weekly:
                lines.append("\n*週訊號*")
                lines.extend(top_weekly[:3])
            lines.append(
                f"\n訊號統計：買入 {buy_count} | 賣出 {sell_count} | 異常活躍 {unusual_count}"
            )
            lines.append("\n🤖 _LokiStock Oracle · 僅供參考，非投資建議_")
            return "\n".join(lines)

        def _build_pro_msg(sub: Subscriber) -> str:
            base = _build_free_msg()
            note = getattr(sub, "editorial_note", None)
            editorial = (
                f"\n\n📝 *編輯評論*\n{note}"
                if note else
                "\n\n📝 *編輯評論*\n目前市場情緒中性，建議觀望，等待明確趨勢確認。VIX 維持低檔，PCR 接近均值，短期方向不明。"
            )
            return base + editorial + "\n\n🌟 _Pro 會員專屬 · 感謝支持 LokiStock_"

        sent_free = sent_pro = 0
        for sub in subs:
            tier = getattr(sub, "tier", "free")
            tier_exp = getattr(sub, "tier_expires_at", None)
            is_pro = (tier == "pro") and (tier_exp is None or tier_exp.replace(tzinfo=timezone.utc) > now_utc)  # type: ignore[attr-defined]
            msg = _build_pro_msg(sub) if is_pro else _build_free_msg()
            _tg_send_raw(sub.telegram_id, msg)
            if is_pro: sent_pro += 1
            else:      sent_free += 1

        result = {"ok": True, "sent_free": sent_free, "sent_pro": sent_pro}

    else:
        raise HTTPException(400, "type must be 'morning', 'result', 'options_signals', or 'market_insights'")

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
