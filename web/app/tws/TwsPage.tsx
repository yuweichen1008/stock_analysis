"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ComposedChart, Area, Line, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from "recharts";
import type { TwsStock, TwsUniverse, OhlcvResponse } from "@/lib/types";
import { twsUniverse, twsStock, chartOhlcv } from "@/lib/api";

// ── Types ─────────────────────────────────────────────────────────────────────

type SortKey  = "signal" | "rsi" | "foreign" | "score";
type FilterCat = "all" | "signal" | "high_value";
type Period   = "1mo" | "3mo" | "6mo" | "1y";

// ── Helpers ───────────────────────────────────────────────────────────────────

const NT = (v: number | null, dec = 0) =>
  v == null ? "—" : `NT$${v.toLocaleString("zh-TW", { minimumFractionDigits: dec, maximumFractionDigits: dec })}`;

const pct = (v: number | null) =>
  v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;

const fmt = (v: number | null, dec = 1) =>
  v == null ? "—" : v.toFixed(dec);

const flow = (v: number | null) => {
  if (v == null) return "—";
  const abs = Math.abs(v);
  const s = abs >= 1e8 ? `${(abs / 1e8).toFixed(1)}億`
          : abs >= 1e4 ? `${(v / 1e4).toFixed(0)}萬`
          : String(Math.round(v));
  return (v >= 0 ? "+" : "-") + s;
};

function rsiColor(rsi: number | null) {
  if (rsi == null) return "#8888aa";
  if (rsi < 30) return "#ff5252";
  if (rsi < 45) return "#ff8a65";
  if (rsi > 70) return "#00e676";
  if (rsi > 60) return "#69f0ae";
  return "#8888aa";
}

function scoreColor(s: number | null) {
  if (s == null) return "#555570";
  if (s >= 7) return "#ffd700";
  if (s >= 4) return "#ff8a65";
  return "#8888aa";
}

function sentimentLabel(v: number | null) {
  if (v == null) return null;
  if (v > 0.2) return { label: "正面", color: "#00e676" };
  if (v < -0.2) return { label: "負面", color: "#ff5252" };
  return { label: "中性", color: "#8888aa" };
}

// ── Small badge components ─────────────────────────────────────────────────────

function SignalBadge({ category, is_signal }: { category: string | null; is_signal: boolean }) {
  if (category === "mean_reversion" || is_signal) {
    return (
      <span className="text-[9px] font-extrabold px-1.5 py-0.5 rounded-full border border-[#ff5252] text-[#ff5252] bg-[#ff525218]">
        訊號
      </span>
    );
  }
  if (category === "high_value_moat") {
    return (
      <span className="text-[9px] font-extrabold px-1.5 py-0.5 rounded-full border border-[#ffd700] text-[#ffd700] bg-[#ffd70018]">
        高值
      </span>
    );
  }
  return null;
}

function RsiBar({ rsi }: { rsi: number | null }) {
  if (rsi == null) return <div className="text-[10px] text-[#555570]">RSI —</div>;
  const color = rsiColor(rsi);
  return (
    <div className="flex items-center gap-1.5">
      <div className="relative w-14 h-1.5 rounded-full bg-[#2e2e50]">
        <div className="absolute left-0 top-0 h-full w-[30%] rounded-l-full bg-[#ff5252]/20" />
        <div className="absolute right-0 top-0 h-full w-[30%] rounded-r-full bg-[#00e676]/20" />
        <div
          className="absolute top-1/2 -translate-y-1/2 w-2 h-2 rounded-full border border-[#0d0d14]"
          style={{ left: `calc(${Math.round(rsi)}% - 4px)`, backgroundColor: color }}
        />
      </div>
      <span className="text-[10px] font-bold tabular-nums" style={{ color }}>{rsi.toFixed(0)}</span>
    </div>
  );
}

// ── Stock list row ─────────────────────────────────────────────────────────────

function StockRow({
  stock, selected, onClick,
}: { stock: TwsStock; selected: boolean; onClick: () => void }) {
  const priceUp = (stock.bias ?? 0) >= 0;
  return (
    <button
      onClick={onClick}
      className={[
        "w-full text-left px-4 py-3 border-b border-[#1e1e38] transition-colors",
        selected ? "bg-[#1a2744]" : "hover:bg-[#14142a]",
      ].join(" ")}
    >
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <span className="font-bold text-sm text-white">{stock.ticker}</span>
          <SignalBadge category={stock.category} is_signal={stock.is_signal} />
        </div>
        <div className="text-right">
          {stock.price != null && (
            <span className="text-sm font-bold text-white">{NT(stock.price)}</span>
          )}
        </div>
      </div>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          {stock.name && (
            <span className="text-[10px] text-[#555570] truncate max-w-[90px]">{stock.name}</span>
          )}
          {stock.bias != null && (
            <span className="text-[10px] font-bold" style={{ color: priceUp ? "#ff5252" : "#00e676" }}>
              {priceUp ? "▲" : "▼"}{Math.abs(stock.bias).toFixed(1)}%
            </span>
          )}
        </div>
        <RsiBar rsi={stock.RSI} />
      </div>
    </button>
  );
}

// ── Stat card ──────────────────────────────────────────────────────────────────

function StatCard({ label, value, color, sub }: {
  label: string; value: string; color?: string; sub?: string;
}) {
  return (
    <div className="bg-[#0d0d14] border border-[#2e2e50] rounded-xl p-3">
      <p className="text-[9px] text-[#555570] uppercase tracking-wide mb-1">{label}</p>
      <p className="text-sm font-bold" style={{ color: color ?? "white" }}>{value}</p>
      {sub && <p className="text-[9px] text-[#8888aa] mt-0.5">{sub}</p>}
    </div>
  );
}

// ── Foreign flow bars ──────────────────────────────────────────────────────────

function FlowBar({ label, value, max }: { label: string; value: number | null; max: number }) {
  if (value == null) return null;
  const pct = max > 0 ? Math.abs(value) / max * 100 : 0;
  const pos = value >= 0;
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] text-[#555570] w-8 shrink-0">{label}</span>
      <div className="flex-1 h-3 bg-[#1e1e38] rounded-full overflow-hidden relative">
        <div
          className="absolute top-0 h-full rounded-full transition-all"
          style={{
            width:  `${pct}%`,
            left:   pos ? "50%" : `${50 - pct}%`,
            backgroundColor: pos ? "#00e676" : "#ff5252",
            opacity: 0.8,
          }}
        />
        <div className="absolute left-1/2 top-0 h-full w-px bg-[#2e2e50]" />
      </div>
      <span className="text-[10px] font-bold w-16 text-right shrink-0"
        style={{ color: pos ? "#00e676" : "#ff5252" }}>
        {flow(value)}
      </span>
    </div>
  );
}

// ── Mini inline chart ──────────────────────────────────────────────────────────

function MiniChart({ ticker, period }: { ticker: string; period: Period }) {
  const [data, setData] = useState<OhlcvResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    chartOhlcv(ticker, period, "TW")
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [ticker, period]);

  if (loading) {
    return <div className="h-48 animate-pulse bg-[#1e1e38] rounded-xl" />;
  }

  const bars = data?.bars ?? [];
  if (!bars.length) {
    return (
      <div className="h-48 flex items-center justify-center text-[#555570] text-xs bg-[#111128] rounded-xl border border-[#2e2e50]">
        圖表資料載入失敗
      </div>
    );
  }

  const bandData = bars.map(b => ({
    date:  b.date,
    low:   b.low,
    band:  parseFloat((b.high - b.low).toFixed(2)),
    close: b.close,
    ma20:  b.ma20,
    ma50:  b.ma50,
    open:  b.open,
    high:  b.high,
  }));

  const yMin = Math.min(...bars.map(b => b.low))  * 0.97;
  const yMax = Math.max(...bars.map(b => b.high)) * 1.03;
  const intv = Math.ceil(bars.length / 6);

  const lastClose = bars[bars.length - 1]?.close;
  const prevClose = bars[bars.length - 2]?.close;
  const chgPct = prevClose && lastClose ? ((lastClose - prevClose) / prevClose * 100) : null;

  return (
    <div>
      {chgPct != null && (
        <div className="flex items-baseline gap-2 mb-2">
          <span className="text-lg font-extrabold text-white">{NT(lastClose)}</span>
          <span className={`text-xs font-bold ${(chgPct ?? 0) >= 0 ? "text-[#ff5252]" : "text-[#00e676]"}`}>
            {(chgPct ?? 0) >= 0 ? "▲" : "▼"} {Math.abs(chgPct ?? 0).toFixed(2)}%
          </span>
        </div>
      )}
      <ResponsiveContainer width="100%" height={180}>
        <ComposedChart data={bandData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e1e38" />
          <XAxis dataKey="date" tick={{ fill: "#555570", fontSize: 9 }} tickLine={false}
            axisLine={false} interval={intv} />
          <YAxis domain={[yMin, yMax]} tick={{ fill: "#8888aa", fontSize: 9 }}
            tickLine={false} axisLine={false} width={52}
            tickFormatter={v => `$${v.toLocaleString("zh-TW")}`} />
          <Tooltip
            contentStyle={{ backgroundColor: "#1a1a2e", border: "1px solid #2e2e50", borderRadius: 8, fontSize: 10 }}
            labelStyle={{ color: "#8888aa" }}
            formatter={(v: number, name: string) => [`NT$${v.toLocaleString("zh-TW", { minimumFractionDigits: 2 })}`, name]}
          />
          <Area type="monotone" dataKey="low" stackId="b" stroke="none" fill="none"
            legendType="none" isAnimationActive={false} />
          <Area type="monotone" dataKey="band" stackId="b" stroke="#448aff44"
            fill="#448aff" fillOpacity={0.12} legendType="none" isAnimationActive={false} />
          <Line type="monotone" dataKey="ma20" stroke="#448aff" strokeWidth={1.2}
            dot={false} connectNulls legendType="none" isAnimationActive={false} />
          <Line type="monotone" dataKey="ma50" stroke="#ffd740" strokeWidth={1.2}
            dot={false} connectNulls legendType="none" isAnimationActive={false} />
          <Line type="monotone" dataKey="close" stroke="#00e676" strokeWidth={2}
            dot={false} legendType="none" isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
      <div className="flex gap-4 mt-1.5 text-[9px] text-[#8888aa]">
        <span className="flex items-center gap-1"><span className="inline-block w-4 h-px bg-[#00e676]" />收盤</span>
        <span className="flex items-center gap-1"><span className="inline-block w-4 h-px bg-[#448aff]" />MA20</span>
        <span className="flex items-center gap-1"><span className="inline-block w-4 h-px bg-[#ffd740]" />MA50</span>
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-sm bg-[#448aff]/20" />高低區間</span>
      </div>
    </div>
  );
}

// ── RSI arc gauge ──────────────────────────────────────────────────────────────

function RsiGauge({ rsi }: { rsi: number | null }) {
  if (rsi == null) return null;
  const color = rsiColor(rsi);
  const angle = (rsi / 100) * 180 - 90; // -90° (0) to +90° (100)
  const label =
    rsi < 30 ? "超賣" : rsi < 45 ? "偏低" : rsi > 70 ? "超買" : rsi > 60 ? "偏高" : "中性";

  return (
    <div className="flex flex-col items-center gap-1">
      <svg width="96" height="56" viewBox="0 0 96 56">
        {/* Background arc */}
        <path d="M 8 52 A 40 40 0 0 1 88 52" fill="none" stroke="#2e2e50" strokeWidth="8" strokeLinecap="round" />
        {/* Oversold zone */}
        <path d="M 8 52 A 40 40 0 0 1 20 19" fill="none" stroke="#ff5252" strokeWidth="8" strokeOpacity="0.25" strokeLinecap="round" />
        {/* Overbought zone */}
        <path d="M 76 19 A 40 40 0 0 1 88 52" fill="none" stroke="#00e676" strokeWidth="8" strokeOpacity="0.25" strokeLinecap="round" />
        {/* Needle */}
        <line
          x1="48" y1="52"
          x2={48 + 32 * Math.cos(((angle - 90) * Math.PI) / 180)}
          y2={52 + 32 * Math.sin(((angle - 90) * Math.PI) / 180)}
          stroke={color} strokeWidth="2.5" strokeLinecap="round"
        />
        <circle cx="48" cy="52" r="4" fill={color} />
      </svg>
      <div className="text-center">
        <p className="text-xl font-extrabold" style={{ color }}>{rsi.toFixed(1)}</p>
        <p className="text-[10px] font-bold" style={{ color }}>{label}</p>
      </div>
    </div>
  );
}

// ── Detail panel ───────────────────────────────────────────────────────────────

function DetailPanel({ ticker, period, onPeriodChange }: {
  ticker: string;
  period: Period;
  onPeriodChange: (p: Period) => void;
}) {
  const [detail, setDetail] = useState<TwsStock | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    twsStock(ticker)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setLoading(false));
  }, [ticker]);

  if (loading) {
    return (
      <div className="p-6 space-y-4 animate-pulse">
        <div className="h-8 bg-[#1e1e38] rounded-xl w-1/2" />
        <div className="h-48 bg-[#1e1e38] rounded-xl" />
        <div className="grid grid-cols-3 gap-3">
          {[...Array(6)].map((_, i) => <div key={i} className="h-14 bg-[#1e1e38] rounded-xl" />)}
        </div>
      </div>
    );
  }

  if (!detail) return (
    <div className="flex items-center justify-center h-full text-[#555570]">
      載入失敗
    </div>
  );

  const sent = sentimentLabel(detail.news_sentiment);
  const flowMax = Math.max(
    Math.abs(detail.f5 ?? 0),
    Math.abs(detail.f20 ?? 0),
    Math.abs(detail.f60 ?? 0),
  );

  const PERIODS: Period[] = ["1mo", "3mo", "6mo", "1y"];

  return (
    <div className="p-5 space-y-5 overflow-y-auto h-full">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <h2 className="text-2xl font-extrabold text-white">{detail.ticker}</h2>
            <SignalBadge category={detail.category} is_signal={detail.is_signal} />
          </div>
          {detail.name && <p className="text-sm text-[#8888aa]">{detail.name}</p>}
          {detail.industry && (
            <p className="text-xs text-[#555570] mt-0.5">{detail.industry}</p>
          )}
        </div>
        <a
          href={`/charts?ticker=${detail.ticker}&market=TW`}
          target="_blank"
          className="text-xs text-[#448aff] hover:text-[#6da3ff] border border-[#448aff]/40 rounded-lg px-2.5 py-1.5 transition-colors shrink-0"
        >
          完整圖表 ↗
        </a>
      </div>

      {/* Period selector + mini chart */}
      <div className="bg-[#111128] border border-[#2e2e50] rounded-xl p-4">
        <div className="flex items-center gap-1 mb-3">
          {PERIODS.map(p => (
            <button key={p} onClick={() => onPeriodChange(p)}
              className={[
                "text-[10px] font-bold px-2 py-0.5 rounded border transition-colors",
                period === p
                  ? "border-[#ffd700] text-[#ffd700] bg-[#ffd70015]"
                  : "border-[#2e2e50] text-[#555570] hover:border-[#ffd700]",
              ].join(" ")}>
              {p}
            </button>
          ))}
        </div>
        <MiniChart ticker={detail.ticker} period={period} />
      </div>

      {/* Technical metrics + RSI gauge */}
      <div className="bg-[#111128] border border-[#2e2e50] rounded-xl p-4">
        <p className="text-[10px] text-[#555570] uppercase tracking-wide mb-3">技術指標</p>
        <div className="flex gap-4">
          <div className="flex-1 space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <StatCard label="MA120" value={NT(detail.MA120, 2)}
                sub={detail.price && detail.MA120 ? `${detail.price > detail.MA120 ? "上方" : "下方"} ${Math.abs((detail.price - detail.MA120) / detail.MA120 * 100).toFixed(1)}%` : undefined}
              />
              <StatCard label="MA20" value={NT(detail.MA20, 2)} />
              <StatCard label="偏差 (bias)" value={pct(detail.bias)}
                color={(detail.bias ?? 0) >= 0 ? "#ff5252" : "#00e676"} />
              <StatCard label="量比" value={fmt(detail.vol_ratio)}
                color={(detail.vol_ratio ?? 1) > 2 ? "#ffd700" : "#8888aa"}
                sub={(detail.vol_ratio ?? 1) > 2 ? "異常量能" : undefined} />
              {detail.score != null && (
                <StatCard label="信號分數" value={detail.score.toFixed(1)}
                  color={scoreColor(detail.score)}
                  sub={detail.score >= 7 ? "強訊號" : detail.score >= 4 ? "中訊號" : "弱訊號"} />
              )}
              {detail.f_zscore != null && (
                <StatCard label="外資 Z-Score" value={detail.f_zscore.toFixed(2)}
                  color={detail.f_zscore > 1 ? "#00e676" : detail.f_zscore < -1 ? "#ff5252" : "#8888aa"} />
              )}
            </div>
          </div>
          <div className="shrink-0">
            <RsiGauge rsi={detail.RSI} />
          </div>
        </div>
      </div>

      {/* Foreign flow */}
      {(detail.f5 != null || detail.f20 != null || detail.f60 != null) && (
        <div className="bg-[#111128] border border-[#2e2e50] rounded-xl p-4">
          <p className="text-[10px] text-[#555570] uppercase tracking-wide mb-3">外資買賣超</p>
          <div className="space-y-2">
            <FlowBar label="5日" value={detail.f5} max={flowMax} />
            <FlowBar label="20日" value={detail.f20} max={flowMax} />
            <FlowBar label="60日" value={detail.f60} max={flowMax} />
          </div>
          <p className="text-[9px] text-[#555570] mt-2">
            正值＝外資買超（紅）/ 負值＝外資賣超（綠）
          </p>
        </div>
      )}

      {/* Fundamentals */}
      {(detail.pe_ratio || detail.roe || detail.dividend_yield) && (
        <div className="bg-[#111128] border border-[#2e2e50] rounded-xl p-4">
          <p className="text-[10px] text-[#555570] uppercase tracking-wide mb-3">基本面</p>
          <div className="grid grid-cols-2 gap-2">
            {detail.pe_ratio && detail.pe_ratio !== "N/A" && (
              <StatCard label="本益比 (PE)" value={detail.pe_ratio} />
            )}
            {detail.roe && detail.roe !== "N/A" && (
              <StatCard label="股東報酬率 (ROE)" value={detail.roe} />
            )}
            {detail.dividend_yield && detail.dividend_yield !== "N/A" && (
              <StatCard label="殖利率" value={detail.dividend_yield} color="#ffd700" />
            )}
            {detail.debt_to_equity && detail.debt_to_equity !== "N/A" && (
              <StatCard label="負債比" value={detail.debt_to_equity} />
            )}
          </div>
        </div>
      )}

      {/* News sentiment */}
      {sent && (
        <div className="bg-[#111128] border border-[#2e2e50] rounded-xl px-4 py-3 flex items-center gap-3">
          <span className="text-sm">📰</span>
          <div>
            <p className="text-[10px] text-[#555570] uppercase tracking-wide">新聞情緒</p>
            <p className="text-sm font-bold" style={{ color: sent.color }}>
              {sent.label} ({detail.news_sentiment?.toFixed(2)})
            </p>
          </div>
        </div>
      )}

      {/* Last updated */}
      {detail.last_date && (
        <p className="text-[9px] text-[#555570] text-center">
          最後更新 {detail.last_date}
        </p>
      )}
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function TwsPage() {
  const [universe,   setUniverse]   = useState<TwsUniverse | null>(null);
  const [loading,    setLoading]    = useState(true);
  const [selected,   setSelected]   = useState<TwsStock | null>(null);
  const [period,     setPeriod]     = useState<Period>("3mo");

  // Filters & sort
  const [search,    setSearch]    = useState("");
  const [filterCat, setFilterCat] = useState<FilterCat>("all");
  const [sector,    setSector]    = useState("");
  const [sortBy,    setSortBy]    = useState<SortKey>("signal");

  const searchRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async (q = "", cat: FilterCat = "all", sec = "", sort: SortKey = "signal") => {
    setLoading(true);
    try {
      const data = await twsUniverse({
        signal_only: cat === "signal",
        sector:      sec || undefined,
        q:           q   || undefined,
        sort_by:     sort,
        limit:       300,
      });
      setUniverse(data);
      // High-value filter is client-side (server returns all when not signal_only)
      if (!selected && data.stocks.length > 0) {
        setSelected(data.stocks[0]);
      }
    } catch {
      setUniverse(null);
    } finally {
      setLoading(false);
    }
  }, [selected]);

  useEffect(() => { load(); }, []);

  const handleSearch = (q: string) => {
    setSearch(q);
    load(q, filterCat, sector, sortBy);
  };

  const handleCat = (cat: FilterCat) => {
    setFilterCat(cat);
    load(search, cat, sector, sortBy);
  };

  const handleSector = (sec: string) => {
    setSector(sec);
    load(search, filterCat, sec, sortBy);
  };

  const handleSort = (sort: SortKey) => {
    setSortBy(sort);
    load(search, filterCat, sector, sort);
  };

  // Client-side high-value filter
  const stocks = (universe?.stocks ?? []).filter(s => {
    if (filterCat === "high_value") return s.category === "high_value_moat";
    return true;
  });

  const sectors = universe?.sectors ?? [];

  return (
    <div className="flex flex-col h-full">
      {/* ── Top toolbar ───────────────────────────────────────────────── */}
      <div className="shrink-0 px-4 py-2.5 border-b border-[#2e2e50] bg-[#111128] flex flex-wrap items-center gap-3">
        {/* Stats */}
        <div className="flex items-center gap-3 text-xs text-[#8888aa] mr-2">
          <span>共 <span className="text-white font-bold">{universe?.total ?? 0}</span> 股</span>
          <span className="text-[#ff5252] font-bold">訊號 {universe?.signal_count ?? 0}</span>
          <span className="text-[#ffd700] font-bold">高值 {universe?.high_value_count ?? 0}</span>
          {universe?.last_updated && (
            <span className="text-[#555570]">更新 {universe.last_updated}</span>
          )}
        </div>

        {/* Search */}
        <input
          ref={searchRef}
          value={search}
          onChange={e => handleSearch(e.target.value)}
          placeholder="搜尋股票 (代碼/名稱)"
          className="w-44 bg-[#1a1a2e] border border-[#2e2e50] rounded-lg px-3 py-1 text-xs text-white placeholder-[#555570] focus:outline-none focus:border-[#448aff]"
        />

        {/* Category filter */}
        <div className="flex gap-1">
          {(["all", "signal", "high_value"] as FilterCat[]).map(c => {
            const labels: Record<FilterCat, string> = { all: "全部", signal: "訊號", high_value: "高值" };
            return (
              <button key={c} onClick={() => handleCat(c)}
                className={[
                  "text-[10px] font-bold px-2 py-1 rounded border transition-colors",
                  filterCat === c
                    ? "border-[#448aff] text-[#448aff] bg-[#1a2744]"
                    : "border-[#2e2e50] text-[#8888aa] hover:border-[#448aff]",
                ].join(" ")}>
                {labels[c]}
              </button>
            );
          })}
        </div>

        {/* Sector dropdown */}
        {sectors.length > 0 && (
          <select
            value={sector}
            onChange={e => handleSector(e.target.value)}
            className="bg-[#1a1a2e] border border-[#2e2e50] rounded-lg px-2 py-1 text-[10px] text-[#8888aa] focus:outline-none focus:border-[#448aff]"
          >
            <option value="">所有產業</option>
            {sectors.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        )}

        {/* Sort */}
        <div className="flex gap-1 ml-auto">
          <span className="text-[10px] text-[#555570] self-center">排序</span>
          {([
            ["signal", "訊號"],
            ["rsi",    "RSI"],
            ["foreign","外資"],
            ["score",  "分數"],
          ] as [SortKey, string][]).map(([k, label]) => (
            <button key={k} onClick={() => handleSort(k)}
              className={[
                "text-[10px] font-bold px-2 py-1 rounded border transition-colors",
                sortBy === k
                  ? "border-[#ffd700] text-[#ffd700] bg-[#ffd70015]"
                  : "border-[#2e2e50] text-[#555570] hover:border-[#ffd700]",
              ].join(" ")}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Main split pane ───────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: stock list */}
        <aside className="w-72 shrink-0 border-r border-[#2e2e50] flex flex-col overflow-hidden bg-[#0d0d14]">
          <div className="flex-1 overflow-y-auto">
            {loading && (
              <div className="space-y-px pt-1">
                {[...Array(12)].map((_, i) => (
                  <div key={i} className="mx-3 my-1 h-14 bg-[#1a1a2e] rounded-lg animate-pulse" />
                ))}
              </div>
            )}
            {!loading && stocks.length === 0 && (
              <div className="flex flex-col items-center justify-center h-full gap-3 text-center p-6">
                <div className="text-4xl">🇹🇼</div>
                <p className="text-sm text-white font-bold">無資料</p>
                <p className="text-xs text-[#8888aa]">
                  執行 TWS 掃描後資料會出現：
                </p>
                <pre className="text-[10px] text-[#00e676] bg-[#111128] border border-[#2e2e50] rounded px-3 py-2 text-left">
                  python tws/taiwan_trending.py
                </pre>
              </div>
            )}
            {stocks.map(s => (
              <StockRow
                key={s.ticker}
                stock={s}
                selected={selected?.ticker === s.ticker}
                onClick={() => setSelected(s)}
              />
            ))}
          </div>
        </aside>

        {/* Right: detail panel */}
        <div className="flex-1 overflow-hidden bg-[#0d0d14]">
          {selected ? (
            <DetailPanel
              ticker={selected.ticker}
              period={period}
              onPeriodChange={setPeriod}
            />
          ) : (
            <div className="flex flex-col items-center justify-center h-full gap-4 text-center">
              <div className="text-6xl">🇹🇼</div>
              <p className="text-white font-bold text-lg">選擇股票查看詳情</p>
              <p className="text-[#8888aa] text-sm">左側清單點選任意股票</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
