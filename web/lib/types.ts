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
