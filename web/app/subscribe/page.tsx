"use client";

import { useState } from "react";
import { subscribeTelegram, unsubscribeTelegram } from "@/lib/api";

const BENEFITS = [
  { icon: "📊", title: "每日多空預測", desc: "08:00 TST 送出今日大盤預測 + 信心指數" },
  { icon: "🎯", title: "結算通知",     desc: "14:05 TST 結算勝負 + 累計積分更新" },
  { icon: "🔔", title: "AI 訊號股",   desc: "精選強勢訊號股票 + 分析師評級" },
];

const FAQ = [
  { q: "這是免費的嗎？",     a: "完全免費，無需綁定信用卡或訂閱方案。" },
  { q: "每天會收到幾則訊息？", a: "每個交易日 2 則：08:00 預測 + 14:05 結算，週末不發送。" },
  { q: "可以隨時取消嗎？",   a: "可以。在下方輸入你的 Chat ID 並點擊「取消訂閱」即可立即生效。" },
];

export default function SubscribePage() {
  const [tid,    setTid]    = useState("");
  const [label,  setLabel]  = useState("");
  const [msg,    setMsg]    = useState<{ text: string; ok: boolean } | null>(null);
  const [loading, setLoading] = useState(false);
  const [openFaq, setOpenFaq] = useState<number | null>(null);

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
    <div className="min-h-full flex flex-col items-center px-4 py-12">
      <div className="w-full max-w-lg space-y-8">
        {/* Header */}
        <div className="text-center space-y-2">
          <h1 className="text-4xl font-extrabold">🔮 Oracle</h1>
          <p className="text-[#8888aa]">訂閱 TAIEX 大盤多空每日通知</p>
        </div>

        {/* Benefits */}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {BENEFITS.map((b) => (
            <div
              key={b.title}
              className="rounded-xl border border-[#2e2e50] bg-[#1a1a2e] p-4 text-center space-y-2"
            >
              <div className="text-3xl">{b.icon}</div>
              <div className="font-semibold text-sm text-white">{b.title}</div>
              <div className="text-xs text-[#8888aa] leading-relaxed">{b.desc}</div>
            </div>
          ))}
        </div>

        {/* How to get Chat ID */}
        <div className="rounded-xl border border-[#2e2e50] bg-[#1a1a2e] p-5 space-y-3">
          <h2 className="font-semibold text-white">如何取得你的 Chat ID？</h2>
          <ol className="space-y-2 text-sm text-[#8888aa]">
            <li><span className="text-white font-medium">步驟 1</span> — 打開 Telegram，搜尋{" "}
              <a href="https://t.me/userinfobot" target="_blank" rel="noopener noreferrer"
                 className="text-accent hover:underline">@userinfobot</a>
            </li>
            <li><span className="text-white font-medium">步驟 2</span> — 傳送任意訊息（例如：/start）</li>
            <li><span className="text-white font-medium">步驟 3</span> — Bot 會立即回覆你的 Chat ID（純數字）</li>
            <li><span className="text-white font-medium">步驟 4</span> — 將此 ID 貼入下方欄位</li>
          </ol>
        </div>

        {/* Subscription form */}
        <div className="rounded-xl border border-[#2e2e50] bg-[#1a1a2e] p-6 space-y-4">
          <div className="space-y-1">
            <label className="block text-xs text-[#8888aa] uppercase tracking-wider">
              Telegram Chat ID
            </label>
            <input
              value={tid}
              onChange={(e) => setTid(e.target.value)}
              placeholder="例：123456789"
              className="w-full rounded-lg bg-[#252540] border border-[#2e2e50] text-white px-4 py-3 outline-none focus:border-accent transition-colors"
            />
          </div>
          <div className="space-y-1">
            <label className="block text-xs text-[#8888aa] uppercase tracking-wider">
              顯示名稱（選填）
            </label>
            <input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="例：Sami"
              className="w-full rounded-lg bg-[#252540] border border-[#2e2e50] text-white px-4 py-3 outline-none focus:border-accent transition-colors"
            />
          </div>

          <button
            onClick={() => handle("subscribe")}
            disabled={loading}
            className="w-full rounded-lg bg-accent py-3 font-bold text-white hover:bg-blue-500 disabled:opacity-50 transition-colors"
          >
            {loading ? "處理中…" : "📬 立即訂閱"}
          </button>

          {msg && (
            <div
              className={`rounded-lg px-4 py-3 text-sm ${
                msg.ok
                  ? "bg-green-900/40 border border-green-500 text-green-400"
                  : "bg-red-900/40  border border-red-500  text-red-400"
              }`}
            >
              {msg.text}
            </div>
          )}

          <div className="text-center text-xs text-[#555570]">
            已訂閱？{" "}
            <button
              onClick={() => handle("unsubscribe")}
              className="text-[#8888aa] hover:text-white transition-colors underline"
            >
              取消訂閱
            </button>
          </div>
        </div>

        {/* FAQ */}
        <div className="space-y-2">
          <h2 className="font-semibold text-white">常見問題</h2>
          {FAQ.map((item, i) => (
            <div
              key={i}
              className="rounded-xl border border-[#2e2e50] bg-[#1a1a2e] overflow-hidden"
            >
              <button
                onClick={() => setOpenFaq(openFaq === i ? null : i)}
                className="w-full flex items-center justify-between px-4 py-3 text-sm text-left text-white hover:bg-[#252540] transition-colors"
              >
                <span>{item.q}</span>
                <span className="text-[#8888aa]">{openFaq === i ? "▲" : "▼"}</span>
              </button>
              {openFaq === i && (
                <div className="px-4 pb-3 text-sm text-[#8888aa]">{item.a}</div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
