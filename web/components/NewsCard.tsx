"use client";

import clsx from "clsx";
import { formatDistanceToNow, parseISO } from "date-fns";
import type { NewsItem } from "@/lib/types";
import PcrBar from "./PcrBar";
import PcrLabel from "./PcrLabel";
import SentimentBadge from "./SentimentBadge";

const MARKET_COLORS: Record<string, string> = {
  US:     "bg-blue-900 text-blue-300",
  TW:     "bg-red-900  text-red-300",
  MARKET: "bg-gray-800 text-gray-400",
};

interface Props {
  item:     NewsItem;
  selected: boolean;
  onClick:  () => void;
}

export default function NewsCard({ item, selected, onClick }: Props) {
  const timeAgo = (() => {
    try {
      return formatDistanceToNow(parseISO(item.published_at), { addSuffix: true });
    } catch {
      return "";
    }
  })();

  const marketClass = MARKET_COLORS[item.market] ?? MARKET_COLORS.MARKET;
  const hasRealPcr  = item.market === "US" && item.pcr != null;

  return (
    <button
      onClick={onClick}
      className={clsx(
        "w-full text-left rounded-xl border p-4 transition-all space-y-3",
        selected
          ? "border-accent bg-[#1a2744]"
          : "border-[#2e2e50] bg-[#1a1a2e] hover:border-[#448aff]/40"
      )}
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          <span className={clsx("rounded px-1.5 py-0.5 font-semibold", marketClass)}>
            {item.market}
          </span>
          {item.ticker && (
            <span className="font-bold text-white">{item.ticker}</span>
          )}
          {item.source && (
            <span className="text-[#8888aa]">· {item.source}</span>
          )}
        </div>
        <span className="shrink-0 text-xs text-[#555570]">{timeAgo}</span>
      </div>

      {/* Headline */}
      <p className="text-sm font-medium text-white leading-snug line-clamp-2">
        {item.headline}
      </p>

      {/* PCR or sentiment */}
      {hasRealPcr ? (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <PcrLabel label={item.pcr_label} />
          </div>
          <PcrBar
            putVolume={item.put_volume}
            callVolume={item.call_volume}
            pcr={item.pcr}
          />
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <span className="text-xs text-[#555570]">Sentiment proxy:</span>
          <SentimentBadge label={item.sentiment_label} score={item.sentiment_score} />
        </div>
      )}

      {/* Related count */}
      {item.related_count > 0 && (
        <div className="text-xs text-[#8888aa]">
          🔗 {item.related_count} related news
        </div>
      )}
    </button>
  );
}
