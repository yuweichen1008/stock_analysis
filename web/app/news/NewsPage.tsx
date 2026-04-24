"use client";

import { useState } from "react";
import type { NewsItem, PcrHistoryResponse, RelatedResponse } from "@/lib/types";
import { pcrHistory, relatedNews } from "@/lib/api";
import NewsFeed from "@/components/NewsFeed";
import PcrChart from "@/components/PcrChart";
import PcrLabel from "@/components/PcrLabel";
import PcrBar from "@/components/PcrBar";
import SentimentBadge from "@/components/SentimentBadge";
import { formatDistanceToNow, parseISO } from "date-fns";

export default function NewsPage() {
  const [selected,  setSelected]  = useState<NewsItem | null>(null);
  const [pcrData,   setPcrData]   = useState<PcrHistoryResponse | null>(null);
  const [relData,   setRelData]   = useState<RelatedResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const handleSelect = async (item: NewsItem) => {
    setSelected(item);
    setDetailLoading(true);
    setPcrData(null);
    setRelData(null);
    try {
      const [pcr, rel] = await Promise.all([
        pcrHistory(item.id),
        relatedNews(item.id),
      ]);
      setPcrData(pcr);
      setRelData(rel);
    } catch {
      // non-fatal
    } finally {
      setDetailLoading(false);
    }
  };

  const timeAgo = selected
    ? (() => {
        try { return formatDistanceToNow(parseISO(selected.published_at), { addSuffix: true }); }
        catch { return ""; }
      })()
    : "";

  const hasRealPcr = selected?.market === "US" && selected?.pcr != null;

  return (
    <div className="flex h-full">
      {/* Left pane — news list */}
      <div className="w-full max-w-sm shrink-0 border-r border-[#2e2e50] overflow-hidden flex flex-col">
        <NewsFeed selectedId={selected?.id ?? null} onSelect={handleSelect} />
      </div>

      {/* Right pane — detail */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
        {!selected && (
          <div className="flex h-full items-center justify-center text-[#555570] text-sm">
            ← Select a news item to see PCR details
          </div>
        )}

        {selected && (
          <>
            {/* Header */}
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2 text-sm text-[#8888aa]">
                <span className="font-bold text-white text-base">{selected.ticker ?? "Market"}</span>
                {selected.source && <span>· {selected.source}</span>}
                <span>· {timeAgo}</span>
                {selected.url && (
                  <a
                    href={selected.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="ml-auto text-accent hover:underline text-xs"
                  >
                    View article ↗
                  </a>
                )}
              </div>
              <h2 className="text-xl font-semibold text-white leading-snug">
                {selected.headline}
              </h2>
            </div>

            {/* PCR summary bar */}
            {hasRealPcr ? (
              <div className="rounded-xl border border-[#2e2e50] bg-[#1a1a2e] p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-white">Put/Call Ratio</span>
                  <PcrLabel label={selected.pcr_label} />
                </div>
                <PcrBar
                  putVolume={selected.put_volume}
                  callVolume={selected.call_volume}
                  pcr={selected.pcr}
                />
                <p className="text-xs text-[#8888aa]">
                  PCR &gt; 1.0 = elevated put buying (fear/hedging). PCR &lt; 0.5 = complacency (greed).
                </p>
              </div>
            ) : (
              <div className="rounded-xl border border-[#2e2e50] bg-[#1a1a2e] p-4 space-y-2">
                <span className="text-sm font-semibold text-white">Sentiment Proxy</span>
                <div className="flex items-center gap-2">
                  <SentimentBadge
                    label={selected.sentiment_label as "positive" | "neutral" | "negative"}
                    score={selected.sentiment_score}
                  />
                  <span className="text-xs text-[#8888aa]">
                    (PCR unavailable for TW stocks — using VADER sentiment)
                  </span>
                </div>
              </div>
            )}

            {/* PCR Timeline chart */}
            {detailLoading && (
              <div className="text-[#8888aa] text-sm">Loading PCR history…</div>
            )}
            {pcrData && (
              <div className="rounded-xl border border-[#2e2e50] bg-[#1a1a2e] p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-white">PCR Timeline</span>
                  <span className="text-xs text-[#8888aa]">
                    {pcrData.snapshots.length} snapshot{pcrData.snapshots.length !== 1 ? "s" : ""}
                  </span>
                </div>
                <PcrChart snapshots={pcrData.snapshots} />
              </div>
            )}

            {/* Related news */}
            {relData && relData.related.length > 0 && (
              <div className="space-y-3">
                <h3 className="text-sm font-semibold text-[#8888aa] uppercase tracking-wide">
                  Related News ({relData.related.length})
                </h3>
                {relData.related.map((rel) => (
                  <button
                    key={rel.id}
                    onClick={() => handleSelect(rel)}
                    className="w-full text-left rounded-lg border border-[#2e2e50] bg-[#1a1a2e] p-3 hover:border-accent/50 transition-colors space-y-1"
                  >
                    <div className="flex items-center gap-2 text-xs text-[#8888aa]">
                      {rel.ticker && <span className="font-bold text-white">{rel.ticker}</span>}
                      {rel.source && <span>· {rel.source}</span>}
                      {rel.pcr_label && <PcrLabel label={rel.pcr_label} />}
                    </div>
                    <p className="text-sm text-white line-clamp-2">{rel.headline}</p>
                  </button>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
