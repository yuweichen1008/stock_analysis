export interface NewsItem {
  id:                  number;
  ticker:              string | null;
  market:              string;
  headline:            string;
  source:              string | null;
  url:                 string | null;
  published_at:        string;
  sentiment_score:     number | null;
  sentiment_label:     "positive" | "neutral" | "negative";
  pcr:                 number | null;
  pcr_label:           string | null;
  put_volume:          number | null;
  call_volume:         number | null;
  pcr_snapshot_count:  number;
  related_count:       number;
}

export interface PcrSnapshot {
  snapshot_at:  string;
  pcr:          number | null;
  pcr_label:    string | null;
  put_volume:   number | null;
  call_volume:  number | null;
}

export interface PcrHistoryResponse {
  news_id:   number;
  ticker:    string | null;
  snapshots: PcrSnapshot[];
}

export interface RelatedResponse {
  news_id: number;
  related: NewsItem[];
}

export type MarketFilter = "all" | "US" | "TW" | "MARKET";

export interface WeeklySignalItem {
  id:          number;
  ticker:      string;
  week_ending: string;
  return_pct:  number;
  signal_type: "buy" | "sell" | null;
  last_price:  number | null;
  pcr:         number | null;
  pcr_label:   string | null;
  put_volume:  number | null;
  call_volume: number | null;
  executed:    boolean;
  order_side:  string | null;
  order_qty:   number | null;
}

export interface WeeklySignalsResponse {
  week_ending: string;
  count:       number;
  signals:     WeeklySignalItem[];
}

export interface WeeklyHistoryResponse {
  ticker:  string;
  history: WeeklySignalItem[];
}

export interface OptionsSignalItem {
  id:               number;
  ticker:           string;
  snapshot_at:      string;
  price:            number | null;
  price_change_1d:  number | null;
  rsi_14:           number | null;
  pcr:              number | null;
  pcr_label:        string | null;
  put_volume:       number | null;
  call_volume:      number | null;
  avg_iv:           number | null;
  iv_rank:          number | null;
  total_oi:         number | null;
  volume_oi_ratio:  number | null;
  signal_type:      "buy_signal" | "sell_signal" | "unusual_activity" | null;
  signal_score:     number | null;
  signal_reason:    string | null;
  executed:         boolean;
  created_at:       string;
}

export interface OptionsScreenerResponse {
  snapshot_at: string | null;
  count:       number;
  signals:     OptionsSignalItem[];
}

export interface OptionsHistoryResponse {
  ticker:  string;
  history: OptionsSignalItem[];
}

export interface OptionsOverview {
  vix:           number | null;
  market_pcr:    number | null;
  buy_count:     number;
  sell_count:    number;
  unusual_count: number;
  top_signals:   OptionsSignalItem[];
  snapshot_at:   string | null;
}

export interface DbStatus {
  options_signals:  number;
  iv_snapshots:     number;
  latest_snapshot:  string | null;
  seeded:           boolean;
}

// ── TWS Stock Management ──────────────────────────────────────────────────────

export interface TwsStock {
  ticker:         string;
  name:           string | null;
  industry:       string | null;
  pe_ratio:       string | null;
  roe:            string | null;
  dividend_yield: string | null;
  debt_to_equity: string | null;
  is_signal:      boolean;
  category:       string | null;
  score:          number | null;
  price:          number | null;
  MA120:          number | null;
  MA20:           number | null;
  RSI:            number | null;
  bias:           number | null;
  vol_ratio:      number | null;
  foreign_net:    number | null;
  f5:             number | null;
  f20:            number | null;
  f60:            number | null;
  f_zscore:       number | null;
  short_interest: number | null;
  news_sentiment: number | null;
  last_date:      string | null;
  error?:         string;
  source?:        string;   // "db_cache" | "universe_snapshot" | "yfinance"
}

export interface TwsUniverse {
  stocks:           TwsStock[];
  total:            number;
  count:            number;
  signal_count:     number;
  high_value_count: number;
  last_updated:     string | null;
  sectors:          string[];
}

// ── Charts ────────────────────────────────────────────────────────────────────

export interface OhlcvBar {
  date:   string;
  open:   number;
  high:   number;
  low:    number;
  close:  number;
  volume: number;
  ma20:   number | null;
  ma50:   number | null;
}

export interface OhlcvResponse {
  ticker:       string;
  market:       string;
  period:       string;
  bars:         OhlcvBar[];
  latest_close: number | null;
  latest_date:  string | null;
  source:       string;
  error?:       string;
}

// ── Backtesting ───────────────────────────────────────────────────────────────

export interface OptionsBtGroup {
  trades:          number;
  wins:            number;
  losses:          number;
  win_rate_pct:    number;
  avg_return_pct:  number;
  sharpe:          number | null;
}

export interface OptionsBacktestResult {
  buy_signal?:  OptionsBtGroup;
  sell_signal?: OptionsBtGroup;
  combined?:    OptionsBtGroup;
  error?:       string;
}

export interface BacktestTrade {
  ticker:         string;
  entry_date:     string;
  exit_date:      string;
  entry_price:    number;
  exit_price:     number;
  profit_pct:     number;
  net_profit_pct: number;
  exit_reason:    string;
  signal_rsi:     number;
  signal_bias:    number;
  signal_score:   number;
}

export interface SignalsBacktestSummary {
  total_trades:      number;
  wins:              number;
  losses:            number;
  win_rate:          number;
  avg_profit_pct:    number;
  total_profit:      number;
  sharpe:            number;
  max_drawdown:      number;
  stop_loss_exits:   number;
  take_profit_exits: number;
  time_exits:        number;
}

export interface SignalsBacktestResult {
  summary:        SignalsBacktestSummary;
  trades:         BacktestTrade[];
  equity_curve:   Array<{ date: string; equity: number }>;
  tickers_tested: number;
  error?:         string;
}

// ── Broker / Trading ──────────────────────────────────────────────────────────

export interface BrokerStatus {
  broker:      string;
  configured:  boolean;
  dry_run:     boolean;
  connected:   boolean;
}

export interface BrokerBalance {
  cash:           number;
  total_value:    number;
  unrealized_pnl: number;
  currency:       string;
}

export interface Position {
  ticker:    string;
  qty:       number;
  avg_cost:  number;
  mkt_value: number;
  pnl:       number;
}

export interface BrokerOrder {
  date:   string;
  ticker: string;
  side:   string;
  qty:    number;
  price:  number;
  status: string;
}

export interface AccountSnapshot {
  date:           string;
  total_value:    number | null;
  cash:           number | null;
  unrealized_pnl: number | null;
  currency:       string | null;
}

export interface OptionsContract {
  code:     string;
  expiry:   string;
  strike:   number;
  type:     string;   // "CALL" | "PUT"
  bid:      number;
  ask:      number;
  last:     number;
  volume:   number;
  open_int: number;
  iv:       number;
  delta:    number;
}

export interface OptionsChainResponse {
  ticker:    string;
  expiry:    string | null;
  contracts: OptionsContract[];
}

export interface TradeRow {
  id:              number;
  broker:          string;
  ticker:          string;
  market:          string;
  side:            "buy" | "sell";
  qty:             number;
  order_type:      string | null;
  limit_price:     number | null;
  broker_order_id: string | null;
  status:          "pending" | "filled" | "cancelled" | "rejected";
  filled_qty:      number | null;
  filled_price:    number | null;
  commission:      number | null;
  realized_pnl:    number | null;
  signal_source:   string | null;
  executed_at:     string | null;
  created_at:      string;
}
