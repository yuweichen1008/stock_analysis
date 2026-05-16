"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ComposedChart, Area, Line, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer, ReferenceLine,
} from "recharts";
import type { OhlcvBar, OhlcvResponse } from "@/lib/types";
import { chartOhlcv } from "@/lib/api";

// ── Types ─────────────────────────────────────────────────────────────────────

type Period = "1mo" | "3mo" | "6mo" | "1y" | "2y";
type Market = "US" | "TW";

interface BandBar {
  date:   string;
  low:    number;
  band:   number;   // high - low (for stacked area)
  close:  number;
  ma20:   number | null;
  ma50:   number | null;
  volume: number;
  isUp:   boolean;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtPrice(v: number | null, market: Market) {
  if (v == null) return "—";
  return market === "TW"
    ? `NT$${v.toLocaleString("zh-TW", { minimumFractionDigits: 2 })}`
    : `$${v.toLocaleString("en-US",  { minimumFractionDigits: 2 })}`;
}

function fmtVol(v: number) {
  if (v >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(1)}B`;
  if (v >= 1_000_000)     return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000)         return `${(v / 1_000).toFixed(0)}K`;
  return String(v);
}

function tickInterval(len: number) {
  if (len <= 22)  return 3;
  if (len <= 65)  return 6;
  if (len <= 130) return 12;
  return Math.ceil(len / 10);
}

// ── Custom tooltip ────────────────────────────────────────────────────────────

function CandleTooltip({ active, payload, market }: {
  active?: boolean;
  payload?: Array<{ payload: BandBar & { high: number; open: number } }>;
  market: Market;
}) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload as any;
  const change = d.close - (d.open ?? d.close);
  const changePct = d.open ? (change / d.open) * 100 : 0;
  return (
    <div className="bg-[#1a1a2e] border border-[#2e2e50] rounded-xl p-3 text-xs shadow-xl">
      <p className="text-[#8888aa] mb-1.5 font-semibold">{d.date}</p>
      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
        {d.open  != null && <><span className="text-[#8888aa]">Open</span><span className="text-right font-bold text-white">{fmtPrice(d.open, market)}</span></>}
        {d.high  != null && <><span className="text-[#8888aa]">High</span><span className="text-right font-bold text-[#00e676]">{fmtPrice(d.high, market)}</span></>}
        {d.low   != null && <><span className="text-[#8888aa]">Low</span><span className="text-right font-bold text-[#ff5252]">{fmtPrice(d.low, market)}</span></>}
        <span className="text-[#8888aa]">Close</span>
        <span className={`text-right font-bold ${changePct >= 0 ? "text-[#00e676]" : "text-[#ff5252]"}`}>
          {fmtPrice(d.close, market)}
        </span>
        <span className="text-[#8888aa]">Change</span>
        <span className={`text-right font-bold ${changePct >= 0 ? "text-[#00e676]" : "text-[#ff5252]"}`}>
          {changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%
        </span>
        {d.volume != null && <><span className="text-[#8888aa]">Volume</span><span className="text-right text-white">{fmtVol(d.volume)}</span></>}
        {d.ma20   != null && <><span className="text-[#8888aa]">MA20</span><span className="text-right text-[#448aff]">{fmtPrice(d.ma20, market)}</span></>}
        {d.ma50   != null && <><span className="text-[#8888aa]">MA50</span><span className="text-right text-[#ffd740]">{fmtPrice(d.ma50, market)}</span></>}
      </div>
    </div>
  );
}

// ── Price change badge ─────────────────────────────────────────────────────────

function PriceBadge({ bars, market }: { bars: OhlcvBar[]; market: Market }) {
  if (bars.length < 2) return null;
  const last  = bars[bars.length - 1];
  const prev  = bars[bars.length - 2];
  const chg   = last.close - prev.close;
  const chgPct = prev.close ? (chg / prev.close) * 100 : 0;
  const up = chg >= 0;
  return (
    <div className="flex items-baseline gap-3">
      <span className="text-2xl font-extrabold text-white">{fmtPrice(last.close, market)}</span>
      <span className={`text-sm font-bold ${up ? "text-[#00e676]" : "text-[#ff5252]"}`}>
        {up ? "▲" : "▼"} {Math.abs(chg).toFixed(2)} ({up ? "+" : ""}{chgPct.toFixed(2)}%)
      </span>
      <span className="text-xs text-[#555570]">{last.date}</span>
    </div>
  );
}

// ── Skeleton loader ────────────────────────────────────────────────────────────

function ChartSkeleton() {
  return (
    <div className="animate-pulse space-y-2">
      <div className="h-80 bg-[#1a1a2e] rounded-xl" />
      <div className="h-24 bg-[#1a1a2e] rounded-xl" />
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ChartsPage() {
  const [ticker,  setTicker]  = useState("AAPL");
  const [input,   setInput]   = useState("AAPL");
  const [market,  setMarket]  = useState<Market>("US");
  const [period,  setPeriod]  = useState<Period>("3mo");
  const [data,    setData]    = useState<OhlcvResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async (t: string, p: Period, m: Market) => {
    setLoading(true);
    setError(null);
    try {
      const res = await chartOhlcv(t, p, m);
      if (res.error) { setError(res.error); setData(null); }
      else setData(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load chart data");
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load
  useEffect(() => { load(ticker, period, market); }, []);

  const handleSearch = () => {
    const t = input.trim().toUpperCase();
    if (!t) return;
    setTicker(t);
    load(t, period, market);
  };

  const handlePeriod = (p: Period) => {
    setPeriod(p);
    load(ticker, p, market);
  };

  const handleMarket = (m: Market) => {
    setMarket(m);
    load(ticker, period, m);
  };

  // Transform bars into band format for Recharts stacked area
  const bars = data?.bars ?? [];
  const bandData: BandBar[] = bars.map(b => ({
    date:   b.date,
    low:    b.low,
    band:   parseFloat((b.high - b.low).toFixed(4)),
    close:  b.close,
    ma20:   b.ma20,
    ma50:   b.ma50,
    volume: b.volume,
    isUp:   b.close >= b.open,
  }));

  const fullData = bars.map((b, i) => ({
    ...bandData[i],
    open: b.open,
    high: b.high,
  }));

  const yMin = bars.length ? Math.min(...bars.map(b => b.low))  * 0.97 : 0;
  const yMax = bars.length ? Math.max(...bars.map(b => b.high)) * 1.03 : 100;
  const volMax = bars.length ? Math.max(...bars.map(b => b.volume)) : 1;
  const interval = tickInterval(bars.length);

  const PERIODS: Period[] = ["1mo", "3mo", "6mo", "1y", "2y"];
  const MARKETS: Market[] = ["US", "TW"];

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {/* Header / search bar */}
      <div className="shrink-0 px-6 py-4 border-b border-[#2e2e50] bg-[#111128]">
        <div className="flex flex-wrap items-center gap-3">
          {/* Ticker input */}
          <div className="flex items-center gap-2">
            <input
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value.toUpperCase())}
              onKeyDown={e => e.key === "Enter" && handleSearch()}
              placeholder="AAPL"
              className="w-28 bg-[#1a1a2e] border border-[#2e2e50] rounded-lg px-3 py-1.5 text-sm text-white placeholder-[#555570] focus:outline-none focus:border-[#448aff]"
            />
            <button
              onClick={handleSearch}
              className="px-3 py-1.5 bg-[#448aff] hover:bg-[#6da3ff] text-white text-sm font-bold rounded-lg transition-colors"
            >
              Go
            </button>
          </div>

          {/* Market toggle */}
          <div className="flex gap-1">
            {MARKETS.map(m => (
              <button
                key={m}
                onClick={() => handleMarket(m)}
                className={[
                  "px-2.5 py-1 text-xs font-bold rounded-md border transition-colors",
                  market === m
                    ? "border-[#448aff] text-[#448aff] bg-[#1a2744]"
                    : "border-[#2e2e50] text-[#8888aa] hover:border-[#448aff]",
                ].join(" ")}
              >
                {m}
              </button>
            ))}
          </div>

          {/* Period pills */}
          <div className="flex gap-1">
            {PERIODS.map(p => (
              <button
                key={p}
                onClick={() => handlePeriod(p)}
                className={[
                  "px-2.5 py-1 text-xs font-bold rounded-md border transition-colors",
                  period === p
                    ? "border-[#ffd740] text-[#ffd740] bg-[#1a1800]"
                    : "border-[#2e2e50] text-[#8888aa] hover:border-[#ffd740]",
                ].join(" ")}
              >
                {p}
              </button>
            ))}
          </div>

          {/* Title */}
          {data && !loading && (
            <div className="ml-2">
              <div className="flex items-center gap-2 mb-0.5">
                <span className="text-lg font-extrabold text-white">{data.ticker}</span>
                <span className="text-xs text-[#555570] border border-[#2e2e50] px-1.5 py-0.5 rounded">{market}</span>
              </div>
              <PriceBadge bars={data.bars} market={market} />
            </div>
          )}
        </div>
      </div>

      {/* Chart area */}
      <div className="flex-1 p-6 space-y-4 min-w-0">
        {loading && <ChartSkeleton />}

        {error && (
          <div className="flex flex-col items-center justify-center py-24 gap-4 text-center">
            <div className="text-5xl">📉</div>
            <p className="text-white font-bold">No chart data</p>
            <p className="text-[#8888aa] text-sm max-w-sm">{error}</p>
          </div>
        )}

        {!loading && !error && bars.length > 0 && (
          <>
            {/* ── Main price chart ─────────────────────────────────────── */}
            <div className="bg-[#111128] border border-[#2e2e50] rounded-xl p-4">
              <div className="flex items-center gap-4 mb-3 text-xs text-[#8888aa]">
                <span className="flex items-center gap-1.5">
                  <span className="inline-block w-3 h-3 rounded-sm bg-[#448aff22] border border-[#448aff55]" />
                  High–Low Range
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="inline-block w-6 h-0.5 bg-[#00e676]" />
                  Close
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="inline-block w-6 h-0.5 bg-[#448aff]" />
                  MA20
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="inline-block w-6 h-0.5 bg-[#ffd740]" />
                  MA50
                </span>
              </div>

              <ResponsiveContainer width="100%" height={360}>
                <ComposedChart data={fullData} margin={{ top: 4, right: 12, left: 4, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e1e38" />
                  <XAxis
                    dataKey="date"
                    tick={{ fill: "#555570", fontSize: 10 }}
                    tickLine={false}
                    axisLine={false}
                    interval={interval}
                  />
                  <YAxis
                    domain={[yMin, yMax]}
                    tick={{ fill: "#8888aa", fontSize: 10 }}
                    tickLine={false}
                    axisLine={false}
                    width={60}
                    tickFormatter={v => market === "TW" ? v.toLocaleString("zh-TW") : `$${v.toFixed(0)}`}
                  />
                  <Tooltip content={<CandleTooltip market={market} />} />

                  {/* High-Low band (stacked area) */}
                  <Area
                    type="monotone"
                    dataKey="low"
                    stackId="band"
                    stroke="none"
                    fill="none"
                    legendType="none"
                    isAnimationActive={false}
                  />
                  <Area
                    type="monotone"
                    dataKey="band"
                    stackId="band"
                    stroke="#448aff"
                    strokeOpacity={0.3}
                    fill="#448aff"
                    fillOpacity={0.12}
                    legendType="none"
                    isAnimationActive={false}
                  />

                  {/* Moving averages */}
                  <Line
                    type="monotone"
                    dataKey="ma20"
                    stroke="#448aff"
                    strokeWidth={1.5}
                    dot={false}
                    connectNulls
                    legendType="none"
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="ma50"
                    stroke="#ffd740"
                    strokeWidth={1.5}
                    dot={false}
                    connectNulls
                    legendType="none"
                    isAnimationActive={false}
                  />

                  {/* Close price */}
                  <Line
                    type="monotone"
                    dataKey="close"
                    stroke="#00e676"
                    strokeWidth={2}
                    dot={false}
                    legendType="none"
                    isAnimationActive={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>

            {/* ── Volume chart ─────────────────────────────────────────── */}
            <div className="bg-[#111128] border border-[#2e2e50] rounded-xl p-4">
              <p className="text-[10px] text-[#555570] uppercase tracking-wide mb-2">Volume</p>
              <ResponsiveContainer width="100%" height={100}>
                <ComposedChart data={fullData} margin={{ top: 0, right: 12, left: 4, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e1e38" vertical={false} />
                  <XAxis
                    dataKey="date"
                    tick={{ fill: "#555570", fontSize: 10 }}
                    tickLine={false}
                    axisLine={false}
                    interval={interval}
                  />
                  <YAxis
                    tick={{ fill: "#555570", fontSize: 9 }}
                    tickLine={false}
                    axisLine={false}
                    width={48}
                    tickFormatter={fmtVol}
                    domain={[0, volMax * 1.1]}
                  />
                  <Tooltip
                    formatter={(v: number) => [fmtVol(v), "Volume"]}
                    contentStyle={{ backgroundColor: "#1a1a2e", border: "1px solid #2e2e50", borderRadius: 8, fontSize: 11 }}
                    labelStyle={{ color: "#8888aa" }}
                  />
                  <Bar
                    dataKey="volume"
                    fill="#448aff"
                    fillOpacity={0.4}
                    radius={[2, 2, 0, 0]}
                    isAnimationActive={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>

            {/* ── Stats row ─────────────────────────────────────────────── */}
            {bars.length > 0 && (() => {
              const last = bars[bars.length - 1];
              const periodHigh = Math.max(...bars.map(b => b.high));
              const periodLow  = Math.min(...bars.map(b => b.low));
              const avgVol = Math.round(bars.reduce((s, b) => s + b.volume, 0) / bars.length);
              return (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {[
                    { label: `${period} High`,   value: fmtPrice(periodHigh, market), color: "#00e676" },
                    { label: `${period} Low`,    value: fmtPrice(periodLow, market),  color: "#ff5252" },
                    { label: "Avg Volume",       value: fmtVol(avgVol) },
                    { label: "Bars",             value: String(bars.length) },
                  ].map(s => (
                    <div key={s.label} className="bg-[#111128] border border-[#2e2e50] rounded-xl p-3">
                      <p className="text-[10px] text-[#555570] uppercase tracking-wide mb-1">{s.label}</p>
                      <p className="text-sm font-bold" style={{ color: s.color ?? "white" }}>{s.value}</p>
                    </div>
                  ))}
                </div>
              );
            })()}
          </>
        )}

        {!loading && !error && bars.length === 0 && (
          <div className="flex flex-col items-center justify-center py-24 gap-4">
            <div className="text-5xl">📈</div>
            <p className="text-white font-bold">Enter a ticker above and press Go</p>
            <p className="text-[#8888aa] text-sm">Try AAPL, TSLA, 2330 (TW)</p>
          </div>
        )}
      </div>
    </div>
  );
}
