import axios from 'axios';
import Constants from 'expo-constants';

export const API_BASE: string =
  (Constants.expoConfig?.extra?.apiBase as string | undefined) ?? 'http://localhost:8000';

const api = axios.create({ baseURL: API_BASE, timeout: 10000 });

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
  device_id: string;
  nickname: string | null;
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
  device_id: string;
  nickname: string;
  coins: number;
  total_bets: number;
  wins: number;
  win_rate: number;
}

export interface SignalRow {
  ticker: string;
  name?: string;
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

// ── API calls ──────────────────────────────────────────────────────────────

export const Oracle = {
  today:   () => api.get<OracleRow>('/api/oracle/today').then(r => r.data),
  live:    () => api.get<LiveData>('/api/oracle/live').then(r => r.data),
  history: (limit = 30) => api.get<OracleRow[]>(`/api/oracle/history?limit=${limit}`).then(r => r.data),
  stats:   () => api.get<OracleStats>('/api/oracle/stats').then(r => r.data),
};

export const Sandbox = {
  register: (device_id: string, nickname?: string) =>
    api.post('/api/sandbox/register', { device_id, nickname }).then(r => r.data),
  me: (device_id: string) =>
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
  tw: () => api.get<SignalsData>('/api/signals/tw').then(r => r.data),
  us: () => api.get<SignalsData>('/api/signals/us').then(r => r.data),
};

export default api;
