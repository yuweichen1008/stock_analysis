import type { NewsItem, PcrHistoryResponse, RelatedResponse } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { next: { revalidate: 0 } });
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

export const newsFeed = (
  market = "all",
  hours = 12,
  limit = 50,
  offset = 0
): Promise<NewsItem[]> =>
  get(`/api/news/feed?market=${market}&hours=${hours}&limit=${limit}&offset=${offset}`);

export const pcrHistory = (id: number): Promise<PcrHistoryResponse> =>
  get(`/api/news/${id}/pcr-history`);

export const relatedNews = (id: number): Promise<RelatedResponse> =>
  get(`/api/news/${id}/related`);

export const subscribeTelegram = async (
  telegram_id: string,
  label?: string
): Promise<{ ok: boolean; status: string }> => {
  const res = await fetch(`${BASE}/api/subscribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ telegram_id, label: label || null }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Subscribe failed");
  }
  return res.json();
};

export const unsubscribeTelegram = async (telegram_id: string): Promise<void> => {
  const res = await fetch(`${BASE}/api/subscribe/${encodeURIComponent(telegram_id)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Unsubscribe failed");
};
