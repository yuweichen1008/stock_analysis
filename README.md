# TWS AI Stock Analyst

Automated Taiwan stock signal pipeline — fetch TWSE top-20, run multi-factor analysis, and deliver a daily report to Telegram subscribers.

---

## How It Works

```
TWSE API
  └─► Top-20 trending tickers (daily)
        └─► K-line sync (250 days via yfinance)
              └─► Technical filters (MA120 / MA20 / RSI)
                    └─► Institutional flow + short interest (TWSE)
                          └─► News sentiment (Google News + VADER)
                                └─► Ledoit-Wolf target price prediction
                                      └─► Telegram report + industry chart
```

`master_run.py` runs all four steps in sequence. Designed to be triggered daily by cron or Google Cloud Scheduler.

---

## Signal Logic (Mean Reversion)

A stock passes the filter only when **all three** conditions are met:

| Condition | Rule | Interpretation |
|-----------|------|----------------|
| MA120 (life line) | `price > MA120` | Long-term trend is healthy |
| MA20 (short-term) | `price < MA20` | Short-term pullback in progress |
| RSI (14-period) | `RSI < 35` | Oversold — potential bounce point |

The combination identifies stocks in a long-term uptrend that have pulled back to an oversold level — a classic mean-reversion day-trading setup.

---

## Features

- **Daily top-20 sync** — fetches TWSE official trending list each market day; falls back to a curated seed list on cold start
- **250-day K-line history** — per-ticker OHLCV downloaded via yfinance, stored in `data/ohlcv/`
- **Technical filters** — MA120 / MA20 / RSI mean-reversion signal
- **Institutional flow** — foreign buy/sell (外資) rolling 5/20/60-day sums + z-score anomaly detection
- **Short interest** — daily 借券賣出 data from TWSE
- **News sentiment** — Google News RSS headlines scored with VADER (+ Chinese keyword fallback)
- **Ledoit-Wolf AI prediction** — shrinkage covariance estimator for stable 5-day target price
- **Fundamental enrichment** — ROE, PE, debt ratio, dividend yield, analyst target price (90-day auto-refresh)
- **Telegram report** — formatted markdown per stock + Plotly candlestick chart per signal stock
- **Industry signal map** — Finviz-style treemap (tile size = score, color = signal strength, grouped by sector) pushed to Telegram
- **Point-in-time logging** — `company_history.csv` records every fundamental update for future backtesting
- **Google Cloud support** — `tws/cloud_function.py` deploys as an HTTP function; results stored in BigQuery

---

## Project Structure

```
stock_analysis/
├── master_run.py              # Daily pipeline entry point (cron / cloud scheduler)
├── app.py                     # Interactive Telegram bot (long-running daemon)
├── backtester.py              # Strategy backtesting framework
├── requirements.txt
├── .env                       # TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
├── data/
│   ├── ohlcv/                 # Per-ticker OHLCV CSVs (250 days)
│   ├── tickers/               # Daily top-20 lists  (top20_YYYYMMDD.csv)
│   └── company/               # Fundamental snapshots + history log
└── tws/
    ├── core.py                # TaiwanStockEngine — sync & fundamental refresh
    ├── taiwan_trending.py     # Signal filter engine (MA / RSI / Bias)
    ├── telegram_notifier.py   # Report builder + Telegram sender
    ├── models.py              # StockAI — Ledoit-Wolf prediction
    ├── utils.py               # TWSE fetchers, sentiment, Telegram tool
    ├── bq_helper.py           # BigQuery write helper (cloud mode)
    └── cloud_function.py      # Google Cloud Function entry point
```

---

## Setup

**1. Install dependencies**

```bash
pip install -r requirements.txt
```

**2. Configure environment**

Create a `.env` file in the project root:

```
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_channel_or_chat_id
```

**3. Run**

| Mode | Command | Description |
|------|---------|-------------|
| Daily scan | `python master_run.py` | Sync → filter → enrich → report |
| Interactive bot | `python app.py` | Long-running Telegram query assistant |
| Backtest | `python backtester.py` | Replay strategy on historical data |

**4. Cron example** (run daily at 15:30 Taiwan time)

```cron
30 15 * * 1-5  cd /path/to/stock_analysis && python master_run.py
```

---

## Algorithm Insights

### Mean Reversion Signal

The strategy exploits temporary dislocations in stocks with confirmed long-term strength. The MA120 acts as a health gate — only stocks trading above their 120-day average qualify. Within that subset, MA20 and RSI identify short-term exhaustion points where a bounce is statistically likely.

### Ledoit-Wolf Shrinkage Estimator

Raw sample covariance matrices are noisy with few observations relative to the number of assets. Ledoit-Wolf shrinks the sample covariance toward a structured target matrix, producing a more stable estimate of portfolio risk. The model uses this to derive an expected 5-day return and compute a target price:

```
target_price = current_price × (1 + expected_gain)
```

### Institutional Flow Z-Score

Foreign net buy/sell figures are normalized into a z-score over a 60-day rolling window. A z-score above +2 signals unusual accumulation; below −2 signals unusual distribution. This supplements the technical signal with a demand-side view.

---

## Roadmap

- [x] **Milestone 1** — Core data engine, TWSE auto-sync, Telegram interaction, point-in-time history log
- [x] **Milestone 2** — Plotly candlestick charts via Telegram + Bias (乖離率) factor + Wilder's RSI + signal score (0–10)
- [ ] **Milestone 3** — Backtester: replay signal history, compute win rate & Sharpe ratio
- [ ] **Milestone 4** — US stock day-trading module (SPY/QQQ sector analysis + broker integration)
- [ ] **Milestone 5** — LSTM / Transformer deep-learning price prediction

---

## Contributing

Pull requests are welcome. Open an issue first for significant feature changes.
