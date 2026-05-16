"use client";

import { useState } from "react";
import Link from "next/link";
import { subscribeTelegram, unsubscribeTelegram } from "@/lib/api";

// ── Static content ────────────────────────────────────────────────────────────

const FREE_PERKS = [
  "每日 TAIEX 多空預測（08:00 TST）",
  "結算通知 + 累計積分（14:05 TST）",
  "每週選擇權訊號摘要",
  "台股 RSI 掃描通知",
  "Discord 社群討論區",
];

const PRO_PERKS = [
  "即時選擇權訊號（2× 每日）",
  "每日市場速報 + 編輯評論",
  "Option Snipe 自動觸發通知",
  "CTBC + Moomoo Broker 整合",
  "完整回測報告 PDF",
  "優先客服 + 私人頻道",
];

const NOTIFICATION_PREVIEW = [
  {
    tier: "free",
    label: "免費會員",
    color: "#448aff",
    messages: [
      { time: "08:00", icon: "🔮", text: "Oracle 今日預測：多方 BULL 🟢  信心 74%\n下注截止 09:00 TST" },
      { time: "14:05", icon: "📊", text: "結算 ✅ 命中！TAIEX +87pts\n+50積分 | 連勝 🔥3" },
      { time: "16:30", icon: "📊", text: "市場速報 — 選擇權訊號\n🟢 AAPL RSI=28 PCR=0.41\n🔴 META RSI=74 PCR=1.8\n訊號統計：買入 4 | 賣出 2" },
    ],
  },
  {
    tier: "pro",
    label: "Pro 會員",
    color: "#ffd700",
    messages: [
      { time: "08:00", icon: "🔮", text: "Oracle 今日預測：多方 BULL 🟢  信心 74%\n下注截止 09:00 TST" },
      { time: "14:05", icon: "📊", text: "結算 ✅ 命中！+50積分  連勝 🔥3\n\n📝 編輯評論\n美股昨日強力反彈，NASDAQ +1.8%，科技股動能延續，今日台股跟漲概率高。外資昨買超 28 億，注意 2330 / 2454 走勢。" },
      { time: "16:30", icon: "⚡", text: "Option Snipe 觸發！\n$NVDA 在 5 分鐘內上漲 5.3%\n已下單：1× CALL 行使 850 到期 2026-06-20\n委託 ask+2% 送出 ✅" },
    ],
  },
];

const FAQ_ITEMS = [
  {
    q: "如何取得 Telegram Chat ID？",
    a: "打開 Telegram → 搜尋 @userinfobot → 傳送任意訊息 → Bot 會回覆你的純數字 Chat ID。",
  },
  {
    q: "免費版和 Pro 版的差異是什麼？",
    a: "免費版提供每日大盤預測、結算通知和基本訊號摘要。Pro 版額外提供即時選擇權訊號、編輯評論、Option Snipe 自動下單通知，以及優先客服。",
  },
  {
    q: "Pro 訂閱如何開通？",
    a: "目前 Pro 採邀請制。完成 Telegram 訂閱後，在 Discord 聯繫管理員，或發送郵件至 pro@lokistock.com。",
  },
  {
    q: "Option Snipe 通知是什麼？",
    a: "我們的機器人持續監控美股價格，當個股在短時間內大幅波動（預設 5%），自動選取最近價外選擇權並通知 Pro 訂閱者，可選擇連動 Moomoo 自動下單。",
  },
  {
    q: "可以隨時取消嗎？",
    a: "可以。在下方輸入你的 Chat ID 並點擊「取消訂閱」，立即生效。訂閱資料不會保留任何個人資訊。",
  },
];

// ── Sub-components ────────────────────────────────────────────────────────────

function TelegramMessage({ time, icon, text }: { time: string; icon: string; text: string }) {
  return (
    <div className="flex gap-2 items-start">
      <div className="w-8 h-8 rounded-full bg-[#2481cc] flex items-center justify-center text-sm shrink-0">
        {icon}
      </div>
      <div className="flex-1">
        <div className="bg-[#1e3a5f] rounded-2xl rounded-tl-none px-3 py-2 text-xs text-white leading-relaxed whitespace-pre-line max-w-xs">
          {text}
        </div>
        <div className="text-[10px] text-[#555570] mt-0.5 ml-1">{time}</div>
      </div>
    </div>
  );
}

function PhoneMockup({ tier, label, color, messages }: (typeof NOTIFICATION_PREVIEW)[0]) {
  return (
    <div className="flex flex-col items-center gap-3">
      <span
        className="text-xs font-bold px-2.5 py-1 rounded-full border"
        style={{ color, borderColor: color, background: `${color}18` }}
      >
        {label}
      </span>
      <div
        className="w-[220px] rounded-[28px] border-4 bg-[#0d1117] overflow-hidden shadow-2xl"
        style={{ borderColor: color + "40" }}
      >
        {/* Status bar */}
        <div className="px-4 py-2 bg-[#111128] flex items-center justify-between">
          <span className="text-white font-bold text-xs">LokiStock Bot</span>
          <span className="text-[#555570] text-[10px]">Telegram</span>
        </div>
        {/* Messages */}
        <div className="p-3 space-y-3 min-h-[240px] bg-[#0d1117]">
          {messages.map((m, i) => (
            <TelegramMessage key={i} {...m} />
          ))}
        </div>
      </div>
    </div>
  );
}

function FaqItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-[#2e2e50] bg-[#111128] overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-4 py-3.5 text-sm text-left text-white hover:bg-[#1a1a2e] transition-colors"
      >
        <span className="font-medium">{q}</span>
        <span className="text-[#555570] ml-3 shrink-0">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="px-4 pb-4 text-sm text-[#8888aa] leading-relaxed border-t border-[#2e2e50] pt-3">
          {a}
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function SubscribePage() {
  const [tid,      setTid]      = useState("");
  const [label,    setLabel]    = useState("");
  const [msg,      setMsg]      = useState<{ text: string; ok: boolean } | null>(null);
  const [loading,  setLoading]  = useState(false);

  const handle = async (action: "subscribe" | "unsubscribe") => {
    if (!tid.trim()) { setMsg({ text: "請輸入你的 Telegram Chat ID", ok: false }); return; }
    setLoading(true); setMsg(null);
    try {
      if (action === "subscribe") {
        await subscribeTelegram(tid.trim(), label.trim() || undefined);
        setMsg({ text: "✅ 訂閱成功！請查看你的 Telegram — 已傳送確認訊息。", ok: true });
      } else {
        await unsubscribeTelegram(tid.trim());
        setMsg({ text: "已取消訂閱。", ok: true });
      }
    } catch (e: unknown) {
      setMsg({ text: `❌ ${e instanceof Error ? e.message : "操作失敗"}`, ok: false });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="overflow-y-auto h-full">

      {/* ── Hero ───────────────────────────────────────────────────────────── */}
      <section className="relative flex flex-col items-center text-center px-6 py-20 overflow-hidden">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] rounded-full bg-[#448aff]/5 blur-3xl pointer-events-none" />
        <p className="text-[#448aff] text-xs font-bold tracking-[0.2em] uppercase mb-4">
          市場情報 × 社群驅動
        </p>
        <h1 className="text-4xl md:text-5xl font-extrabold text-white mb-4 leading-tight">
          加入 <span className="text-[#ffd700]">LokiStock</span> 社群
        </h1>
        <p className="text-[#8888aa] text-base max-w-xl mb-10 leading-relaxed">
          訂閱 Telegram 通知，每天收到 AI 選股訊號、市場速報與專業編輯評論。
          加入 Discord 與同好交流，共享開源平台的成長。
        </p>
        <div className="flex flex-wrap gap-3 justify-center">
          <a
            href="#subscribe-form"
            className="px-6 py-3 rounded-xl bg-[#448aff] text-white font-extrabold text-sm hover:bg-[#5c9fff] transition-colors"
          >
            📬 立即訂閱 Telegram →
          </a>
          <a
            href="https://discord.gg/lokistock"
            target="_blank"
            rel="noopener noreferrer"
            className="px-6 py-3 rounded-xl border border-[#5865F2] text-[#5865F2] font-bold text-sm hover:bg-[#5865F2]/10 transition-colors flex items-center gap-2"
          >
            <svg width="16" height="12" viewBox="0 0 127.14 96.36" fill="currentColor">
              <path d="M107.7,8.07A105.15,105.15,0,0,0,81.47,0a72.06,72.06,0,0,0-3.36,6.83A97.68,97.68,0,0,0,49,6.83,72.37,72.37,0,0,0,45.64,0,105.89,105.89,0,0,0,19.39,8.09C2.79,32.65-1.71,56.6.54,80.21h0A105.73,105.73,0,0,0,32.71,96.36,77.7,77.7,0,0,0,39.6,85.25a68.42,68.42,0,0,1-10.85-5.18c.91-.66,1.8-1.34,2.66-2a75.57,75.57,0,0,0,64.32,0c.87.71,1.76,1.39,2.66,2a68.68,68.68,0,0,1-10.87,5.19,77,77,0,0,0,6.89,11.1A105.25,105.25,0,0,0,126.6,80.22h0C129.24,52.84,122.09,29.11,107.7,8.07ZM42.45,65.69C36.18,65.69,31,60,31,53s5-12.74,11.43-12.74S54,46,53.89,53,48.84,65.69,42.45,65.69Zm42.24,0C78.41,65.69,73.25,60,73.25,53s5-12.74,11.44-12.74S96.23,46,96.12,53,91.08,65.69,84.69,65.69Z"/>
            </svg>
            加入 Discord
          </a>
        </div>
      </section>

      {/* ── Notification previews ───────────────────────────────────────────── */}
      <section className="px-6 py-16 max-w-4xl mx-auto">
        <h2 className="text-2xl font-extrabold text-white text-center mb-2">你會收到什麼？</h2>
        <p className="text-[#555570] text-sm text-center mb-12">每日訊號、市場速報、Pro 編輯評論 — 全部直送 Telegram</p>
        <div className="flex flex-col sm:flex-row gap-8 justify-center items-start">
          {NOTIFICATION_PREVIEW.map(p => (
            <PhoneMockup key={p.tier} {...p} />
          ))}
        </div>
      </section>

      {/* ── Tier comparison ─────────────────────────────────────────────────── */}
      <section className="px-6 py-16 max-w-3xl mx-auto">
        <h2 className="text-2xl font-extrabold text-white text-center mb-2">方案比較</h2>
        <p className="text-[#555570] text-sm text-center mb-10">選擇適合你的訂閱方式</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

          {/* Free */}
          <div className="bg-[#111128] border border-[#2e2e50] rounded-2xl p-6">
            <div className="mb-4">
              <p className="text-xs text-[#555570] uppercase tracking-wide mb-1">免費</p>
              <p className="text-3xl font-extrabold text-white">NT$0</p>
              <p className="text-xs text-[#555570] mt-1">永久免費，無需信用卡</p>
            </div>
            <ul className="space-y-2.5 mb-6">
              {FREE_PERKS.map(f => (
                <li key={f} className="flex items-start gap-2 text-sm text-[#8888aa]">
                  <span className="text-[#448aff] mt-0.5">✓</span>
                  <span>{f}</span>
                </li>
              ))}
            </ul>
            <a
              href="#subscribe-form"
              className="block text-center py-2.5 rounded-xl border border-[#448aff] text-[#448aff] text-sm font-bold hover:bg-[#448aff]/10 transition-colors"
            >
              立即訂閱
            </a>
          </div>

          {/* Pro */}
          <div className="bg-[#111128] border border-[#ffd700]/50 rounded-2xl p-6 relative overflow-hidden">
            <div className="absolute top-3 right-3">
              <span className="text-[9px] font-extrabold px-2 py-0.5 rounded-full bg-[#ffd700] text-[#0d0d14]">PRO</span>
            </div>
            <div className="mb-4">
              <p className="text-xs text-[#ffd700] uppercase tracking-wide mb-1">Pro 方案</p>
              <p className="text-3xl font-extrabold text-white">
                NT$100<span className="text-base font-normal text-[#8888aa]">/月</span>
              </p>
              <p className="text-xs text-[#555570] mt-1">目前採邀請制 — Discord 聯繫開通</p>
            </div>
            <ul className="space-y-2.5 mb-6">
              {PRO_PERKS.map(f => (
                <li key={f} className="flex items-start gap-2 text-sm text-white">
                  <span className="text-[#ffd700] mt-0.5">✓</span>
                  <span>{f}</span>
                </li>
              ))}
            </ul>
            <a
              href="https://discord.gg/lokistock"
              target="_blank"
              rel="noopener noreferrer"
              className="block text-center py-2.5 rounded-xl bg-[#ffd700] text-[#0d0d14] text-sm font-extrabold hover:bg-[#ffe033] transition-colors"
            >
              Discord 申請 Pro →
            </a>
          </div>
        </div>
      </section>

      {/* ── Telegram subscription form ──────────────────────────────────────── */}
      <section id="subscribe-form" className="px-6 py-16 max-w-lg mx-auto">
        <h2 className="text-2xl font-extrabold text-white text-center mb-2">訂閱每日通知</h2>
        <p className="text-[#555570] text-sm text-center mb-8">
          輸入你的 Telegram Chat ID，立即收到確認訊息
        </p>

        {/* How to get Chat ID */}
        <div className="rounded-xl border border-[#2e2e50] bg-[#111128] p-4 mb-6">
          <p className="text-xs font-bold text-white mb-2">如何取得 Chat ID？</p>
          <ol className="space-y-1 text-xs text-[#8888aa]">
            <li><span className="text-white">1.</span> 打開 Telegram，搜尋{" "}
              <a href="https://t.me/userinfobot" target="_blank" rel="noopener noreferrer"
                 className="text-[#448aff] hover:underline">@userinfobot</a>
            </li>
            <li><span className="text-white">2.</span> 傳送任意訊息（例如 /start）</li>
            <li><span className="text-white">3.</span> Bot 回覆的純數字即為你的 Chat ID</li>
          </ol>
        </div>

        <div className="bg-[#111128] border border-[#2e2e50] rounded-2xl p-6 space-y-4">
          <div>
            <label className="text-xs text-[#8888aa] block mb-1.5 uppercase tracking-wider">Telegram Chat ID</label>
            <input
              value={tid}
              onChange={e => setTid(e.target.value)}
              placeholder="例：123456789"
              className="w-full bg-[#0d0d14] border border-[#2e2e50] rounded-lg px-4 py-3 text-white text-sm placeholder-[#555570] focus:outline-none focus:border-[#448aff] transition-colors"
            />
          </div>
          <div>
            <label className="text-xs text-[#8888aa] block mb-1.5 uppercase tracking-wider">顯示名稱（選填）</label>
            <input
              value={label}
              onChange={e => setLabel(e.target.value)}
              placeholder="例：Sami"
              className="w-full bg-[#0d0d14] border border-[#2e2e50] rounded-lg px-4 py-3 text-white text-sm placeholder-[#555570] focus:outline-none focus:border-[#448aff] transition-colors"
            />
          </div>

          {msg && (
            <div className={`rounded-lg px-4 py-3 text-sm ${
              msg.ok
                ? "bg-[#00e676]/10 border border-[#00e676] text-[#00e676]"
                : "bg-[#ff5252]/10 border border-[#ff5252] text-[#ff5252]"
            }`}>
              {msg.text}
            </div>
          )}

          <button
            onClick={() => handle("subscribe")}
            disabled={loading}
            className="w-full py-3 rounded-xl bg-[#448aff] text-white font-extrabold text-sm hover:bg-[#5c9fff] disabled:opacity-50 transition-colors"
          >
            {loading ? "處理中…" : "📬 立即訂閱"}
          </button>
          <p className="text-center text-xs text-[#555570]">
            已訂閱？{" "}
            <button
              onClick={() => handle("unsubscribe")}
              className="text-[#8888aa] hover:text-white underline transition-colors"
            >
              取消訂閱
            </button>
          </p>
        </div>
      </section>

      {/* ── Discord community ───────────────────────────────────────────────── */}
      <section className="px-6 py-16 max-w-4xl mx-auto">
        <div className="rounded-2xl border border-[#5865F2]/40 bg-[#111128] p-8 flex flex-col md:flex-row items-center gap-8">
          <div className="flex-1 text-center md:text-left">
            <div className="text-4xl mb-3">
              <svg viewBox="0 0 127.14 96.36" fill="#5865F2" className="w-10 h-10 inline-block">
                <path d="M107.7,8.07A105.15,105.15,0,0,0,81.47,0a72.06,72.06,0,0,0-3.36,6.83A97.68,97.68,0,0,0,49,6.83,72.37,72.37,0,0,0,45.64,0,105.89,105.89,0,0,0,19.39,8.09C2.79,32.65-1.71,56.6.54,80.21h0A105.73,105.73,0,0,0,32.71,96.36,77.7,77.7,0,0,0,39.6,85.25a68.42,68.42,0,0,1-10.85-5.18c.91-.66,1.8-1.34,2.66-2a75.57,75.57,0,0,0,64.32,0c.87.71,1.76,1.39,2.66,2a68.68,68.68,0,0,1-10.87,5.19,77,77,0,0,0,6.89,11.1A105.25,105.25,0,0,0,126.6,80.22h0C129.24,52.84,122.09,29.11,107.7,8.07ZM42.45,65.69C36.18,65.69,31,60,31,53s5-12.74,11.43-12.74S54,46,53.89,53,48.84,65.69,42.45,65.69Zm42.24,0C78.41,65.69,73.25,60,73.25,53s5-12.74,11.44-12.74S96.23,46,96.12,53,91.08,65.69,84.69,65.69Z"/>
              </svg>
            </div>
            <h3 className="text-xl font-extrabold text-white mb-2">加入 Discord 社群</h3>
            <p className="text-[#8888aa] text-sm leading-relaxed max-w-md">
              和其他交易者交流心得、分享訊號、討論市場。Pro 會員可進入私人分析頻道，
              開源貢獻者可直接在 #dev 頻道提交功能建議。
            </p>
            <div className="flex flex-wrap gap-2 mt-4 justify-center md:justify-start">
              {["#市場討論", "#訊號分享", "#回測研究", "#dev", "#pro-analysis"].map(ch => (
                <span key={ch} className="text-xs px-2.5 py-1 rounded-full bg-[#5865F2]/20 text-[#7289da] border border-[#5865F2]/30">
                  {ch}
                </span>
              ))}
            </div>
          </div>
          <a
            href="https://discord.gg/lokistock"
            target="_blank"
            rel="noopener noreferrer"
            className="shrink-0 px-8 py-4 rounded-2xl bg-[#5865F2] text-white font-extrabold text-sm hover:bg-[#4752c4] transition-colors shadow-lg shadow-[#5865F2]/20"
          >
            加入 Discord →
          </a>
        </div>
      </section>

      {/* ── Open source banner ──────────────────────────────────────────────── */}
      <section className="px-6 py-10 max-w-4xl mx-auto">
        <div className="rounded-2xl border border-[#2e2e50] bg-[#111128] p-6 flex flex-col sm:flex-row items-center gap-6">
          <div className="text-4xl">
            <svg viewBox="0 0 24 24" fill="white" className="w-10 h-10">
              <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/>
            </svg>
          </div>
          <div className="flex-1 text-center sm:text-left">
            <h3 className="text-white font-extrabold mb-1">LokiStock 是開源專案</h3>
            <p className="text-[#8888aa] text-sm leading-relaxed">
              我們的分析引擎、回測系統與 API 完全開源。歡迎提 Issue、送 PR、Fork 後自行部署，
              或在 Discord #dev 頻道提交功能建議。一起把台股工具做得更好。
            </p>
          </div>
          <a
            href="https://github.com/lokistock/lokistock"
            target="_blank"
            rel="noopener noreferrer"
            className="shrink-0 px-5 py-2.5 rounded-xl border border-white/20 text-white font-bold text-sm hover:border-white/60 hover:bg-white/5 transition-colors flex items-center gap-2"
          >
            ⭐ Star on GitHub
          </a>
        </div>
      </section>

      {/* ── FAQ ─────────────────────────────────────────────────────────────── */}
      <section className="px-6 py-10 max-w-2xl mx-auto">
        <h2 className="text-xl font-extrabold text-white mb-6">常見問題</h2>
        <div className="space-y-2">
          {FAQ_ITEMS.map((item, i) => <FaqItem key={i} {...item} />)}
        </div>
      </section>

      {/* ── Footer note ─────────────────────────────────────────────────────── */}
      <section className="px-6 py-10 text-center border-t border-[#2e2e50]">
        <p className="text-[#555570] text-xs">
          資料僅供參考，不構成投資建議。訂閱即同意接收 LokiStock 每日市場通知。
        </p>
        <div className="flex justify-center gap-4 mt-3 text-[10px] text-[#2e2e50]">
          <Link href="/" className="hover:text-[#555570] transition-colors">← 回首頁</Link>
          <span>·</span>
          <a href="https://discord.gg/lokistock" target="_blank" rel="noopener noreferrer" className="hover:text-[#555570] transition-colors">Discord</a>
          <span>·</span>
          <a href="https://github.com/lokistock/lokistock" target="_blank" rel="noopener noreferrer" className="hover:text-[#555570] transition-colors">GitHub</a>
        </div>
      </section>
    </div>
  );
}
