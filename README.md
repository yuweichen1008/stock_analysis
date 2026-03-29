# TWS AI Stock Analyst

Automated stock signal pipeline covering Taiwan (TWSE) and US markets — daily mean-reversion analysis, full-market heatmaps, multi-broker portfolio management, and a personal web trading dashboard.

---

## How It Works

```
TWSE API
  └─► Top-20 trending tickers (daily)
        └─► K-line sync — 250 days via yfinance
              └─► Technical filters (MA120 / MA20 / RSI / Bias)
                    └─► Institutional flow + short interest (TWSE)
                          └─► News sentiment (Google News + VADER)
                                └─► Ledoit-Wolf target price prediction
                                      └─► Telegram report + charts

TWSE MI_INDEX (full market ~1068 stocks)
  └─► Industry heatmap (Plotly Treemap, 4000×2400 px)
        └─► Top-3 sector zoom charts
              └─► Investment intel — limit-up news, near-signal watchlist
```

`master_run.py` runs the full TWS + US pipelines in sequence.
Designed to be triggered daily by cron or Google Cloud Scheduler.

---

## Signal Logic (Mean Reversion)

A stock passes the filter only when **all three** conditions are met simultaneously:

| Condition | Rule | Interpretation |
|-----------|------|----------------|
| MA120 (life line) | `price > MA120` | Long-term uptrend intact |
| Bias (pullback) | `bias < −2%` | Price ≥ 2% below MA20 |
| RSI (14-period, Wilder's) | `RSI < 35` | Short-term oversold — bounce likely |

**Signal score (0–10):** RSI depth (4 pts) + Bias depth (3 pts) + volume quality (2 pts) + MA120 margin (1 pt). Higher score = cleaner setup.

---

## Features

### Signal Pipeline
- **Daily top-20 sync** — TWSE official trending list; cold-start fallback to curated seed list
- **250-day OHLCV** — per-ticker K-lines stored in `data/ohlcv/`; thread-safe parallel download
- **Wilder's RSI** — exponential smoothing (`ewm(alpha=1/14, adjust=False)`) matching TradingView
- **Institutional flow** — 外資 rolling 5/20/60-day sums + z-score anomaly detection (TWSE API)
- **Short interest** — daily 借券賣出 data from TWSE
- **News sentiment** — Google News RSS scored with VADER + Chinese keyword fallback
- **Ledoit-Wolf prediction** — shrinkage covariance for stable 5-day target price
- **Fundamental enrichment** — ROE, PE, debt ratio, dividend yield, analyst target (90-day auto-refresh)
- **Universe snapshot** — `universe_snapshot.csv` tracks all ever-scanned tickers with latest metrics

### Telegram Reports
- **Signal board** — horizontal RSI bar chart; all tracked tickers color-coded (🟢 signal / 🟠 watch / 🔴 below MA120)
- **Buy list message** — actionable table: ticker · price · RSI · Bias% · score · vol ratio · foreign flow · sentiment
- **TWSE Market Map** — full 1068-stock heatmap (red/green % change, log-scaled volume tiles, 4000×2400 px sent as document)
- **Sector zoom charts** — focused heatmap for top-3 sectors by trading value
- **Investment intelligence** — limit-up stocks with latest news, near-signal watchlist, sector momentum, intra-day trade idea

### US Pipeline
- S&P 500 tickers from Wikipedia; same mean-reversion filters applied
- Signal output to `data_us/current_trending.csv`

### Broker Integration (IBKR · Moomoo · Robinhood)
- Unified `BrokerClient` interface — connect, get_positions, get_balance, get_orders, place_order
- **IBKR**: `ib_insync` — TWS/IB Gateway; supports VWAP / TWAP / ADAPTIVE execution algos
- **Moomoo**: `moomoo-api` — OpenD daemon; US + HK markets; SIMULATE and REAL modes
- **Robinhood**: `robin_stocks` — REST API; no local daemon required
- Graceful degradation — unconfigured/unreachable brokers are skipped silently
- **Telegram commands**: `/balance` · `/positions` · `/orders [days]`

### Web Dashboard (Streamlit)
- Password-protected personal dashboard (`bcrypt` + `streamlit-authenticator`)
- **Overview** — balance cards, total portfolio value, allocation pie chart, P&L by position
- **Positions** — merged holdings across all brokers enriched with PE/ROE/target price
- **Trading** — manual order form (broker · ticker · side · qty · algo) + strategy execution tab
- **Signals** — Taiwan & US signal tables with one-click "⚡ Trade" button
- **Backtest** — equity curve, per-ticker win rate, full trade log

---

## Project Structure

```
stock_analysis/
├── master_run.py              # Daily pipeline (TWS + US) — cron entry point
├── app.py                     # Interactive Telegram bot
├── backtester.py              # Mean-reversion backtesting engine
├── requirements.txt
├── .env                       # Secrets (see .env.example)
├── .env.example               # Template — Telegram + broker credentials
│
├── tws/
│   ├── core.py                # TaiwanStockEngine — sync & fundamental refresh
│   ├── taiwan_trending.py     # Signal filter: apply_filters(), run_taiwan_trending()
│   ├── telegram_notifier.py   # Report builder + all Telegram senders
│   │                          #   generate_signal_board()     RSI bar chart
│   │                          #   generate_market_heatmap()   1068-stock map
│   │                          #   generate_sector_zoom()      per-sector map
│   │                          #   build_investment_intel()    news + watchlist
│   │                          #   send_market_overview()      daily market summary
│   │                          #   send_stock_report()         signal buy list
│   ├── models.py              # StockAI — Ledoit-Wolf prediction
│   ├── utils.py               # TWSE fetchers, sentiment, TelegramTool, fetch_twse_all_prices()
│   ├── bq_helper.py           # BigQuery write helper (cloud mode)
│   └── cloud_function.py      # Google Cloud Function entry point
│
├── us/
│   ├── core.py                # USStockEngine — S&P 500 sync
│   └── us_trending.py         # US signal filter (reuses apply_filters)
│
├── brokers/
│   ├── base.py                # BrokerClient ABC
│   ├── ibkr.py                # Interactive Brokers (ib_insync)
│   ├── moomoo.py              # Moomoo/Futu (moomoo-api)
│   ├── robinhood.py           # Robinhood (robin_stocks)
│   ├── manager.py             # BrokerManager — aggregator + order router
│   └── strategies.py          # MeanReversionExecutor, ManualOrderExecutor
│
├── dashboard/
│   ├── app.py                 # Streamlit entry point + auth gate
│   ├── auth.py                # streamlit-authenticator wrapper
│   ├── config.yaml            # Hashed password config (gitignored)
│   ├── data_helpers.py        # Cached data loaders, broker manager singleton
│   └── pages/
│       ├── 1_Overview.py      # Portfolio summary across all brokers
│       ├── 2_Positions.py     # Holdings table + industry chart
│       ├── 3_Trading.py       # Order form + strategy execution
│       ├── 4_Signals.py       # Today's TW + US signal stocks
│       └── 5_Backtest.py      # Backtest runner + equity curve
│
├── data/
│   ├── ohlcv/                 # Per-ticker OHLCV CSVs (250 days)
│   ├── tickers/               # Daily top-20 lists (top20_YYYYMMDD.csv)
│   └── company/
│       ├── company_mapping.csv    # Fundamentals snapshot
│       ├── company_history.csv    # Point-in-time fundamental log
│       └── universe_snapshot.csv  # All-time scanned tickers + latest metrics
│
├── data_us/                   # US OHLCV + signal output
└── tests/
    └── test_taiwan_trending.py  # 19 tests: RSI, filters, score, bias
```

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Required for the daily pipeline:
```
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_channel_or_chat_id
```

Optional — add only the broker(s) you use:
```
# IBKR (requires TWS or IB Gateway running)
IBKR_HOST=127.0.0.1
IBKR_PORT=7497          # 7497=paper TWS · 7496=live TWS · 4002=live Gateway
IBKR_CLIENT_ID=1

# Moomoo (requires OpenD daemon running)
MOOMOO_HOST=127.0.0.1
MOOMOO_PORT=11111
MOOMOO_TRADE_ENV=SIMULATE   # or REAL

# Robinhood (no daemon needed)
ROBINHOOD_USERNAME=your@email.com
ROBINHOOD_PASSWORD=yourpassword
```

### 3. Run

| Mode | Command | Description |
|------|---------|-------------|
| Daily scan | `python master_run.py` | TWS + US sync → filter → enrich → Telegram |
| Interactive bot | `python app.py` | Telegram query bot + broker commands |
| Web dashboard | `streamlit run dashboard/app.py --server.address=127.0.0.1` | Personal trading UI |
| Backtest | `python backtester.py` | Replay strategy on historical data |

### 4. Dashboard first-time setup

Generate a bcrypt password hash (one-time):

```bash
python3 -c "
import bcrypt, getpass
pw = getpass.getpass('Dashboard password: ')
print(bcrypt.hashpw(pw.encode(), bcrypt.gensalt(12)).decode())
"
```

Paste the hash into `dashboard/config.yaml` under `credentials.usernames.admin.password`.

### 5. Cron example (daily at 15:30 Taiwan time, Mon–Fri)

```cron
30 15 * * 1-5  cd /path/to/stock_analysis && python master_run.py >> logs/run.log 2>&1
```

---

## Algorithm Insights

### Mean Reversion Signal

The strategy exploits temporary dislocations in stocks with confirmed long-term strength. MA120 acts as a health gate — only stocks above their 120-day average qualify. Within that subset, Bias and RSI identify short-term exhaustion points where a bounce is statistically likely.

### Wilder's RSI

Uses exponential smoothing with `alpha = 1/window` and `adjust=False` — the same method as TradingView and most professional charting platforms. The simpler SMA-seeded RSI produces materially different values near extreme readings.

### Ledoit-Wolf Shrinkage Estimator

Raw sample covariance matrices are noisy when observations are few relative to assets. Ledoit-Wolf shrinks the sample covariance toward a structured target, producing a more stable risk estimate. The model derives an expected 5-day return and computes:

```
target_price = current_price × (1 + expected_gain)
```

### Institutional Flow Z-Score

Foreign net buy/sell figures (外資) are normalized into a z-score over a 60-day rolling window. Z-score > +2 signals unusual accumulation; < −2 signals unusual distribution — a demand-side complement to the technical signal.

### TWSE Market Heatmap

Fetches all ~1068 regular-stock closing prices from `TWSE MI_INDEX?type=ALL`. Tile size is log-scaled by trading value (prevents TSMC from dominating). Sent as a Telegram document (no compression) at 4000×2400 px so users can pinch-zoom to any sector.

---

## Telegram Commands

| Command | Description |
|---------|-------------|
| Send a 4-digit code | Look up fundamentals + AI target price for any TWS ticker |
| `/balance` | Account cash + net value across all connected brokers |
| `/positions` | Open holdings across all connected brokers |
| `/orders [days]` | Recent order history (default: last 7 days) |

---

## Roadmap

- [x] **Milestone 1** — Core data engine, TWSE auto-sync, Telegram interaction, point-in-time history log
- [x] **Milestone 2** — Plotly charts, Bias factor, Wilder's RSI, signal score (0–10), full-market heatmap, signal board, sector zoom, investment intelligence
- [x] **Milestone 3** — Backtester: equity curve, win rate, Sharpe ratio, max drawdown
- [x] **Milestone 4** — US pipeline (S&P 500) + broker integration (IBKR · Moomoo · Robinhood) + personal trading dashboard
- [ ] **Milestone 5** — LSTM / Transformer deep-learning price prediction

---

## Contributing

Pull requests are welcome. Open an issue first for significant feature changes.
