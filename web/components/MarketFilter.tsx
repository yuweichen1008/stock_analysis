"use client";

import clsx from "clsx";
import type { MarketFilter } from "@/lib/types";

const OPTIONS: { value: MarketFilter; label: string }[] = [
  { value: "all",    label: "All" },
  { value: "US",     label: "🇺🇸 US" },
  { value: "TW",     label: "🇹🇼 TW" },
  { value: "MARKET", label: "📊 Market" },
];

interface Props {
  value:    MarketFilter;
  onChange: (v: MarketFilter) => void;
}

export default function MarketFilter({ value, onChange }: Props) {
  return (
    <div className="flex gap-2">
      {OPTIONS.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={clsx(
            "rounded-full px-3 py-1 text-sm font-medium transition-colors",
            value === opt.value
              ? "bg-accent text-white"
              : "bg-[#1a1a2e] text-[#8888aa] hover:text-white border border-[#2e2e50]"
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
