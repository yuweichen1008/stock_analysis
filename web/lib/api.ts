import type { NewsItem, PcrHistoryResponse, RelatedResponse, WeeklySignalsResponse, WeeklyHistoryResponse, OptionsScreenerResponse, OptionsHistoryResponse, OptionsOverview, DbStatus } from "./types";

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

export const weeklySignals = (
  signalOnly = true,
  limit = 200,
  week = ""
): Promise<WeeklySignalsResponse> =>
  get(
    `/api/weekly/signals?signal_only=${signalOnly}&limit=${limit}${week ? `&week=${encodeURIComponent(week)}` : ""}`
  );

export const weeklyHistory = (ticker: string): Promise<WeeklyHistoryResponse> =>
  get(`/api/weekly/signals/${encodeURIComponent(ticker)}/history`);

export const optionsScreener = (
  signalOnly = true,
  limit = 20,
  signalType = "",
  pcrLabel = "",
  rsiZone = ""
): Promise<OptionsScreenerResponse> => {
  const params = new URLSearchParams({
    signal_only: String(signalOnly),
    limit: String(limit),
    ...(signalType && { signal_type: signalType }),
    ...(pcrLabel   && { pcr_label:   pcrLabel }),
    ...(rsiZone    && { rsi_zone:    rsiZone }),
  });
  return get(`/api/options/screener?${params}`);
};

export const optionsHistory = (ticker: string): Promise<OptionsHistoryResponse> =>
  get(`/api/options/screener/${encodeURIComponent(ticker)}/history`);

export const optionsOverview = (): Promise<OptionsOverview> =>
  get("/api/options/overview");

export const optionsDbStatus = (): Promise<DbStatus> =>
  get("/api/options/db-status");
