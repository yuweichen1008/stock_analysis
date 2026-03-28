# tws — Taiwan Stock Signal Engine

This package contains the full Taiwan stock daily pipeline. It runs as a scheduled task (cron or Cloud Scheduler → Cloud Function) and delivers a Telegram report with candlestick charts for each signal stock.

---

## Pipeline

```
TWSE API
  └─► Top-20 trending tickers  (top20_YYYYMMDD.csv)
        └─► K-line sync via yfinance  (data/ohlcv/)
              └─► Mean-reversion signal filter
                    └─► Institutional flow + short interest (TWSE)
                          └─► News sentiment (Google News + VADER)
                                └─► Ledoit-Wolf 5-day target price
                                      └─► Plotly candlestick chart (PNG)
                                            └─► Telegram report
```

---

## Signal Filter Logic

Hard gates — **all three must pass**:

| Gate | Rule | Notes |
|------|------|-------|
| MA120 (life line) | `price > MA120` | Long-term trend healthy |
| Bias (乖離率) | `bias < -2%` where `bias = (price − MA20) / MA20 × 100` | Meaningful pullback, not noise |
| RSI (Wilder's 14) | `RSI < 35` | Oversold — bounce candidate |

Signal quality score (0–10) for ranking:
- RSI depth below 35 → up to 4 pts
- Bias depth below −2% → up to 3 pts
- Volume ratio ≤ 1.5× avg (calm pullback) → 2 pts; ≤ 2.5× → 1 pt
- Price > 5% above MA120 → 1 pt

Output: `current_trending.csv` sorted by score descending.

---

## Files

| File | Purpose |
|------|---------|
| `taiwan_trending.py` | Signal filter engine — MA120/MA20/RSI/Bias/Volume, Wilder's RSI, score |
| `telegram_notifier.py` | Report builder + Plotly candlestick chart sender |
| `core.py` | `TaiwanStockEngine` — TWSE sync, K-line download, fundamental refresh |
| `models.py` | `StockAI` — Ledoit-Wolf 5-day target price prediction |
| `utils.py` | TWSE fetchers (institutional flow, short interest), VADER sentiment, `TelegramTool` |
| `bq_helper.py` | BigQuery write/query helper (cloud mode only) |
| `cloud_function.py` | GCP Cloud Function HTTP entrypoint — mirrors `master_run.py` + BQ insert |

---

## Running Locally

```bash
# Full daily pipeline
python master_run.py

# Signal filter only (standalone)
python tws/taiwan_trending.py

# Interactive Telegram bot
python app.py
```

---

## GCP Cloud Function Deployment

Entry point: `tws.cloud_function.tws_handler`

The function auto-detects GCF via the `K_SERVICE` environment variable and writes all runtime files to `/tmp/tws` (the only writable path in Cloud Functions).

Required environment variables:

```
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
GCP_PROJECT          # or GOOGLE_CLOUD_PROJECT
BQ_DATASET           # default: tws_dataset
BQ_TABLE             # default: tws_trending
BQ_LOCATION          # default: US
```

Cloud Scheduler trigger: HTTP POST, daily after market close (e.g. `30 7 * * 1-5` UTC for 15:30 Taipei time).

---

## BigQuery Schema

Table: `{GCP_PROJECT}.{BQ_DATASET}.{BQ_TABLE}`

| Column | Type | Description |
|--------|------|-------------|
| run_date | TIMESTAMP | UTC timestamp of the pipeline run |
| ticker | STRING | TWSE ticker code |
| score | FLOAT64 | Signal quality score (0–10) |
| price | FLOAT64 | Last close price |
| MA120 | FLOAT64 | 120-day moving average |
| MA20 | FLOAT64 | 20-day moving average |
| RSI | FLOAT64 | Wilder's 14-period RSI |
| bias | FLOAT64 | (price − MA20) / MA20 × 100 |
| vol_ratio | FLOAT64 | Last-day volume / 20-day avg volume |
| foreign_net | FLOAT64 | Foreign net buy/sell (latest day) |
| f5 / f20 / f60 | FLOAT64 | Rolling foreign flow sums |
| f_zscore | FLOAT64 | 60-day z-score of foreign flow |
| short_interest | FLOAT64 | Daily 借券賣出 shares |
| news_sentiment | FLOAT64 | VADER composite sentiment (−1 to +1) |
| last_date | STRING | Last OHLCV date for the ticker |

Query example:
```python
from tws.bq_helper import BigQueryClient
bq = BigQueryClient()
df = bq.query_trending(days=7)          # last 7 days, all signals
hist = bq.query_ticker_history("2330", days=30)  # single ticker history
```

---

## Security

- Never commit `.env` or service account credentials.
- In GCP, load secrets via Secret Manager and inject as environment variables.
- The `cloud_function.py` HTTP trigger should be protected with Cloud IAP or a secret header check.
