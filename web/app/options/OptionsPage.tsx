"use client";

import { useEffect, useState } from "react";
import {
  ComposedChart, Line, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ReferenceLine, ResponsiveContainer,
} from "recharts";
import type {
  OptionsSignalItem,
  OptionsScreenerResponse,
  OptionsHistoryResponse,
  OptionsOverview,
} from "@/lib/types";
import { optionsScreener, optionsHistory, optionsOverview } from "@/lib/api";
import PcrBar from "@/components/PcrBar";
import PcrLabel from "@/components/PcrLabel";

// ── Filter types ──────────────────────────────────────────────────────────────
type SigFilter = "all" | "buy_signal" | "sell_signal" | "unusual_activity";
type RsiZone   = "all" | "oversold" | "overbought";

// ── Helpers ───────────────────────────────────────────────────────────────────
function pcrColor(label: string | null): string {
  if (!label) return "#8888aa";
  if (label.includes("extreme_fear"))   return "#ff5252";
  if (label.includes("fear"))           return "#ff8a65";
  if (label.includes("extreme_greed"))  return "#00e676";
  if (label.includes("greed"))          return "#69f0ae";
  return "#8888aa";
}

function fmtSnap(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("en-US", {
    month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit",
  });
}

// ── Sub-components ────────────────────────────────────────────────────────────

function OverviewBar({ ov }: { ov: OptionsOverview }) {
  return (
    <div className="flex flex-wrap items-center gap-4 px-4 py-2 bg-[#111128] border-b border-[#2e2e50] text-xs text-[#8888aa]">
      {ov.vix != null && (
        <span>
          VIX <span className="text-white font-bold">{ov.vix.toFixed(1)}</span>
        </span>
      )}
      {ov.market_pcr != null && (
        <span>
          Mkt PCR <span className="font-bold" style={{ color: pcrColor(null) }}>{ov.market_pcr.toFixed(2)}</span>
        </span>
      )}
      <span className="text-[#00e676]">🟢 {ov.buy_count} buy</span>
      <span className="text-[#ff5252]">🔴 {ov.sell_count} sell</span>
      <span className="text-yellow-400">⚡ {ov.unusual_count} unusual</span>
      {ov.snapshot_at && (
        <span className="ml-auto text-[#555570]">as of {fmtSnap(ov.snapshot_at)}</span>
      )}
    </div>
  );
}

function SignalTypeBadge({ type }: { type: OptionsSignalItem["signal_type"] }) {
  if (!type) return null;
  const map: Record<string, [string, string, string]> = {
    buy_signal:        ["🟢", "#00e676", "rgba(0,230,118,0.1)"],
    sell_signal:       ["🔴", "#ff5252", "rgba(255,82,82,0.1)"],
    unusual_activity:  ["⚡", "#ffd740", "rgba(255,215,64,0.1)"],
  };
  const [icon, color, bg] = map[type] ?? ["?", "#8888aa", "transparent"];
  const label = type.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
  return (
    <span
      className="text-xs font-bold px-2 py-0.5 rounded-full border"
      style={{ color, borderColor: color, backgroundColor: bg }}
    >
      {icon} {label}
    </span>
  );
}

function ScoreBadge({ score }: { score: number | null }) {
  if (score == null) return null;
  const color = score >= 7 ? "#00e676" : score >= 4 ? "#ffd740" : "#ff8a65";
  return (
    <span className="text-xs font-bold tabular-nums" style={{ color }}>
      {score.toFixed(1)}
    </span>
  );
}

function RsiMeter({ rsi }: { rsi: number | null }) {
  if (rsi == null) return <span className="text-xs text-[#555570]">RSI —</span>;
  const pct = Math.round(rsi);
  const color = rsi < 30 ? "#ff5252" : rsi > 70 ? "#00e676" : "#8888aa";
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-xs text-[#555570]">RSI</span>
      <div className="relative w-16 h-1.5 rounded-full bg-[#2e2e50]">
        {/* zones */}
        <div className="absolute left-0 top-0 h-full w-[30%] rounded-l-full bg-[#ff5252]/20" />
        <div className="absolute right-0 top-0 h-full w-[30%] rounded-r-full bg-[#00e676]/20" />
        {/* dot */}
        <div
          className="absolute top-1/2 -translate-y-1/2 w-2 h-2 rounded-full border border-[#0d0d14]"
          style={{ left: `calc(${pct}% - 4px)`, backgroundColor: color }}
        />
      </div>
      <span className="text-xs font-bold tabular-nums" style={{ color }}>
        {rsi.toFixed(1)}
      </span>
    </div>
  );
}

function IvRankBadge({ rank }: { rank: number | null }) {
  if (rank == null)
    return <span className="text-xs px-1.5 py-0.5 rounded bg-[#2e2e50] text-[#555570]">IV —</span>;
  const [label, color, bg] =
    rank < 25
      ? ["Low IV",  "#448aff", "rgba(68,138,255,0.15)"]
      : rank < 50
      ? ["Mid IV",  "#8888aa", "rgba(136,136,170,0.15)"]
      : ["High IV", "#ff8a65", "rgba(255,138,101,0.15)"];
  return (
    <span
      className="text-xs font-bold px-1.5 py-0.5 rounded"
      style={{ color, backgroundColor: bg }}
    >
      {label} {rank.toFixed(0)}
    </span>
  );
}

function SignalListRow({
  item,
  selected,
  onSelect,
}: {
  item: OptionsSignalItem;
  selected: boolean;
  onSelect: (item: OptionsSignalItem) => void;
}) {
  return (
    <button
      onClick={() => onSelect(item)}
      className={[
        "w-full text-left px-4 py-3 border-b border-[#2e2e50] transition-colors",
        selected ? "bg-[#1a2744]" : "hover:bg-[#1a1a2e]",
      ].join(" ")}
    >
      <div className="flex items-center gap-2 mb-1.5">
        <SignalTypeBadge type={item.signal_type} />
        <span className="font-bold text-white">{item.ticker}</span>
        <ScoreBadge score={item.signal_score} />
        {item.price != null && (
          <span className="text-xs text-[#8888aa] ml-auto">${item.price.toFixed(2)}</span>
        )}
      </div>
      <div className="flex items-center gap-3 flex-wrap">
        <RsiMeter rsi={item.rsi_14} />
        {item.pcr_label && (
          <PcrLabel label={item.pcr_label} />
        )}
        <IvRankBadge rank={item.iv_rank} />
      </div>
    </button>
  );
}

function StatCard({
  label, value, sub, color,
}: {
  label: string; value: string; sub?: string; color?: string;
}) {
  return (
    <div className="bg-[#1a1a2e] border border-[#2e2e50] rounded-xl p-3">
      <p className="text-[10px] text-[#555570] uppercase tracking-wide mb-1">{label}</p>
      <p className="text-base font-bold" style={{ color: color ?? "white" }}>{value}</p>
      {sub && <p className="text-[10px] text-[#8888aa] mt-0.5 capitalize">{sub}</p>}
    </div>
  );
}

function RsiPcrChart({ history }: { history: OptionsSignalItem[] }) {
  if (history.length === 0) return null;
  const data = [...history]
    .reverse()
    .map((h) => ({
      date: fmtSnap(h.snapshot_at),
      rsi:  h.rsi_14 != null ? +h.rsi_14.toFixed(1) : null,
      pcr:  h.pcr    != null ? +h.pcr.toFixed(2)    : null,
    }));

  return (
    <div className="bg-[#1a1a2e] border border-[#2e2e50] rounded-xl p-4 mb-6">
      <p className="text-xs text-[#8888aa] font-bold uppercase mb-3">RSI(14) + PCR History</p>
      <ResponsiveContainer width="100%" height={200}>
        <ComposedChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#2e2e50" />
          <XAxis dataKey="date" tick={{ fill: "#555570", fontSize: 10 }} tickLine={false} />
          <YAxis yAxisId="rsi" domain={[0, 100]} tick={{ fill: "#8888aa", fontSize: 10 }} tickLine={false} width={28} />
          <YAxis yAxisId="pcr" orientation="right" domain={[0, 2.5]} tick={{ fill: "#8888aa", fontSize: 10 }} tickLine={false} width={28} />
          <Tooltip
            contentStyle={{ backgroundColor: "#1a1a2e", border: "1px solid #2e2e50", borderRadius: 8, fontSize: 11 }}
            labelStyle={{ color: "#8888aa" }}
          />
          <Legend wrapperStyle={{ fontSize: 11, color: "#8888aa" }} />
          <ReferenceLine yAxisId="rsi" y={30} stroke="#ff5252" strokeDasharray="4 2" label={{ value: "30", fill: "#ff5252", fontSize: 9 }} />
          <ReferenceLine yAxisId="rsi" y={70} stroke="#00e676" strokeDasharray="4 2" label={{ value: "70", fill: "#00e676", fontSize: 9 }} />
          <Line
            yAxisId="rsi"
            type="monotone"
            dataKey="rsi"
            stroke="#448aff"
            strokeWidth={2}
            dot={{ r: 3, fill: "#448aff" }}
            name="RSI(14)"
            connectNulls
          />
          <Bar
            yAxisId="pcr"
            dataKey="pcr"
            fill="#ff8a6566"
            name="PCR"
            radius={[3, 3, 0, 0]}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function OptionsPage() {
  const [data,       setData]       = useState<OptionsScreenerResponse | null>(null);
  const [overview,   setOverview]   = useState<OptionsOverview | null>(null);
  const [loading,    setLoading]    = useState(true);
  const [sigFilter,  setSigFilter]  = useState<SigFilter>("all");
  const [rsiZone,    setRsiZone]    = useState<RsiZone>("all");
  const [selected,   setSelected]   = useState<OptionsSignalItem | null>(null);
  const [history,    setHistory]    = useState<OptionsHistoryResponse | null>(null);
  const [histLoading,setHistLoading]= useState(false);

  useEffect(() => {
    Promise.all([
      optionsScreener(true, 100),
      optionsOverview(),
    ])
      .then(([d, ov]) => { setData(d); setOverview(ov); })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const handleSelect = async (item: OptionsSignalItem) => {
    setSelected(item);
    setHistory(null);
    setHistLoading(true);
    try {
      setHistory(await optionsHistory(item.ticker));
    } catch { /* non-fatal */ } finally {
      setHistLoading(false);
    }
  };

  const filtered = (data?.signals ?? []).filter((s) => {
    if (sigFilter !== "all" && s.signal_type !== sigFilter) return false;
    if (rsiZone === "oversold"  && (s.rsi_14 == null || s.rsi_14 >= 35)) return false;
    if (rsiZone === "overbought"&& (s.rsi_14 == null || s.rsi_14 <= 65)) return false;
    return true;
  });

  return (
    <div className="flex flex-col h-full">
      {/* Overview bar */}
      {overview && <OverviewBar ov={overview} />}

      <div className="flex flex-1 overflow-hidden">
        {/* ── Left pane ──────────────────────────────────────────────────── */}
        <aside className="w-80 shrink-0 flex flex-col border-r border-[#2e2e50] overflow-hidden">
          <div className="px-4 py-3 border-b border-[#2e2e50] space-y-2">
            <div className="flex items-center justify-between">
              <h2 className="font-bold text-sm text-[#8888aa] uppercase tracking-wide">
                Options Signals
              </h2>
              {data && (
                <span className="text-xs text-[#555570]">
                  {data.count} signals
                </span>
              )}
            </div>

            {/* Signal type filter */}
            <div className="flex gap-1 flex-wrap">
              {(["all", "buy_signal", "sell_signal", "unusual_activity"] as SigFilter[]).map((f) => {
                const labels: Record<SigFilter, string> = {
                  all:               "All",
                  buy_signal:        "🟢 Buy",
                  sell_signal:       "🔴 Sell",
                  unusual_activity:  "⚡ Unusual",
                };
                return (
                  <button
                    key={f}
                    onClick={() => setSigFilter(f)}
                    className={[
                      "text-xs px-2 py-0.5 rounded-full border transition-colors",
                      sigFilter === f
                        ? "border-[#448aff] text-[#448aff] bg-[#1a2744]"
                        : "border-[#2e2e50] text-[#8888aa] hover:border-[#448aff]",
                    ].join(" ")}
                  >
                    {labels[f]}
                  </button>
                );
              })}
            </div>

            {/* RSI zone filter */}
            <div className="flex gap-1">
              {(["all", "oversold", "overbought"] as RsiZone[]).map((z) => (
                <button
                  key={z}
                  onClick={() => setRsiZone(z)}
                  className={[
                    "text-xs px-2 py-0.5 rounded-full border transition-colors",
                    rsiZone === z
                      ? "border-[#448aff] text-[#448aff] bg-[#1a2744]"
                      : "border-[#2e2e50] text-[#8888aa] hover:border-[#448aff]",
                  ].join(" ")}
                >
                  {z === "all" ? "All RSI" : z === "oversold" ? "RSI < 35" : "RSI > 65"}
                </button>
              ))}
            </div>
          </div>

          {/* Signal list */}
          <div className="flex-1 overflow-y-auto">
            {loading && (
              <p className="text-[#8888aa] text-sm text-center p-8">Loading…</p>
            )}
            {!loading && data?.count === 0 && (
              <div className="flex flex-col items-center justify-center gap-4 text-center px-6 py-10">
                <div className="text-4xl">📊</div>
                <p className="text-white font-bold text-sm">No options signals yet</p>
                <p className="text-[#8888aa] text-xs max-w-[220px]">
                  The screener hasn&apos;t run yet. Seed the DB locally:
                </p>
                <code className="bg-[#0d0d14] text-[#00e676] text-xs px-3 py-2 rounded border border-[#2e2e50] font-mono text-left leading-5">
                  OPTIONS_DRY_RUN=true{"\n"}python options_screener_pipeline.py
                </code>
                <p className="text-[#555570] text-xs">
                  Or wait for the 09:45 AM / 3:30 PM ET cron.
                </p>
              </div>
            )}
            {!loading && data != null && data.count > 0 && filtered.length === 0 && (
              <p className="text-[#555570] text-xs text-center p-8">
                No signals match the current filter
              </p>
            )}
            {filtered.map((s) => (
              <SignalListRow
                key={s.id}
                item={s}
                selected={selected?.id === s.id}
                onSelect={handleSelect}
              />
            ))}
          </div>
        </aside>

        {/* ── Right pane ─────────────────────────────────────────────────── */}
        <div className="flex-1 overflow-y-auto p-6">
          {!selected && !loading && (
            <div className="flex items-center justify-center h-full text-[#555570]">
              Select a signal to view details
            </div>
          )}

          {selected && (
            <div className="max-w-2xl">
              {/* Title */}
              <div className="flex items-center gap-3 mb-6 flex-wrap">
                <SignalTypeBadge type={selected.signal_type} />
                <h1 className="text-3xl font-extrabold">{selected.ticker}</h1>
                <ScoreBadge score={selected.signal_score} />
                <IvRankBadge rank={selected.iv_rank} />
              </div>

              {/* Stats grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
                {selected.price != null && (
                  <StatCard label="Price" value={`$${selected.price.toFixed(2)}`}
                    sub={selected.price_change_1d != null
                      ? `${selected.price_change_1d > 0 ? "+" : ""}${selected.price_change_1d.toFixed(2)}% today`
                      : undefined}
                  />
                )}
                <StatCard
                  label="RSI(14)"
                  value={selected.rsi_14 != null ? selected.rsi_14.toFixed(1) : "—"}
                  color={
                    selected.rsi_14 == null ? "#8888aa"
                    : selected.rsi_14 < 30 ? "#ff5252"
                    : selected.rsi_14 > 70 ? "#00e676"
                    : "#8888aa"
                  }
                />
                {selected.pcr != null && (
                  <StatCard
                    label="PCR"
                    value={selected.pcr.toFixed(2)}
                    sub={selected.pcr_label?.replace(/_/g, " ") ?? ""}
                    color={pcrColor(selected.pcr_label)}
                  />
                )}
                <StatCard
                  label="IV Rank"
                  value={selected.iv_rank != null ? `${selected.iv_rank.toFixed(0)}` : "—"}
                  sub={selected.avg_iv != null ? `Avg IV ${(selected.avg_iv * 100).toFixed(1)}%` : undefined}
                  color={
                    selected.iv_rank == null ? "#8888aa"
                    : selected.iv_rank < 25 ? "#448aff"
                    : selected.iv_rank < 50 ? "#8888aa"
                    : "#ff8a65"
                  }
                />
                {selected.volume_oi_ratio != null && (
                  <StatCard
                    label="Vol / OI"
                    value={`${selected.volume_oi_ratio.toFixed(1)}x`}
                    color={selected.volume_oi_ratio > 3 ? "#ffd740" : "#8888aa"}
                  />
                )}
                {selected.total_oi != null && (
                  <StatCard
                    label="Open Interest"
                    value={(selected.total_oi / 1000).toFixed(0) + "K"}
                  />
                )}
                <StatCard label="Score" value={selected.signal_score?.toFixed(1) ?? "—"} />
                <StatCard label="As of" value={fmtSnap(selected.snapshot_at)} />
              </div>

              {/* Signal reason */}
              {selected.signal_reason && (
                <div className="bg-[#1a1a2e] border border-[#2e2e50] rounded-xl px-4 py-3 mb-6">
                  <p className="text-[10px] text-[#555570] uppercase tracking-wide mb-1">Signal Reason</p>
                  <p className="text-sm font-mono text-[#8888aa]">{selected.signal_reason}</p>
                </div>
              )}

              {/* PCR bar */}
              {selected.put_volume != null && selected.call_volume != null && (
                <div className="bg-[#1a1a2e] border border-[#2e2e50] rounded-xl p-4 mb-6">
                  <p className="text-xs text-[#8888aa] font-bold uppercase mb-2">Put / Call Volume</p>
                  <PcrBar
                    putVolume={selected.put_volume}
                    callVolume={selected.call_volume}
                    pcr={selected.pcr}
                  />
                </div>
              )}

              {/* RSI + PCR chart */}
              {histLoading && (
                <p className="text-[#8888aa] text-sm mb-4">Loading history…</p>
              )}
              {history && history.history.length > 0 && (
                <RsiPcrChart history={history.history} />
              )}

              {/* History table */}
              <div className="bg-[#1a1a2e] border border-[#2e2e50] rounded-xl p-4">
                <p className="text-xs text-[#8888aa] font-bold uppercase mb-3">
                  Signal History — {selected.ticker}
                </p>
                {!histLoading && history && history.history.length === 0 && (
                  <p className="text-[#555570] text-sm">No prior signals found</p>
                )}
                {history && history.history.length > 0 && (
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-[#555570] text-left text-xs uppercase">
                        <th className="pb-2">Date</th>
                        <th className="pb-2">RSI</th>
                        <th className="pb-2">PCR</th>
                        <th className="pb-2">IV Rank</th>
                        <th className="pb-2">Signal</th>
                        <th className="pb-2">Score</th>
                      </tr>
                    </thead>
                    <tbody>
                      {history.history.map((h) => (
                        <tr key={h.id} className="border-t border-[#2e2e50]">
                          <td className="py-1.5 text-[#8888aa] text-xs">{fmtSnap(h.snapshot_at)}</td>
                          <td className="py-1.5">
                            <span style={{ color: h.rsi_14 == null ? "#555570" : h.rsi_14 < 30 ? "#ff5252" : h.rsi_14 > 70 ? "#00e676" : "#8888aa" }}>
                              {h.rsi_14?.toFixed(1) ?? "—"}
                            </span>
                          </td>
                          <td className="py-1.5">
                            {h.pcr != null
                              ? <span style={{ color: pcrColor(h.pcr_label) }}>{h.pcr.toFixed(2)}</span>
                              : "—"}
                          </td>
                          <td className="py-1.5">
                            <IvRankBadge rank={h.iv_rank} />
                          </td>
                          <td className="py-1.5">
                            <SignalTypeBadge type={h.signal_type} />
                          </td>
                          <td className="py-1.5">
                            <ScoreBadge score={h.signal_score} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
