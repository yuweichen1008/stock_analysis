import type { NewsItem, PcrHistoryResponse, RelatedResponse, WeeklySignalsResponse, WeeklyHistoryResponse, OptionsScreenerResponse, OptionsHistoryResponse, OptionsOverview, DbStatus, BrokerStatus, BrokerBalance, Position, BrokerOrder, TradeRow } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";
const INTERNAL_SECRET = process.env.NEXT_PUBLIC_INTERNAL_SECRET ?? "";

async function get<T>(path: string, headers?: Record<string, string>): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    next: { revalidate: 0 },
    headers,
  });
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown, headers?: Record<string, string>): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? `API ${path} → ${res.status}`);
  }
  return res.json() as Promise<T>;
}

const brokerHeaders = () => ({ "X-Internal-Secret": INTERNAL_SECRET });

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

// ── Broker / Trading ──────────────────────────────────────────────────────────

export const brokerStatus    = (): Promise<BrokerStatus>  => get("/api/broker/status", brokerHeaders());
export const brokerBalance   = (): Promise<BrokerBalance> => get("/api/broker/balance", brokerHeaders());
export const brokerPositions = (): Promise<Position[]>    => get("/api/broker/positions", brokerHeaders());
export const brokerOrders    = (days = 7): Promise<BrokerOrder[]> =>
  get(`/api/broker/orders?days=${days}`, brokerHeaders());
export const brokerTrades    = (params?: { limit?: number; ticker?: string; status?: string; days?: number }): Promise<TradeRow[]> => {
  const p = new URLSearchParams();
  if (params?.limit)  p.set("limit",  String(params.limit));
  if (params?.ticker) p.set("ticker", params.ticker);
  if (params?.status) p.set("status", params.status);
  if (params?.days)   p.set("days",   String(params.days));
  return get(`/api/broker/trades?${p}`, brokerHeaders());
};
export const brokerTickerTrades = (ticker: string): Promise<{ ticker: string; count: number; trades: TradeRow[] }> =>
  get(`/api/broker/trades/${encodeURIComponent(ticker)}`, brokerHeaders());
export const brokerPlaceOrder = (body: {
  ticker: string; side: string; qty: number; limit_price: number; signal_source?: string;
}): Promise<{ trade: TradeRow; message: string; dry_run: boolean }> =>
  post("/api/broker/order", body, brokerHeaders());
