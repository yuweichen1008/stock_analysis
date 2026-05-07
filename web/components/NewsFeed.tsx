"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { MarketFilter as MarketFilterType, NewsItem } from "@/lib/types";
import { newsFeed } from "@/lib/api";
import NewsCard from "./NewsCard";
import MarketFilter from "./MarketFilter";

const PAGE = 30;
const AUTO_REFRESH_MS = 5 * 60 * 1000; // 5 min

interface Props {
  selectedId: number | null;
  onSelect:   (item: NewsItem) => void;
}

export default function NewsFeed({ selectedId, onSelect }: Props) {
  const [items,    setItems]    = useState<NewsItem[]>([]);
  const [market,   setMarket]   = useState<MarketFilterType>("all");
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState<string | null>(null);
  const [offset,   setOffset]   = useState(0);
  const [hasMore,  setHasMore]  = useState(true);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async (reset: boolean, mkt: MarketFilterType) => {
    try {
      if (reset) setLoading(true);
      const off = reset ? 0 : offset;
      const data = await newsFeed(mkt, 12, PAGE, off);
      setItems((prev) => reset ? data : [...prev, ...data]);
      setOffset(off + data.length);
      setHasMore(data.length === PAGE);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load news");
    } finally {
      setLoading(false);
    }
  }, [offset]);

  // Initial + market-change load
  useEffect(() => {
    setOffset(0);
    setHasMore(true);
    load(true, market);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [market]);

  // Auto-refresh
  useEffect(() => {
    timerRef.current = setInterval(() => load(true, market), AUTO_REFRESH_MS);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [market]);

  return (
    <div className="flex flex-col h-full">
      {/* Filter bar */}
      <div className="shrink-0 px-4 py-3 border-b border-[#2e2e50]">
        <MarketFilter value={market} onChange={(v) => setMarket(v)} />
      </div>

      {/* Scrollable list */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
        {loading && items.length === 0 && (
          <div className="text-center text-[#8888aa] py-12 text-sm">Loading news…</div>
        )}
        {error && (
          <div className="text-center text-red-400 py-6 text-sm">{error}</div>
        )}
        {items.map((item) => (
          <NewsCard
            key={item.id}
            item={item}
            selected={item.id === selectedId}
            onClick={() => onSelect(item)}
          />
        ))}
        {hasMore && !loading && (
          <button
            onClick={() => load(false, market)}
            className="w-full py-3 text-sm text-[#8888aa] hover:text-white transition-colors"
          >
            Load more
          </button>
        )}
      </div>
    </div>
  );
}
