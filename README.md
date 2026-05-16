# LokiStock — AI Stock Screener, Options Intelligence & Taiwan/US Trading Dashboard

A multi-platform stock analysis system with a **web dashboard** (lokistock.com), an **iOS app** (LokiStock Oracle), and a **Telegram bot**. Every trading day it scans thousands of Taiwan and US stocks, scores them with a 7-factor model, runs multi-agent AI analysis, tracks **put/call ratios** on market-moving news, and sends automated Telegram reports — all on Google Cloud Run. Live **CTBC** (Taiwan) and **Moomoo** (US) broker integrations let you place orders, view positions, and run options strategies directly from the dashboard.

---

## What It Does

1. **8:00 AM TST** — Predicts TAIEX direction using 5 market signals. Sends Telegram prediction to all subscribers.
2. **9:45 AM + 3:30 PM ET** — Options screener scans ~200 liquid US stocks for RSI extremes, PCR fear/greed, IV Rank, and unusual options flow. Pushes top signals to subscribers.
3. **Every 30 min, market hours** — Fetches news for signal stocks, snapshots PCR so you can see market positioning around each news item.
4. **2:05 PM TST** — Resolves prediction, runs full TW signal scan, sends Telegram report with today's best picks.
5. **Web dashboard** — TWS stock management (auto-loads TSMC 2330), high-low band charts, options screener, CTBC + Moomoo live trading with asset history chart, options chain browser, backtesting.
6. **iOS app** — Browse TW/US signals, bet virtual coins on the daily prediction, CTBC portfolio view, trade history.
7. **Option Snipe** — Monitors US prices every 60s. When a ticker moves ≥5% in 5 minutes, automatically selects nearest OTM contract and fires a Moomoo order + Telegram alert.
8. **Market Insights Broadcast** — Daily rich market digest sent to all Telegram subscribers. Free tier gets signal summary; Pro tier gets editorial commentary per user.

---

## Broker Integrations

| Broker | Market | Connection | What Works |
|--------|--------|------------|------------|
| CTBC Win168 | Taiwan (TW) | Playwright browser automation | Balance, positions, orders, limit order placement |
| Moomoo / Futu | US | OpenD socket (local daemon) | Balance, positions, orders, options chain, order placement |

**Market toggle** in the Trading page switches between 🇹🇼 CTBC and 🇺🇸 Moomoo in one click. Both are shown in the TWS sidebar (CTBC account widget shows balance + top holdings).

---

## US Options Screener

Runs twice daily on weekdays (9:45 AM and 3:30 PM ET). Scans ~200 pre-filtered stocks:

**Metrics per ticker:**
| Metric | Source | How |
|--------|--------|-----|
| RSI(14) | yfinance 30d OHLCV | Wilder exponential smoothing |
| PCR | yfinance options chain (2 nearest expiries) | put_vol / call_vol |
| Avg IV | yfinance impliedVolatility | Mean across liquid strikes |
| IV Rank | `options_iv_snapshots` (accumulated) | (IV_today − IV_52w_low) / (IV_52w_high − IV_52w_low) × 100 |
| Vol/OI ratio | Options chain | (put_vol + call_vol) / open_interest |

**Signal rules:**
| Type | Condition |
|------|-----------|
| `buy_signal` | RSI < 30 **and** PCR > 1.0 **and** IV Rank < 50 |
| `sell_signal` | RSI > 70 **and** PCR < 0.6 **and** IV Rank < 50 |
| `unusual_activity` | Vol/OI > 3.0× (any RSI) |

**Score 0–10:** RSI depth (4 pts) + PCR extreme (3 pts) + IV Rank cheap (2 pts) + unusual vol (1 pt)

---

## Option Snipe

`options_snipe.py` — standalone price monitor that auto-triggers options orders via Moomoo when a stock moves sharply.

```bash
SNIPE_DRY_RUN=true SNIPE_TICKERS=AAPL,NVDA,TSLA python options_snipe.py
```

**How it works:**
1. Polls yfinance every 60s during US market hours (13:30–20:00 UTC)
2. Detects moves ≥ `SNIPE_THRESHOLD`% (default 5%) within `SNIPE_WINDOW_MIN` minutes (default 5)
3. Finds nearest OTM CALL (move up) or PUT (move down) using yfinance options chain
4. Checks `ask ≤ SNIPE_MAX_PREMIUM` (default $500) before ordering
5. Places Moomoo limit order at ask+2% for fill probability
6. Sends Telegram alert to all active subscribers
7. 30-minute cooldown per ticker after firing

**Environment variables:**
```env
SNIPE_TICKERS=AAPL,TSLA,NVDA,MSFT,SPY  # tickers to watch
SNIPE_THRESHOLD=5.0                      # % move to trigger (default 5%)
SNIPE_WINDOW_MIN=5                       # rolling window in minutes
SNIPE_QTY=1                             # contracts per order
SNIPE_MAX_PREMIUM=500                    # max ask price willing to pay
SNIPE_DRY_RUN=true                      # MUST be false to place real orders
```

---

## Signal Logic (Taiwan)

A stock passes only when **all three** conditions hold simultaneously:

| Check | Rule |
|-------|------|
| Long-term trend | Price above MA120 |
| Short-term dip | Bias < −2% (price ≥ 2% below 20-day avg) |
| Oversold | RSI(14) < 35 |

**Score 0–10:** RSI depth (4 pts) + Bias depth (3 pts) + volume quality (2 pts) + MA120 margin (1 pt).

Enrichment: foreign investor (外資) flow z-score, short interest, news sentiment (VADER), Ledoit-Wolf 5-day target price.

---

## Put/Call Ratio (PCR) — News Sentiment

For each news item in the past 12 hours, Oracle shows how options traders are positioned:

| PCR Range | Label | Meaning |
|-----------|-------|---------|
| > 1.5 | Extreme Fear | Heavy put buying — contrarian buy signal |
| 1.0–1.5 | Fear | Elevated hedging |
| 0.6–1.0 | Neutral | Balanced positioning |
| 0.4–0.6 | Greed | More calls than puts |
| < 0.4 | Extreme Greed | Complacency — watch for reversal |

---

## Architecture

```
Cloud Scheduler
  ├─ 00:00 UTC (08:00 TST) Mon-Fri ──► oracle-predict
  │                                      TAIEX Bull/Bear prediction
  │                                      → Telegram + iOS push
  │
  ├─ 06:05 UTC (14:05 TST) Mon-Fri ──► oracle-resolve
  │                                      OHLCV sync → resolve → settle bets
  │                                      → TW signals → Telegram reports
  │
  ├─ */30 01-06 UTC (TW hours) ─────► oracle-news-poller
  ├─ */30 13-21 UTC (US hours) ─────► oracle-news-poller
  │                                      Google News RSS + PCR snapshots
  │
  ├─ 09:45 ET Mon-Fri ──────────────► oracle-options-screener (morning)
  └─ 15:30 ET Mon-Fri ──────────────► oracle-options-screener (afternoon)
                                        RSI + PCR + IV Rank → iOS push + Telegram

Cloud Run Services
  ├─ oracle-api      — FastAPI backend (scales to zero)
  ├─ oracle-web      — Next.js dashboard → proxies /api/* to oracle-api
  └─ oracle-telegram-bot — always-on (min 1 instance)

Cloud SQL PostgreSQL (14 tables)
GCS bucket — oracle_history.csv, current_trending.csv, data_us/
```

---

## Run Locally

**Requirements:** Docker Desktop + a `.env` file.

```bash
# 1. Clone and configure
cp .env.example .env   # fill in secrets (see below)

# 2. Start PostgreSQL + FastAPI
docker compose up api postgres

# 3. Apply all DB migrations
python3 -m alembic upgrade head

# 4. (optional) Seed data — run pipelines in dry-run mode
OPTIONS_DRY_RUN=true python3 options_screener_pipeline.py
WEEKLY_DRY_RUN=true  python3 weekly_signal_pipeline.py
python3 news_pipeline.py
```

API: `http://localhost:8000` · Docs: `http://localhost:8000/docs`

**Web dashboard:**
```bash
cd web
npm install
npm run dev   # → http://localhost:3000
```

**Option Snipe (optional, requires Moomoo OpenD running):**
```bash
SNIPE_DRY_RUN=true SNIPE_TICKERS=AAPL,NVDA python3 options_snipe.py
```

---

## Environment Variables

### Required for local dev
```env
DATABASE_URL=postgresql+psycopg2://oracle:oracle_dev_password@localhost:5433/oracle
JWT_SECRET=any-random-string-32-chars
INTERNAL_API_SECRET=another-random-string
NEXT_PUBLIC_INTERNAL_SECRET=same-as-INTERNAL_API_SECRET  # web Trading page
```

### Telegram + AI
```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_channel_id
ANTHROPIC_API_KEY=sk-ant-...
```

### CTBC (Taiwan broker)
```env
CTBC_ID=your-ctbc-account-id
CTBC_PASSWORD=your-ctbc-password
CTBC_DRY_RUN=true              # false = submit real orders
```

### Moomoo / Futu (US broker)
```env
MOOMOO_PORT=11111              # OpenD port (required to enable Moomoo features)
MOOMOO_HOST=127.0.0.1
MOOMOO_TRADE_ENV=SIMULATE      # SIMULATE (safe default) or REAL
MOOMOO_UNLOCK_PWD=             # trading password (REAL mode only)
MOOMOO_MARKET=US               # US or HK
```

> **Important:** Start Moomoo OpenD before using any `?market=US` broker endpoints.
> Download: [futunn.com/download/OpenAPI](https://www.futunn.com/download/OpenAPI)

### Option Snipe
```env
SNIPE_TICKERS=AAPL,TSLA,NVDA,MSFT,SPY
SNIPE_THRESHOLD=5.0
SNIPE_WINDOW_MIN=5
SNIPE_QTY=1
SNIPE_MAX_PREMIUM=500
SNIPE_DRY_RUN=true             # MUST set to false to place real orders
```

### Optional (GCS, OAuth)
```env
GCS_BUCKET=                    # empty = local dev; set in prod
GOOGLE_CLIENT_ID=
APPLE_TEAM_ID=
APPLE_CLIENT_ID=
ORACLE_API_BASE=http://localhost:8000
ORACLE_API_URL=http://localhost:8000
NEXT_PUBLIC_API_BASE=          # empty = relative paths (dev); set for external API
```

---

## Deploy to GCP

### Step 1 — One-time infrastructure setup
```bash
# Edit PROJECT_ID at the top of the script, then:
./setup-gcp.sh
```
Creates: Artifact Registry, GCS bucket, Cloud SQL (PostgreSQL), service account, all IAM roles, all secrets, Cloud Scheduler jobs.

### Step 2 — Fill in secrets that can't be auto-generated
```bash
gcloud secrets versions add TELEGRAM_BOT_TOKEN --data-file=- <<< 'your-bot-token'
gcloud secrets versions add TELEGRAM_CHAT_ID   --data-file=- <<< 'your-chat-id'
gcloud secrets versions add ANTHROPIC_API_KEY  --data-file=- <<< 'sk-ant-...'
gcloud secrets versions add GOOGLE_CLIENT_ID   --data-file=- <<< 'your-google-client-id'
```

### Step 3 — Deploy
```bash
gcloud builds submit --config cloudbuild.yaml
```

### Step 4 — Point pipelines at the live API
```bash
API_URL=$(gcloud run services describe oracle-api --region=us-central1 --format='value(status.url)')
gcloud secrets versions add ORACLE_API_BASE --data-file=- <<< "$API_URL"
gcloud secrets versions add ORACLE_API_URL  --data-file=- <<< "$API_URL"
```

### Step 5 — Run migrations on prod DB
```bash
gcloud run jobs execute oracle-migrate --region=us-central1 --wait
```

### Step 6 — Seed data
```bash
gcloud run jobs execute oracle-options-screener --region=us-central1 --wait
gcloud run jobs execute oracle-weekly-signals   --region=us-central1 --wait
gcloud run jobs execute oracle-news-poller      --region=us-central1 --wait
```

---

## Cron Schedule

| Job | When (UTC) | What it does |
|-----|-----------|-------------|
| `oracle-predict` | 00:00 Mon–Fri | TAIEX prediction → Telegram + push |
| `oracle-resolve` | 06:05 Mon–Fri | Resolve Oracle → signals → Telegram reports |
| `oracle-news-poller` | `*/30 1-6` (TW) | News + PCR snapshots for TW tickers |
| `oracle-news-poller` | `*/30 13-21` (US) | News + PCR snapshots for US tickers |
| `oracle-options-screener` | `45 9` ET Mon–Fri | Options screener (morning run) |
| `oracle-options-screener` | `30 15` ET Mon–Fri | Options screener (afternoon run) |
| `oracle-weekly-signals` | `30 10` ET Mon | US ±5% contrarian trades |

---

## API Endpoints

### Public
| Route | Description |
|-------|-------------|
| `GET /health` | Service + DB health check |
| `GET /api/signals/tw` | Taiwan signal stocks |
| `GET /api/signals/us` | US signal stocks |
| `GET /api/oracle/today` | Today's TAIEX prediction |
| `GET /api/oracle/history` | Last 30 resolved predictions |
| `GET /api/news/feed?market=US&hours=12` | News feed with PCR |
| `GET /api/news/{id}/pcr-history` | PCR timeline for one news item |
| `GET /api/weekly/signals` | Weekly ±5% contrarian signals |
| `GET /api/options/screener` | Latest options signals |
| `GET /api/options/overview` | VIX, market PCR, signal counts |
| `GET /api/tws/universe` | TW stock list with filters |
| `GET /api/tws/lookup/{ticker}` | DB-first ticker lookup (DB → universe → yfinance) |
| `GET /api/charts/ohlcv/{ticker}` | OHLCV bars with MA20/MA50 |
| `GET /api/backtest/options` | Options RSI+PCR win-rate backtest |
| `GET /api/backtest/signals` | TW mean-reversion backtest + equity curve |
| `POST /api/subscribe` | Subscribe Telegram chat ID |
| `DELETE /api/subscribe/{telegram_id}` | Unsubscribe |
| `GET /api/subscribe/status/{telegram_id}` | Check tier + editorial note |
| `GET /api/subscribe/count` | Total + pro subscriber counts |

### Broker / Trading (requires `X-Internal-Secret` header)
| Route | Description |
|-------|-------------|
| `GET /api/broker/status` | Connection status for both brokers |
| `GET /api/broker/balance?market=TW\|US` | Live balance (CTBC or Moomoo) — auto-snapshots daily |
| `GET /api/broker/positions?market=TW\|US` | Open positions |
| `GET /api/broker/orders?market=TW\|US&days=7` | Recent orders |
| `POST /api/broker/order` | Place limit order (body: `{ticker, side, qty, limit_price, market}`) |
| `GET /api/broker/trades` | Trade journal (filterable by ticker/status/days/market) |
| `GET /api/broker/asset-history?market=TW&days=90` | Daily balance snapshots for charting |
| `GET /api/broker/options-chain?ticker=AAPL` | Moomoo options chain via OpenQuoteContext |

### Subscription Management (requires `X-Internal-Secret` for upgrade)
| Route | Description |
|-------|-------------|
| `POST /api/subscribe/upgrade` | Grant/revoke Pro tier (internal admin use) |

### Internal (pipeline → API)
| Route | Description |
|-------|-------------|
| `POST /api/notify/broadcast` | Broadcast: `morning`, `result`, `options_signals`, `market_insights` |

---

## Database Schema

```
users               id, auth_provider, auth_id, email, display_name, coins, push_token

subscribers         telegram_id, active, tier (free|pro), tier_expires_at,
                    editorial_note  (admin note shown in Pro digests)

bets                user_id→users, date, direction (Bull/Bear), amount, payout

stock_bets          user_id→users, ticker, direction, entry/exit price, payout

watchlist           user_id→users, ticker, market  [unique: user+ticker+market]

posts               user_id→users, ticker, content (280 chars), signal_type

reactions           user_id→users, post_id→posts, emoji_type  [unique: user+post]

news_items          external_id (sha1 dedup), ticker, market, headline, source,
                    url, published_at, sentiment_score, related_ids (JSON)

news_pcr_snapshots  news_item_id→news_items, ticker, snapshot_at,
                    put_volume, call_volume, pcr, pcr_label

weekly_signals      ticker, week_ending, return_pct, signal_type (buy/sell),
                    executed, order_side, order_qty
                    [unique: ticker + week_ending]

options_iv_snapshots  ticker, snapshot_at, avg_iv
options_signals       ticker, snapshot_at, price, rsi_14, pcr, avg_iv, iv_rank,
                      total_oi, volume_oi_ratio, signal_type, signal_score
                      [unique: ticker + snapshot_at]

trades              broker, ticker, market, side, qty, limit_price,
                    broker_order_id, status, filled_qty, filled_price,
                    commission, realized_pnl, signal_source
                    [unique: broker + broker_order_id]

tws_stock_cache     ticker (unique), name, industry, price, rsi_14,
                    ma20, ma120, bias, fetched_at, updated_at

account_snapshots   market (TW|US), snapshot_date (YYYY-MM-DD),
                    cash, total_value, unrealized_pnl, currency
                    [unique: market + snapshot_date]
                    Written automatically on every /balance fetch —
                    builds 90-day asset history chart passively.
```

**Alembic migrations:**
```
0001_initial_schema.py         base 7 tables
0002_news_and_pcr.py           news_items + news_pcr_snapshots
0003_weekly_signals.py         weekly_signals
0004_options_signals.py        options_signals + options_iv_snapshots
0005_add_trades_table.py       trades (broker order journal)
0006_add_tws_stock_cache.py    tws_stock_cache (ticker lookup cache)
0007_add_account_snapshots.py  account_snapshots (asset history)
0008_subscriber_tier.py        subscribers.tier + tier_expires_at + editorial_note
```

Run all: `python3 -m alembic upgrade head`

---

## Subscription & Community

### Telegram Notifications

| Tier | Price | What you get |
|------|-------|-------------|
| Free | NT$0 | Daily TAIEX prediction, settlement, weekly signal summary, basic market insights |
| Pro  | NT$100/月 | Real-time options signals, daily market digest + editorial commentary, Option Snipe alerts, priority support |

**Subscribing:** Visit `/subscribe` on the dashboard → enter your Telegram Chat ID (get it from [@userinfobot](https://t.me/userinfobot)).

**Pro access:** Pro is invite-based. Subscribe free → join Discord → DM an admin. Admin runs:
```bash
curl -X POST /api/subscribe/upgrade \
  -H "X-Internal-Secret: $INTERNAL_API_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"telegram_id":"123456789","tier":"pro","editorial_note":"Taiwan tech focus, long TSMC"}'
```

### Market Insights Broadcast

Trigger manually or add to cron:
```bash
curl -X POST /api/notify/broadcast \
  -H "X-Internal-Secret: $INTERNAL_API_SECRET" \
  -d '{"type":"market_insights"}'
```

Free subscribers receive: top options signals, weekly movers, stats summary.
Pro subscribers receive the same + per-subscriber `editorial_note` commentary.

### Discord Community

Join: [discord.gg/lokistock](https://discord.gg/lokistock)

Channels: `#市場討論` `#訊號分享` `#回測研究` `#dev` `#pro-analysis`

### Open Source

LokiStock is open source. Star us on GitHub, open issues, or submit PRs. Discuss features in Discord `#dev`.

---

## Web Dashboard Pages

| Route | Description |
|-------|-------------|
| `/` | Landing page — hero, feature grid, Free/Pro pricing |
| `/tws` | TWS stock management — auto-loads TSMC 2330, CTBC account widget in sidebar, DB-first ticker lookup |
| `/charts` | High-low band chart (Recharts), period selector, TW/US market toggle |
| `/trading` | CTBC + Moomoo trading — market toggle 🇹🇼/🇺🇸, 90-day asset history chart, open positions, order form, options chain browser (US), trade history |
| `/backtest` | Options win-rate + signals equity curve + trades table |
| `/options` | Options screener + RSI/PCR chart + P&L calculator |
| `/news` | Two-pane: news list + PCR timeline chart |
| `/weekly` | ±5% contrarian signals with PCR bars |
| `/subscribe` | Community hub — Telegram signup, Free/Pro comparison, Discord, open source |

---

## Telegram Commands

| Command | What it does |
|---------|-------------|
| Send a 4-digit code | Fundamentals + AI target price for any Taiwan stock |
| `/options` | Top 5 US options signals from latest screener run |
| `/balance` | Cash + net value (CTBC + Moomoo) |
| `/positions` | Open holdings |
| `/orders [days]` | Recent order history (default: 7 days) |

**Automated daily reports:**

| Time (TST) | Report |
|-----------|--------|
| 08:00 | TAIEX prediction + 5-factor breakdown + confidence % |
| 14:05 | Prediction result + TAIEX change + streak |
| 14:05 | Signal buy list — RSI, bias, score, foreign flow, sentiment |
| On demand | Market insights broadcast (triggered via `/api/notify/broadcast`) |

---

## Mobile App (iOS)

```bash
cd mobile && npm install
npx expo start       # local dev
eas build --platform ios --profile preview   # TestFlight
```

Bundle ID: `com.lokistock.oracle` · Min iOS: 16.0

**Tabs:** Signals · Oracle · News · Community · Watchlist · Profile (CTBC portfolio)

---

## Project Layout

```
stock_analysis/
│
├── api/
│   ├── db.py                      SQLAlchemy models (16 tables incl. account_snapshots)
│   ├── main.py                    FastAPI entry point
│   └── routers/
│       ├── broker.py              CTBC + Moomoo — balance (auto-snapshot), positions,
│       │                          orders, trades, asset-history, options-chain
│       ├── subscribe.py           Telegram sub + tier management (free/pro/upgrade)
│       ├── notify.py              Push + Telegram broadcast (morning/result/options/market_insights)
│       ├── tws.py                 TWS universe + DB-first ticker lookup
│       ├── charts.py              OHLCV via yfinance
│       └── backtest.py            Options win-rate + TW mean-reversion
│
├── brokers/
│   ├── moomoo.py                  Moomoo/Futu: positions, balance, orders,
│   │                              place_order, get_options_chain (OpenQuoteContext)
│   └── ctbc.py / base.py         CTBC Playwright automation
│
├── options/
│   ├── fetcher.py                 RSI+PCR+IV per ticker (all numpy → float cast)
│   ├── signals.py                 classify_signal() + 0-10 score
│   └── universe.py                Finviz + weekly + S&P 500 pre-filter
│
├── alembic/versions/
│   ├── 0001_initial_schema.py
│   ├── 0002_news_and_pcr.py
│   ├── 0003_weekly_signals.py
│   ├── 0004_options_signals.py
│   ├── 0005_add_trades_table.py
│   ├── 0006_add_tws_stock_cache.py
│   ├── 0007_add_account_snapshots.py  ← NEW: daily balance snapshots
│   └── 0008_subscriber_tier.py        ← NEW: free/pro tier + editorial_note
│
├── web/
│   ├── app/page.tsx               Landing page (hero + features + pricing)
│   ├── app/tws/                   TWS: auto-load 2330, CTBC sidebar widget
│   ├── app/trading/               CTBC+Moomoo: market toggle, asset history chart,
│   │                              options chain tab (US), order form
│   ├── app/subscribe/             Community hub: Discord, open source, Free/Pro
│   ├── components/NavBar.tsx      Active-state nav (usePathname)
│   ├── lib/api.ts                 All API calls incl. brokerAssetHistory, brokerOptionsChain
│   └── lib/types.ts               Types incl. AccountSnapshot, OptionsChainResponse
│
├── options_snipe.py               ← NEW: price monitor → OTM contract → Moomoo order + Telegram
├── options_screener_pipeline.py   Twice-daily options screener (numpy types fixed)
├── weekly_signal_pipeline.py      Monday ±5% contrarian trades
├── news_pipeline.py               News + PCR every 30 min
├── master_run.py                  Daily cron: predict + resolve
├── app.py                         Telegram bot
│
├── Dockerfile                     Full pipeline image (Playwright)
├── Dockerfile.api                 Slim API image
├── docker-compose.yml             Local: postgres + api + pipeline
├── setup-gcp.sh                   One-time GCP infra setup
└── cloudbuild.yaml                CI/CD: build → migrate → deploy all services
```

---

## Claude Code MCP Integration

```bash
cd mcp && npm install
# .claude/mcp.json auto-registers when you open the project
```

**Tools available:** `oracle_options_screener`, `oracle_weekly_signals`, `oracle_news_feed`, `oracle_signal_search`, `oracle_backtest_results`, `oracle_prediction` — plus TradingView chart/Pine/screenshot tools when TradingView Desktop is running with `--remote-debugging-port=9222`.

---

## Roadmap

### Completed
- [x] Taiwan + US signal pipeline (RSI + Bias + MA120, Ledoit-Wolf, institutional flow)
- [x] TAIEX Oracle prediction + virtual coin betting game
- [x] Multi-agent AI analysis (6 Claude agents + orchestrator)
- [x] iOS app — LokiStock Oracle (Apple/Google auth, community feed, watchlist)
- [x] FastAPI backend on GCP Cloud Run + Cloud SQL
- [x] GCP Cloud Scheduler cron jobs (predict + resolve + options + news + weekly)
- [x] News feed with put/call ratio — 12h rolling, PCR timeline, cross-related
- [x] LokiStock web dashboard — TWS, Charts, Trading, Backtest, Options, News, Weekly, Subscribe
- [x] Landing page with feature grid + Free/Pro pricing
- [x] Active-state NavBar (`usePathname`)
- [x] Telegram subscription + daily automated reports
- [x] US weekly contrarian pipeline — ±5% movers, broker-executed trades
- [x] US options screener — RSI + PCR + IV Rank + unusual flow, push delivery
- [x] TWS stock management (auto-loads TSMC 2330, CTBC account widget, DB-first lookup)
- [x] High-low band chart (Recharts stacked Area, period selector, TW/US market)
- [x] Options P&L calculator (call/put payoff at expiry)
- [x] Options + signals backtesting (equity curve, win-rate cards)
- [x] CTBC broker integration — balance, positions, orders, limit order placement
- [x] Moomoo broker integration — US market, balance, positions, orders, limit orders
- [x] TW/US market toggle in Trading page
- [x] 90-day asset history chart (auto-built from passive `/balance` snapshots)
- [x] Moomoo options chain browser in Trading page (options chain tab)
- [x] Option Snipe script (price trigger → OTM contract → Moomoo order + Telegram)
- [x] Premium subscriber tiers (free/pro) + editorial commentary in market insights
- [x] Market Insights broadcast — rich daily digest, free vs pro content split
- [x] Discord + open source community hub on Subscribe page
- [x] `account_snapshots` table (migrations 0007 + 0008)
- [x] Numpy float64 → Python float fix in options screener (SQLAlchemy compat)

### Upcoming
- [ ] Run `python3 -m alembic upgrade head` on production DB (migrations 0007 + 0008)
- [ ] Create Discord server at discord.gg/lokistock and GitHub org at github.com/lokistock
- [ ] IV Rank accuracy (improves after 30 trading days of snapshot accumulation)
- [ ] EAS credentials + first TestFlight build
- [ ] App Store submission
- [ ] Push notification for TWS signal stocks (notify watchlisted users when signal fires)
- [ ] Options Snipe Cloud Run job + Cloud Scheduler (run during US market hours)
- [ ] LSTM / Transformer deep-learning price prediction
