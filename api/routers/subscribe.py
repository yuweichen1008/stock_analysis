"""
Subscription management — Telegram-based notifications for web / non-app visitors.

Web flow:
  1. Visitor opens GET /subscribe  →  sees HTML subscription page
  2. They enter their Telegram chat ID + click Subscribe
  3. POST /api/subscribe  →  sends a confirmation Telegram DM
  4. On success: saved to subscribers table, gets daily Oracle push
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests as _requests
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from api.db import Subscriber, get_db

router = APIRouter(tags=["subscribe"])


# ── Telegram helper ───────────────────────────────────────────────────────────

def _tg_send(chat_id: str, text: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return False
    try:
        r = _requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=8,
        )
        return r.ok
    except Exception:
        return False


# ── Schemas ───────────────────────────────────────────────────────────────────

class SubscribeBody(BaseModel):
    telegram_id: str
    label:       str | None = None


# ── HTML subscribe page ───────────────────────────────────────────────────────

_SUBSCRIBE_HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Oracle 訂閱通知</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{background:#0d0d14;color:#fff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
         display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;padding:24px}
    .card{background:#1a1a2e;border:1px solid #2e2e50;border-radius:20px;padding:36px;width:100%;max-width:460px}
    h1{font-size:2rem;font-weight:800;margin-bottom:6px}
    .sub{color:#8888aa;font-size:.9rem;margin-bottom:28px}
    label{display:block;font-size:.8rem;color:#8888aa;margin-bottom:6px;letter-spacing:.05em;text-transform:uppercase}
    input{width:100%;background:#252540;border:1px solid #2e2e50;border-radius:10px;color:#fff;font-size:1rem;
          padding:12px 16px;outline:none;transition:.2s}
    input:focus{border-color:#448aff}
    .hint{font-size:.78rem;color:#555570;margin-top:8px;margin-bottom:24px;line-height:1.5}
    .hint a{color:#448aff;text-decoration:none}
    button{width:100%;background:#448aff;border:none;border-radius:10px;color:#fff;cursor:pointer;
           font-size:1rem;font-weight:700;padding:14px;transition:.2s}
    button:hover{background:#5c9fff}
    button:disabled{opacity:.5;cursor:not-allowed}
    .msg{margin-top:20px;padding:14px 16px;border-radius:10px;font-size:.9rem;display:none}
    .msg.ok{background:#004d26;border:1px solid #00e676;color:#00e676}
    .msg.err{background:#4d0000;border:1px solid #ff5252;color:#ff5252}
    .channels{display:flex;gap:12px;margin-bottom:28px}
    .ch{flex:1;background:#252540;border:1px solid #2e2e50;border-radius:12px;padding:14px;text-align:center;cursor:pointer;transition:.2s}
    .ch.active{border-color:#448aff;background:#1a2744}
    .ch-icon{font-size:1.5rem}
    .ch-name{font-size:.8rem;color:#8888aa;margin-top:4px}
    .divider{text-align:center;color:#555570;font-size:.8rem;margin:20px 0;position:relative}
    .divider::before,.divider::after{content:'';position:absolute;top:50%;width:42%;height:1px;background:#2e2e50}
    .divider::before{left:0}.divider::after{right:0}
    .unsub-link{text-align:center;margin-top:16px;font-size:.8rem;color:#555570}
    .unsub-link a{color:#8888aa;text-decoration:none}
  </style>
</head>
<body>
  <div class="card">
    <h1>🔮 Oracle</h1>
    <p class="sub">訂閱 TAIEX 大盤多空每日通知</p>

    <p style="font-size:.85rem;color:#8888aa;line-height:1.6;margin-bottom:24px">
      每個交易日 <strong style="color:#fff">08:00</strong> 送出當日預測，<strong style="color:#fff">14:05</strong> 結算通知。<br>
      透過 Telegram 私訊接收，完全免費。
    </p>

    <label for="tid">你的 Telegram Chat ID</label>
    <input id="tid" type="text" placeholder="例：123456789" autocomplete="off">
    <p class="hint">
      不知道你的 Chat ID？在 Telegram 搜尋
      <a href="https://t.me/userinfobot" target="_blank">@userinfobot</a>
      並傳送任意訊息，它會回覆你的 ID。
    </p>

    <label for="lbl">顯示名稱（選填）</label>
    <input id="lbl" type="text" placeholder="例：Sami" style="margin-bottom:24px" autocomplete="off">

    <button id="btn" onclick="doSubscribe()">📬 立即訂閱</button>

    <div id="msg" class="msg"></div>

    <div class="unsub-link">
      已訂閱？<a href="#" onclick="doUnsubscribe();return false">取消訂閱</a>
    </div>
  </div>

  <script>
    async function doSubscribe() {
      const tid = document.getElementById('tid').value.trim();
      const lbl = document.getElementById('lbl').value.trim();
      if (!tid) { showMsg('請輸入你的 Telegram Chat ID', false); return; }
      const btn = document.getElementById('btn');
      btn.disabled = true; btn.textContent = '訂閱中…';
      try {
        const r = await fetch('/api/subscribe', {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({telegram_id: tid, label: lbl || null})
        });
        const d = await r.json();
        if (r.ok) {
          showMsg('✅ 訂閱成功！請查看你的 Telegram — 已傳送確認訊息。', true);
        } else {
          showMsg('❌ ' + (d.detail || '訂閱失敗，請確認 Chat ID 是否正確'), false);
        }
      } catch(e) {
        showMsg('❌ 網路錯誤，請稍後再試', false);
      } finally {
        btn.disabled = false; btn.textContent = '📬 立即訂閱';
      }
    }

    async function doUnsubscribe() {
      const tid = document.getElementById('tid').value.trim();
      if (!tid) { showMsg('請先輸入你的 Telegram Chat ID', false); return; }
      const r = await fetch('/api/subscribe/' + encodeURIComponent(tid), {method:'DELETE'});
      const d = await r.json();
      showMsg(r.ok ? '已取消訂閱。' : '❌ 找不到此 Chat ID。', r.ok);
    }

    function showMsg(text, ok) {
      const m = document.getElementById('msg');
      m.textContent = text;
      m.className = 'msg ' + (ok ? 'ok' : 'err');
      m.style.display = 'block';
    }
  </script>
</body>
</html>"""


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/subscribe", response_class=HTMLResponse, include_in_schema=False)
def subscribe_page():
    """HTML subscription page for web visitors."""
    return _SUBSCRIBE_HTML


@router.post("/api/subscribe")
def subscribe(body: SubscribeBody, db: Session = Depends(get_db)):
    """Subscribe a Telegram chat ID for Oracle daily notifications."""
    tid = body.telegram_id.strip()
    if not tid:
        raise HTTPException(400, "telegram_id is required")

    existing = db.query(Subscriber).filter(Subscriber.telegram_id == tid).first()
    if existing:
        if existing.active:
            raise HTTPException(409, "Already subscribed")
        existing.active = True
        existing.label  = body.label or existing.label
        db.commit()
        _tg_send(tid, "🔮 *Oracle* — 你已重新訂閱每日 TAIEX 多空通知！")
        return {"ok": True, "status": "reactivated"}

    # Send confirmation DM — if it fails, the chat ID is likely wrong
    ok = _tg_send(
        tid,
        "🔮 *Oracle* 訂閱成功！\n\n"
        "每個交易日你將收到：\n"
        "• 08:00  今日多空預測\n"
        "• 14:05  結算 + 累計積分\n\n"
        "輸入 /unsubscribe 或至 [訂閱頁面] 隨時取消。",
    )
    if not ok:
        raise HTTPException(400, "無法傳送確認訊息 — 請確認 Chat ID 是否正確，以及是否已開啟與 Bot 的對話")

    sub = Subscriber(telegram_id=tid, label=body.label)
    db.add(sub)
    db.commit()
    return {"ok": True, "status": "subscribed"}


@router.delete("/api/subscribe/{telegram_id}")
def unsubscribe(telegram_id: str, db: Session = Depends(get_db)):
    """Unsubscribe a Telegram chat ID."""
    sub = db.query(Subscriber).filter(Subscriber.telegram_id == telegram_id).first()
    if not sub or not sub.active:
        raise HTTPException(404, "Subscription not found")
    sub.active = False
    db.commit()
    _tg_send(telegram_id, "🔕 已取消 Oracle 訂閱。如需重新訂閱，請至訂閱頁面。")
    return {"ok": True}


@router.get("/api/subscribe/list")
def list_subscribers(db: Session = Depends(get_db)):
    """List all active Telegram subscribers."""
    subs = db.query(Subscriber).filter(Subscriber.active == True).all()
    return [
        {"id": s.id, "telegram_id": s.telegram_id, "label": s.label, "since": s.subscribed_at}
        for s in subs
    ]
