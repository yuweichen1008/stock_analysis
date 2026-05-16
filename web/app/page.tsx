"use client";

import Link from "next/link";

const FEATURES = [
  {
    icon: "🇹🇼",
    title: "TWS 選股",
    desc: "台股宇宙全覆蓋，RSI 超賣訊號、外資買超、高值護城河股自動篩選，Enter 即時查詢任意個股。",
    href: "/tws",
  },
  {
    icon: "📈",
    title: "選擇權篩選",
    desc: "雙日 RSI + PCR + IV Rank 交叉篩選，自動標記買入/賣出/異常活躍訊號，支援歷史回測。",
    href: "/options",
  },
  {
    icon: "💹",
    title: "CTBC / Moomoo 交易",
    desc: "直接在平台下單 CTBC（台股）或 Moomoo（美股），帳戶餘額、持倉、委託一目了然。",
    href: "/trading",
  },
  {
    icon: "🔬",
    title: "回測引擎",
    desc: "選擇權訊號勝率分析、台股 RSI 策略回測、資金曲線圖，快速驗證你的交易假設。",
    href: "/backtest",
  },
  {
    icon: "📰",
    title: "新聞 & PCR",
    desc: "Google News 即時聚合 + 30 分鐘 PCR 快照，情緒指標與市場脈動同步追蹤。",
    href: "/news",
  },
  {
    icon: "📅",
    title: "週訊號",
    desc: "每週自動掃描 4500+ 那斯達克股票，±5% 逆勢信號，可接 Moomoo 自動執行。",
    href: "/weekly",
  },
];

const FREE_FEATURES = ["基本市場訊號", "新聞 & PCR 追蹤", "台股宇宙瀏覽", "選擇權篩選（延遲）"];
const PRO_FEATURES  = ["即時數據 & 優先推播", "CTBC + Moomoo Broker 整合", "完整回測引擎", "週訊號自動執行", "選擇權即時篩選", "優先客服支援"];

export default function LandingPage() {
  return (
    <div className="overflow-y-auto h-full">
      {/* ── Hero ──────────────────────────────────────────────────────────────── */}
      <section className="relative flex flex-col items-center justify-center text-center px-6 py-24 overflow-hidden">
        {/* Glow */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] rounded-full bg-[#ffd700]/5 blur-3xl pointer-events-none" />

        <p className="text-[#ffd700] text-xs font-bold tracking-[0.2em] uppercase mb-4">
          台灣・美國股市智能平台
        </p>
        <h1 className="text-5xl md:text-6xl font-extrabold text-white mb-6 leading-tight">
          <span className="text-[#ffd700]">Loki</span>Stock
        </h1>
        <p className="text-[#8888aa] text-lg md:text-xl max-w-2xl mb-10 leading-relaxed">
          市場訊號、選擇權情報、Broker 整合交易——全在一個平台。
          台股用 CTBC，美股用 Moomoo，訊號 AI 自動篩選。
        </p>
        <div className="flex flex-wrap gap-3 justify-center">
          <Link
            href="/tws"
            className="px-6 py-3 rounded-xl bg-[#ffd700] text-[#0d0d14] font-extrabold text-sm hover:bg-[#ffe033] transition-colors"
          >
            進入 TWS 選股 →
          </Link>
          <Link
            href="/options"
            className="px-6 py-3 rounded-xl border border-[#2e2e50] text-white font-bold text-sm hover:border-[#ffd700] hover:text-[#ffd700] transition-colors"
          >
            查看選擇權篩選
          </Link>
        </div>

        {/* Quick stats */}
        <div className="flex flex-wrap gap-8 justify-center mt-16 text-center">
          {[
            ["4500+", "美股覆蓋"],
            ["1000+", "台股追蹤"],
            ["2×/天", "選擇權掃描"],
            ["30分鐘", "PCR 更新"],
          ].map(([val, label]) => (
            <div key={label}>
              <p className="text-2xl font-extrabold text-[#ffd700]">{val}</p>
              <p className="text-xs text-[#555570] mt-1">{label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Features ──────────────────────────────────────────────────────────── */}
      <section className="px-6 py-16 max-w-5xl mx-auto">
        <h2 className="text-2xl font-extrabold text-white text-center mb-2">平台功能</h2>
        <p className="text-[#555570] text-sm text-center mb-10">從篩選到下單，一站搞定</p>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {FEATURES.map(f => (
            <Link
              key={f.href}
              href={f.href}
              className="group bg-[#111128] border border-[#2e2e50] rounded-2xl p-5 hover:border-[#ffd700]/60 transition-colors"
            >
              <div className="text-3xl mb-3">{f.icon}</div>
              <h3 className="text-white font-extrabold mb-2 group-hover:text-[#ffd700] transition-colors">
                {f.title}
              </h3>
              <p className="text-[#8888aa] text-xs leading-relaxed">{f.desc}</p>
            </Link>
          ))}
        </div>
      </section>

      {/* ── Pricing ───────────────────────────────────────────────────────────── */}
      <section className="px-6 py-16 max-w-3xl mx-auto">
        <h2 className="text-2xl font-extrabold text-white text-center mb-2">方案選擇</h2>
        <p className="text-[#555570] text-sm text-center mb-10">
          免費體驗核心功能，Pro 解鎖即時數據與 Broker 整合
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Free */}
          <div className="bg-[#111128] border border-[#2e2e50] rounded-2xl p-6">
            <p className="text-xs text-[#555570] uppercase tracking-wide mb-1">免費</p>
            <p className="text-3xl font-extrabold text-white mb-1">NT$0</p>
            <p className="text-xs text-[#555570] mb-5">永久免費，無需信用卡</p>
            <ul className="space-y-2 mb-6">
              {FREE_FEATURES.map(f => (
                <li key={f} className="flex items-center gap-2 text-sm text-[#8888aa]">
                  <span className="text-[#555570]">✓</span> {f}
                </li>
              ))}
            </ul>
            <Link
              href="/tws"
              className="block text-center py-2.5 rounded-xl border border-[#2e2e50] text-[#8888aa] text-sm font-bold hover:border-white hover:text-white transition-colors"
            >
              開始使用
            </Link>
          </div>

          {/* Pro */}
          <div className="bg-[#111128] border border-[#ffd700]/40 rounded-2xl p-6 relative overflow-hidden">
            <div className="absolute top-3 right-3">
              <span className="text-[9px] font-extrabold px-2 py-0.5 rounded-full bg-[#ffd700] text-[#0d0d14]">
                PRO
              </span>
            </div>
            <p className="text-xs text-[#ffd700] uppercase tracking-wide mb-1">Pro 方案</p>
            <p className="text-3xl font-extrabold text-white mb-1">
              NT$100<span className="text-base font-normal text-[#8888aa]">/月</span>
            </p>
            <p className="text-xs text-[#555570] mb-5">月繳，隨時取消</p>
            <ul className="space-y-2 mb-6">
              {PRO_FEATURES.map(f => (
                <li key={f} className="flex items-center gap-2 text-sm text-white">
                  <span className="text-[#ffd700]">✓</span> {f}
                </li>
              ))}
            </ul>
            <Link
              href="/subscribe"
              className="block text-center py-2.5 rounded-xl bg-[#ffd700] text-[#0d0d14] text-sm font-extrabold hover:bg-[#ffe033] transition-colors"
            >
              訂閱 Pro →
            </Link>
          </div>
        </div>
      </section>

      {/* ── Footer CTA ────────────────────────────────────────────────────────── */}
      <section className="px-6 py-16 text-center border-t border-[#2e2e50]">
        <p className="text-[#555570] text-sm mb-4">
          資料僅供參考，不構成投資建議。交易有風險，請自行判斷。
        </p>
        <p className="text-[#2e2e50] text-xs">
          LokiStock © {new Date().getFullYear()} — Powered by Oracle AI
        </p>
      </section>
    </div>
  );
}
