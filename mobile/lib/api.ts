import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';
import Constants from 'expo-constants';

export const API_BASE: string =
  (Constants.expoConfig?.extra?.apiBase as string | undefined) ?? 'http://localhost:8080';

const api = axios.create({ baseURL: API_BASE, timeout: 15000 });

// ── JWT request interceptor ────────────────────────────────────────────────
api.interceptors.request.use(async (config) => {
  const token = await AsyncStorage.getItem('oracle_auth_token');
  if (token) {
    config.headers = config.headers ?? {};
    config.headers['Authorization'] = `Bearer ${token}`;
  }
  return config;
});

// ── 401 → logout ──────────────────────────────────────────────────────────
api.interceptors.response.use(
  r => r,
  async (error) => {
    if (error?.response?.status === 401) {
      await AsyncStorage.multiRemove(['oracle_auth_token', 'oracle_user']);
      // The auth store listener will pick this up on next render
    }
    return Promise.reject(error);
  },
);

// ── Types ──────────────────────────────────────────────────────────────────

export interface OracleRow {
  date: string;
  direction: 'Bull' | 'Bear' | null;
  confidence_pct: number | null;
  factors: Record<string, unknown>;
  taiex_open: number | null;
  taiex_close: number | null;
  taiex_change_pts: number | null;
  score_pts: number | null;
  cumulative_score: number | null;
  is_correct: boolean;
  status: 'pending' | 'resolved' | 'no_prediction';
}

export interface LiveData {
  current_level: number | null;
  change_pts: number | null;
  change_pct: number | null;
  last_updated: string | null;
}

export interface OracleStats {
  total: number;
  resolved: number;
  wins: number;
  win_rate_pct: number;
  streak: number;
  cumulative_score: number;
}

export interface UserData {
  id: number;
  device_id: string | null;
  display_name: string;
  coins: number;
  total_bets: number;
  wins: number;
  losses: number;
  win_rate_pct: number;
  today_bet: TodayBet | null;
}

export interface TodayBet {
  direction: 'Bull' | 'Bear';
  amount: number;
  status: 'pending' | 'settled';
  payout: number | null;
}

export interface BetRow {
  date: string;
  direction: 'Bull' | 'Bear';
  amount: number;
  is_correct: boolean | null;
  payout: number | null;
  status: 'pending' | 'settled';
}

export interface LeaderboardRow {
  rank: number;
  id: number;
  device_id: string | null;
  display_name: string;
  coins: number;
  total_bets: number;
  wins: number;
  win_rate: number;
}

export interface SignalRow {
  ticker: string;
  name?: string;
  market?: string;
  score?: number | null;
  price?: number | null;
  RSI?: number | null;
  bias?: number | null;
  category?: string;
  is_signal?: boolean | string;
  [key: string]: unknown;
}

export interface SignalsData {
  signals: SignalRow[];
  watchlist: SignalRow[];
  total: number;
}

export interface WatchlistItem {
  id:       number;
  ticker:   string;
  market:   string;
  notes:    string | null;
  added_at: string | null;
}

export interface PostReactions { bull: number; bear: number; fire: number; }

export interface PostItem {
  id:              number;
  user:            { id: number | null; display_name: string; avatar_url: string | null };
  ticker:          string | null;
  market:          string | null;
  content:         string;
  signal_type:     string | null;
  created_at:      string | null;
  reactions:       PostReactions;
  viewer_reaction: string | null;
}

export interface AuthResponse {
  access_token: string;
  token_type:   string;
  user: {
    id:            number;
    display_name:  string;
    email:         string | null;
    coins:         number;
    avatar_url:    string | null;
    auth_provider: string | null;
  };
}

// ── API namespaces ─────────────────────────────────────────────────────────

export const Oracle = {
  today:   () => api.get<OracleRow>('/api/oracle/today').then(r => r.data),
  live:    () => api.get<LiveData>('/api/oracle/live').then(r => r.data),
  history: (limit = 30) => api.get<OracleRow[]>(`/api/oracle/history?limit=${limit}`).then(r => r.data),
  stats:   () => api.get<OracleStats>('/api/oracle/stats').then(r => r.data),
};

export const Sandbox = {
  register: (device_id: string, nickname?: string) =>
    api.post('/api/sandbox/register', { device_id, nickname }).then(r => r.data),
  // New token-based me endpoint (no path param)
  me: () => api.get<UserData>('/api/sandbox/me').then(r => r.data),
  // Legacy path-param variant (kept for backwards compat)
  meByDevice: (device_id: string) =>
    api.get<UserData>(`/api/sandbox/me/${device_id}`).then(r => r.data),
  bet: (device_id: string, direction: 'Bull' | 'Bear', bet_amount: number) =>
    api.post('/api/sandbox/bet', { device_id, direction, bet_amount }).then(r => r.data),
  history: (device_id: string, limit = 30) =>
    api.get<BetRow[]>(`/api/sandbox/history/${device_id}?limit=${limit}`).then(r => r.data),
  leaderboard: (limit = 50) =>
    api.get<LeaderboardRow[]>(`/api/sandbox/leaderboard?limit=${limit}`).then(r => r.data),
};

export const Notify = {
  register: (device_id: string, expo_token: string) =>
    api.post('/api/notify/register', { device_id, expo_token }).then(r => r.data),
};

export const Signals = {
  tw:     () => api.get<SignalsData>('/api/signals/tw').then(r => r.data),
  us:     () => api.get<SignalsData>('/api/signals/us').then(r => r.data),
  search: (q: string, market = 'all', limit = 20) =>
    api.get<SignalRow[]>(`/api/signals/search?q=${encodeURIComponent(q)}&market=${market}&limit=${limit}`).then(r => r.data),
};

export const Auth = {
  apple:  (identity_token: string, full_name?: string) =>
    api.post<AuthResponse>('/api/auth/apple', { identity_token, full_name }).then(r => r.data),
  google: (id_token: string) =>
    api.post<AuthResponse>('/api/auth/google', { id_token }).then(r => r.data),
  device: (device_id: string, nickname?: string) =>
    api.post<AuthResponse>('/api/auth/device', { device_id, nickname }).then(r => r.data),
};

export const Watchlist = {
  list:    () => api.get<WatchlistItem[]>('/api/watchlist/').then(r => r.data),
  alerts:  () => api.get<SignalRow[]>('/api/watchlist/alerts').then(r => r.data),
  add:     (ticker: string, market: string, notes?: string) =>
    api.post<WatchlistItem>('/api/watchlist/', { ticker, market, notes }).then(r => r.data),
  remove:  (ticker: string, market = 'US') =>
    api.delete(`/api/watchlist/${encodeURIComponent(ticker)}?market=${market}`).then(r => r.data),
};

export const Feed = {
  list:   (market = 'all', limit = 20, offset = 0) =>
    api.get<PostItem[]>(`/api/feed/?market=${market}&limit=${limit}&offset=${offset}`).then(r => r.data),
  create: (content: string, ticker?: string, market?: string, signal_type?: string) =>
    api.post<PostItem>('/api/feed/', { content, ticker, market, signal_type }).then(r => r.data),
  react:  (post_id: number, emoji_type: 'bull' | 'bear' | 'fire') =>
    api.post(`/api/feed/${post_id}/react`, { emoji_type }).then(r => r.data),
};

// ── Stock movers + bets ────────────────────────────────────────────────────

export interface MoverRow {
  ticker:   string;
  name:     string;
  sector:   string;
  price:    number | null;
  change:   number;
  volume:   number;
  rsi:      number | null;
  pe:       number | null;
  category: string;
  score:    number;
}

export interface MoversData {
  top_gainers:  MoverRow[];
  oversold:     MoverRow[];
  high_volume:  MoverRow[];
  all_movers:   MoverRow[];
  cached_at:    string | null;
}

export interface BacktestResult {
  ticker:       string;
  total_trades: number;
  wins:         number;
  losses:       number;
  win_rate:     number;
  avg_return:   number;
  last_signal:  string | null;
}

export interface StockBetRow {
  id:          number;
  ticker:      string;
  date:        string;
  direction:   'Bull' | 'Bear';
  amount:      number;
  entry_price: number | null;
  exit_price:  number | null;
  is_correct:  boolean | null;
  payout:      number | null;
  status:      'pending' | 'settled';
  category:    string | null;
}

export interface StockStats {
  total_bets:   number;
  wins:         number;
  losses:       number;
  win_rate_pct: number;
  total_payout: number;
  by_ticker:    { ticker: string; trades: number; wins: number; win_rate: number; payout: number }[];
}

export const Stocks = {
  movers:   () => api.get<MoversData>('/api/stocks/movers').then(r => r.data),
  backtest: (tickers: string[]) =>
    api.get<{ results: BacktestResult[]; tickers_tested: number }>(
      `/api/stocks/backtest?tickers=${tickers.join(',')}`,
    ).then(r => r.data),
  bet: (device_id: string, ticker: string, direction: 'Bull' | 'Bear', bet_amount: number, category?: string) =>
    api.post('/api/stocks/bet', { device_id, ticker, direction, bet_amount, category }).then(r => r.data),
  history: (device_id: string, limit = 30) =>
    api.get<StockBetRow[]>(`/api/stocks/history/${device_id}?limit=${limit}`).then(r => r.data),
  stats: (device_id: string) =>
    api.get<StockStats>(`/api/stocks/stats/${device_id}`).then(r => r.data),
};

export default api;
