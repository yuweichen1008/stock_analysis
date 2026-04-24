"use client";

const CONFIG: Record<string, { text: string; bg: string; color: string; emoji: string }> = {
  extreme_fear:  { text: "Extreme Fear",  bg: "#3b0a0a", color: "#ef4444", emoji: "😱" },
  fear:          { text: "Fear",          bg: "#2d1010", color: "#f87171", emoji: "😨" },
  neutral:       { text: "Neutral",       bg: "#1f2937", color: "#9ca3af", emoji: "😐" },
  greed:         { text: "Greed",         bg: "#052e16", color: "#4ade80", emoji: "😀" },
  extreme_greed: { text: "Extreme Greed", bg: "#022c22", color: "#22c55e", emoji: "🤑" },
};

export default function PcrLabel({ label }: { label: string | null }) {
  if (!label) return null;
  const cfg = CONFIG[label] ?? CONFIG.neutral;
  return (
    <span
      className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-semibold"
      style={{ background: cfg.bg, color: cfg.color }}
    >
      {cfg.emoji} {cfg.text}
    </span>
  );
}
