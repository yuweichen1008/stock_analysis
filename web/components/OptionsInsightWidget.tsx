"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { OptionsSignalItem } from "@/lib/types";
import { optionsOverview } from "@/lib/api";

const SIGNAL_CONFIG = {
  buy_signal:       { label: "Buy Signal",      emoji: "📈", color: "#00e676", bg: "#00e67620" },
  sell_signal:      { label: "Sell Signal",      emoji: "📉", color: "#ff5252", bg: "#ff525220" },
  unusual_activity: { label: "Unusual Activity", emoji: "⚡", color: "#ffd700", bg: "#ffd70020" },
} as const;

function SkeletonCard() {
  return (
    <div className="min-w-0 flex-1 bg-[#1a1a2e] border border-[#2e2e50] rounded-xl p-3 animate-pulse">
      <div className="h-5 w-16 bg-[#2e2e50] rounded mb-2" />
      <div className="h-4 w-24 bg-[#2e2e50] rounded mb-3" />
      <div className="h-3 w-20 bg-[#2e2e50] rounded mb-1" />
      <div className="h-3 w-16 bg-[#2e2e50] rounded mb-1" />
      <div className="h-3 w-18 bg-[#2e2e50] rounded" />
    </div>
  );
}

function SignalCard({ item }: { item: OptionsSignalItem }) {
  const type = item.signal_type ?? "unusual_activity";
  const cfg = SIGNAL_CONFIG[type] ?? SIGNAL_CONFIG.unusual_activity;

  return (
    <div className="min-w-0 flex-1 bg-[#1a1a2e] border border-[#2e2e50] rounded-xl p-3 flex flex-col gap-1.5">
      <span className="text-base font-extrabold text-white leading-none">{item.ticker}</span>

      <span
        className="inline-flex items-center gap-1 text-[11px] font-bold px-2 py-0.5 rounded-full w-fit"
        style={{ color: cfg.color, backgroundColor: cfg.bg }}
      >
        {cfg.emoji} {cfg.label}
      </span>

      {item.signal_score != null && (
        <p className="text-[11px] text-[#8888aa]">
          Score <span className="text-white font-bold">{item.signal_score.toFixed(1)}</span>
          <span className="text-[#555570]"> / 10</span>
        </p>
      )}

      {item.rsi_14 != null && (
        <p className="text-[11px] text-[#8888aa]">
          RSI <span className="text-white font-bold">{item.rsi_14.toFixed(1)}</span>
        </p>
      )}

      {item.iv_rank != null && (
        <p className="text-[11px] text-[#8888aa]">
          IVR <span className="text-white font-bold">{item.iv_rank.toFixed(0)}</span>
        </p>
      )}
    </div>
  );
}

export default function OptionsInsightWidget() {
  const [signals, setSignals] = useState<OptionsSignalItem[] | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchSignals = () => {
    setLoading(true);
    optionsOverview()
      .then(data => setSignals(data.top_signals.slice(0, 3)))
      .catch(() => setSignals([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchSignals();
    const id = setInterval(fetchSignals, 300_000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="shrink-0 px-4 py-3 border-b border-[#2e2e50] bg-[#0d0d14]">
      <div className="flex items-center justify-between mb-2.5">
        <h3 className="text-xs font-bold text-[#8888aa] uppercase tracking-wide">Options Insights</h3>
        <Link
          href="/options"
          className="text-[11px] font-semibold text-[#7c5cfc] hover:text-[#8f72ff] transition-colors"
        >
          View all →
        </Link>
      </div>

      {loading ? (
        <div className="flex gap-3">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : signals && signals.length > 0 ? (
        <div className="flex gap-3">
          {signals.map(item => (
            <SignalCard key={item.id} item={item} />
          ))}
        </div>
      ) : (
        <p className="text-xs text-[#555570] py-2">
          No signals today — check back after market hours.
        </p>
      )}
    </div>
  );
}
