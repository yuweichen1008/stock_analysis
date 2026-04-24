"use client";

interface Props {
  label:  "positive" | "neutral" | "negative";
  score?: number | null;
}

const CONFIG = {
  positive: { text: "Positive",  color: "#22c55e", bg: "#052e16" },
  neutral:  { text: "Neutral",   color: "#9ca3af", bg: "#1f2937" },
  negative: { text: "Negative",  color: "#ef4444", bg: "#3b0a0a" },
};

export default function SentimentBadge({ label, score }: Props) {
  const cfg = CONFIG[label] ?? CONFIG.neutral;
  return (
    <span
      className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium"
      style={{ background: cfg.bg, color: cfg.color }}
    >
      {cfg.text}
      {score != null && (
        <span className="opacity-70">({score > 0 ? "+" : ""}{score.toFixed(2)})</span>
      )}
    </span>
  );
}
