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
from typing import Optional
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
    label:       Optional[str] = None


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
         min-height:100vh;padding:32px 16px}
    .page{max-width:520px;margin:0 auto}
    .logo{text-align:center;margin-bottom:32px}
    .logo h1{font-size:2.4rem;font-weight:800}
    .logo p{color:#8888aa;font-size:.95rem;margin-top:6px}
    .count-badge{display:inline-block;background:#1a2744;border:1px solid #448aff;
                 border-radius:20px;padding:4px 14px;font-size:.8rem;color:#448aff;
                 margin-top:10px;font-weight:600}
    /* Benefits grid */
    .benefits{display:grid;grid-template-columns:1fr;gap:12px;margin-bottom:28px}
    @media(min-width:640px){.benefits{grid-template-columns:repeat(3,1fr)}}
    .benefit{background:#1a1a2e;border:1px solid #2e2e50;border-radius:14px;
             padding:18px 14px;text-align:center}
    .benefit-icon{font-size:1.8rem;margin-bottom:8px}
    .benefit-title{font-size:.9rem;font-weight:700;margin-bottom:4px}
    .benefit-desc{font-size:.78rem;color:#8888aa;line-height:1.5}
    /* How-to box */
    .howto{background:#1a1a2e;border:1px solid #2e2e50;border-radius:14px;
           padding:20px;margin-bottom:24px}
    .howto h2{font-size:1rem;font-weight:700;margin-bottom:12px}
    .steps{list-style:none;display:flex;flex-direction:column;gap:8px}
    .steps li{font-size:.85rem;color:#8888aa;line-height:1.5}
    .steps li strong{color:#fff}
    .steps a{color:#448aff;text-decoration:none}
    .steps a:hover{text-decoration:underline}
    /* Form card */
    .card{background:#1a1a2e;border:1px solid #2e2e50;border-radius:20px;
          padding:28px;margin-bottom:24px}
    label{display:block;font-size:.75rem;color:#8888aa;margin-bottom:6px;
          letter-spacing:.06em;text-transform:uppercase}
    input{width:100%;background:#252540;border:1px solid #2e2e50;border-radius:10px;
          color:#fff;font-size:1rem;padding:12px 16px;outline:none;
          transition:.2s;margin-bottom:16px}
    input:focus{border-color:#448aff}
    .btn-primary{width:100%;background:#448aff;border:none;border-radius:10px;
                 color:#fff;cursor:pointer;font-size:1rem;font-weight:700;
                 padding:14px;transition:.2s;margin-bottom:12px}
    .btn-primary:hover{background:#5c9fff}
    .btn-primary:disabled{opacity:.5;cursor:not-allowed}
    .msg{padding:14px 16px;border-radius:10px;font-size:.9rem;display:none;margin-bottom:12px}
    .msg.ok{background:#004d26;border:1px solid #00e676;color:#00e676}
    .msg.err{background:#4d0000;border:1px solid #ff5252;color:#ff5252}
    .unsub-link{text-align:center;font-size:.82rem;color:#555570}
    .unsub-link a{color:#8888aa;text-decoration:none;cursor:pointer}
    .unsub-link a:hover{color:#fff}
    /* FAQ */
    .faq{margin-bottom:40px}
    .faq h2{font-size:1rem;font-weight:700;margin-bottom:12px}
    .faq-item{background:#1a1a2e;border:1px solid #2e2e50;border-radius:12px;
              margin-bottom:8px;overflow:hidden}
    .faq-q{width:100%;background:none;border:none;color:#fff;cursor:pointer;
           font-size:.9rem;font-weight:500;padding:14px 16px;text-align:left;
           display:flex;justify-content:space-between;align-items:center;transition:.15s}
    .faq-q:hover{background:#252540}
    .faq-a{padding:0 16px;max-height:0;overflow:hidden;
           font-size:.85rem;color:#8888aa;line-height:1.6;transition:max-height .25s ease,padding .25s}
    .faq-a.open{max-height:120px;padding:0 16px 14px}
  </style>
</head>
<body>
  <div class="page">
    <!-- Logo + count -->
    <div class="logo">
      <h1>🔮 Oracle</h1>
      <p>訂閱 TAIEX 大盤多空每日通知</p>
      <span class="count-badge">{{COUNT}} 人已訂閱</span>
    </div>

    <!-- Benefits -->
    <div class="benefits">
      <div class="benefit">
        <div class="benefit-icon">📊</div>
        <div class="benefit-title">每日多空預測</div>
        <div class="benefit-desc">每個交易日 08:00 送出今日大盤預測 + 信心指數</div>
      </div>
      <div class="benefit">
        <div class="benefit-icon">🎯</div>
        <div class="benefit-title">結算通知</div>
        <div class="benefit-desc">14:05 結算勝負並更新你的累計積分</div>
      </div>
      <div class="benefit">
        <div class="benefit-icon">🔔</div>
        <div class="benefit-title">AI 訊號股</div>
        <div class="benefit-desc">精選 AI 掃描強勢訊號股票 + 分析師評級</div>
      </div>
    </div>

    <!-- How to get Chat ID -->
    <div class="howto">
      <h2>如何取得你的 Chat ID？</h2>
      <ol class="steps">
        <li><strong>步驟 1</strong> — 打開 Telegram，搜尋
          <a href="https://t.me/userinfobot" target="_blank">@userinfobot</a></li>
        <li><strong>步驟 2</strong> — 傳送任意訊息（例如：/start）</li>
        <li><strong>步驟 3</strong> — Bot 會立即回覆你的 Chat ID（純數字）</li>
        <li><strong>步驟 4</strong> — 將此 ID 貼入下方欄位，點擊訂閱</li>
      </ol>
    </div>

    <!-- Subscription form -->
    <div class="card">
      <label for="tid">Telegram Chat ID</label>
      <input id="tid" type="text" placeholder="例：123456789" autocomplete="off">

      <label for="lbl">顯示名稱（選填）</label>
      <input id="lbl" type="text" placeholder="例：Sami" autocomplete="off">

      <div id="msg" class="msg"></div>

      <button id="btn" class="btn-primary" onclick="doSubscribe()">📬 立即訂閱</button>

      <div class="unsub-link">
        已訂閱？<a onclick="doUnsubscribe()">取消訂閱</a>
      </div>
    </div>

    <!-- FAQ -->
    <div class="faq">
      <h2>常見問題</h2>
      <div class="faq-item">
        <button class="faq-q" onclick="toggleFaq(this)">
          這是免費的嗎？ <span>▼</span>
        </button>
        <div class="faq-a">完全免費，無需綁定信用卡或訂閱方案。</div>
      </div>
      <div class="faq-item">
        <button class="faq-q" onclick="toggleFaq(this)">
          每天會收到幾則訊息？ <span>▼</span>
        </button>
        <div class="faq-a">每個交易日 2 則：08:00 多空預測 + 14:05 結算通知。週末及國定假日不發送。</div>
      </div>
      <div class="faq-item">
        <button class="faq-q" onclick="toggleFaq(this)">
          可以隨時取消嗎？ <span>▼</span>
        </button>
        <div class="faq-a">可以。在上方輸入你的 Chat ID 並點擊「取消訂閱」即可立即生效。</div>
      </div>
    </div>
  </div>

  <script>
    function toggleFaq(btn) {
      const a = btn.nextElementSibling;
      const arrow = btn.querySelector('span');
      const open = a.classList.toggle('open');
      arrow.textContent = open ? '▲' : '▼';
    }

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
      } catch {
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
def subscribe_page(db: Session = Depends(get_db)):
    """HTML subscription page for web visitors."""
    count = db.query(Subscriber).filter(Subscriber.active == True).count()
    return _SUBSCRIBE_HTML.replace("{{COUNT}}", str(count))


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
