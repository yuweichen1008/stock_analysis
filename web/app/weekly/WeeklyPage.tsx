"use client";

import { useEffect, useState } from "react";
import type { WeeklySignalItem, WeeklySignalsResponse, WeeklyHistoryResponse } from "@/lib/types";
import { weeklySignals, weeklyHistory } from "@/lib/api";
import PcrBar from "@/components/PcrBar";

type SignalFilter = "all" | "buy" | "sell";

function pcrLabelColor(label: string | null): string {
  if (!label) return "#8888aa";
  if (label.includes("extreme_fear")) return "#ff5252";
  if (label.includes("fear"))         return "#ff8a65";
  if (label.includes("extreme_greed")) return "#00e676";
  if (label.includes("greed"))        return "#69f0ae";
  return "#8888aa";
}

function RetBadge({ ret }: { ret: number }) {
  const pct = (ret * 100).toFixed(1);
  const pos = ret > 0;
  return (
    <span
      className="text-sm font-bold tabular-nums"
      style={{ color: pos ? "#ff5252" : "#00e676" }}
    >
      {pos ? "+" : ""}{pct}%
    </span>
  );
}

function SignalBadge({ type }: { type: "buy" | "sell" | null }) {
  if (!type) return null;
  const isBuy = type === "buy";
  return (
    <span
      className="text-xs font-bold px-2 py-0.5 rounded-full border"
      style={{
        color:            isBuy ? "#00e676" : "#ff5252",
        borderColor:      isBuy ? "#00e676" : "#ff5252",
        backgroundColor:  isBuy ? "rgba(0,230,118,0.1)" : "rgba(255,82,82,0.1)",
      }}
    >
      {isBuy ? "🟢 BUY" : "🔴 SELL"}
    </span>
  );
}

function SignalRow({
  item,
  selected,
  onSelect,
}: {
  item: WeeklySignalItem;
  selected: boolean;
  onSelect: (item: WeeklySignalItem) => void;
}) {
  return (
    <button
      onClick={() => onSelect(item)}
      className={[
        "w-full text-left px-4 py-3 border-b border-[#2e2e50] transition-colors",
        selected ? "bg-[#1a2744]" : "hover:bg-[#1a1a2e]",
      ].join(" ")}
    >
      <div className="flex items-center gap-2 mb-1">
        <SignalBadge type={item.signal_type} />
        <span className="font-bold text-white">{item.ticker}</span>
        <RetBadge ret={item.return_pct} />
        {item.last_price != null && (
          <span className="text-xs text-[#8888aa] ml-auto">${item.last_price.toFixed(2)}</span>
        )}
      </div>

      {item.pcr != null && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-[#8888aa]">PCR</span>
          <span
            className="text-xs font-bold"
            style={{ color: pcrLabelColor(item.pcr_label) }}
          >
            {item.pcr.toFixed(2)}
          </span>
          {item.pcr_label && (
            <span className="text-xs text-[#555570] capitalize">
              {item.pcr_label.replace(/_/g, " ")}
            </span>
          )}
        </div>
      )}
    </button>
  );
}

export default function WeeklyPage() {
  const [data,    setData]    = useState<WeeklySignalsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter,  setFilter]  = useState<SignalFilter>("all");
  const [selected, setSelected] = useState<WeeklySignalItem | null>(null);
  const [history,  setHistory]  = useState<WeeklyHistoryResponse | null>(null);
  const [histLoading, setHistLoading] = useState(false);

  useEffect(() => {
    weeklySignals()
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const handleSelect = async (item: WeeklySignalItem) => {
    setSelected(item);
    setHistory(null);
    setHistLoading(true);
    try {
      const h = await weeklyHistory(item.ticker);
      setHistory(h);
    } catch {
      // non-fatal
    } finally {
      setHistLoading(false);
    }
  };

  const filtered = (data?.signals ?? []).filter(
    (s) => filter === "all" || s.signal_type === filter
  );

  return (
    <div className="flex h-full">
      {/* ── Left pane ─────────────────────────────────────────────── */}
      <aside className="w-80 shrink-0 flex flex-col border-r border-[#2e2e50] overflow-hidden">
        {/* Header */}
        <div className="px-4 py-3 border-b border-[#2e2e50]">
          <div className="flex items-center justify-between mb-2">
            <h2 className="font-bold text-sm text-[#8888aa] uppercase tracking-wide">
              Weekly ±5% Signals
            </h2>
            {data && (
              <span className="text-xs text-[#555570]">
                {data.week_ending} · {data.count}
              </span>
            )}
          </div>
          {/* Filter pills */}
          <div className="flex gap-2">
            {(["all", "buy", "sell"] as SignalFilter[]).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={[
                  "text-xs px-3 py-1 rounded-full border transition-colors",
                  filter === f
                    ? "border-[#448aff] text-[#448aff] bg-[#1a2744]"
                    : "border-[#2e2e50] text-[#8888aa] hover:border-[#448aff]",
                ].join(" ")}
              >
                {f === "all" ? "All" : f === "buy" ? "🟢 Buy" : "🔴 Sell"}
              </button>
            ))}
          </div>
        </div>

        {/* Signal list */}
        <div className="flex-1 overflow-y-auto">
          {loading && (
            <p className="text-[#8888aa] text-sm text-center p-8">Loading…</p>
          )}
          {!loading && filtered.length === 0 && (
            <p className="text-[#555570] text-sm text-center p-8">
              No signals this week
            </p>
          )}
          {filtered.map((s) => (
            <SignalRow
              key={s.id}
              item={s}
              selected={selected?.id === s.id}
              onSelect={handleSelect}
            />
          ))}
        </div>
      </aside>

      {/* ── Right pane ────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto p-6">
        {!selected && (
          <div className="flex items-center justify-center h-full text-[#555570]">
            Select a signal to view details
          </div>
        )}

        {selected && (
          <div className="max-w-2xl">
            {/* Title */}
            <div className="flex items-center gap-3 mb-6">
              <SignalBadge type={selected.signal_type} />
              <h1 className="text-3xl font-extrabold">{selected.ticker}</h1>
              <RetBadge ret={selected.return_pct} />
            </div>

            {/* Stats grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
              {selected.last_price != null && (
                <StatCard label="Last Price" value={`$${selected.last_price.toFixed(2)}`} />
              )}
              <StatCard
                label="$5 Qty"
                value={
                  selected.last_price && selected.last_price > 0
                    ? (5 / selected.last_price).toFixed(4)
                    : "—"
                }
              />
              <StatCard label="Week Ending" value={selected.week_ending} />
              {selected.pcr != null && (
                <StatCard
                  label="PCR"
                  value={selected.pcr.toFixed(2)}
                  sub={selected.pcr_label?.replace(/_/g, " ") ?? ""}
                  color={pcrLabelColor(selected.pcr_label)}
                />
              )}
            </div>

            {/* PCR bar */}
            {selected.put_volume != null && selected.call_volume != null && (
              <div className="bg-[#1a1a2e] border border-[#2e2e50] rounded-xl p-4 mb-6">
                <p className="text-xs text-[#8888aa] font-bold uppercase mb-2">
                  Put / Call Volume
                </p>
                <PcrBar putVolume={selected.put_volume} callVolume={selected.call_volume} pcr={selected.pcr} />
              </div>
            )}

            {/* History table */}
            <div className="bg-[#1a1a2e] border border-[#2e2e50] rounded-xl p-4">
              <p className="text-xs text-[#8888aa] font-bold uppercase mb-3">
                Signal History — {selected.ticker}
              </p>
              {histLoading && <p className="text-[#8888aa] text-sm">Loading…</p>}
              {history && history.history.length === 0 && (
                <p className="text-[#555570] text-sm">No prior signals found</p>
              )}
              {history && history.history.length > 0 && (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-[#555570] text-left text-xs uppercase">
                      <th className="pb-2">Week</th>
                      <th className="pb-2">Return</th>
                      <th className="pb-2">Signal</th>
                      <th className="pb-2">PCR</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.history.map((h) => (
                      <tr key={h.week_ending} className="border-t border-[#2e2e50]">
                        <td className="py-1.5 text-[#8888aa]">{h.week_ending}</td>
                        <td className="py-1.5"><RetBadge ret={h.return_pct} /></td>
                        <td className="py-1.5"><SignalBadge type={h.signal_type} /></td>
                        <td className="py-1.5">
                          {h.pcr != null ? (
                            <span style={{ color: pcrLabelColor(h.pcr_label) }}>
                              {h.pcr.toFixed(2)}
                            </span>
                          ) : "—"}
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
  );
}

function StatCard({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: string;
  sub?: string;
  color?: string;
}) {
  return (
    <div className="bg-[#1a1a2e] border border-[#2e2e50] rounded-xl p-3">
      <p className="text-[10px] text-[#555570] uppercase tracking-wide mb-1">{label}</p>
      <p className="text-base font-bold" style={{ color: color ?? "white" }}>
        {value}
      </p>
      {sub && <p className="text-[10px] text-[#8888aa] mt-0.5 capitalize">{sub}</p>}
    </div>
  );
}
