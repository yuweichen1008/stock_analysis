# LokiStock — AI Stock Screener, Options Sentiment & Taiwan Trading Dashboard

A multi-platform stock analysis system with a **web dashboard** (lokistock.com), an **iOS app** (LokiStock Oracle), and a **Telegram bot**. Every trading day it scans thousands of Taiwan and US stocks, scores them with a 7-factor model, runs multi-agent AI analysis, tracks **put/call ratios** on market-moving news, and sends automated Telegram reports — all on Google Cloud Run. A live **CTBC broker integration** lets you place Taiwan stock orders directly from the dashboard.

---

## What It Does (ELI5)

1. **8:00 AM (Taiwan time)** — Predicts whether the TAIEX index will go up or down today using 5 market signals (S&P 500 overnight, VIX, momentum, etc.)
2. **9:45 AM + 3:30 PM ET (US weekdays)** — Options screener scans ~200 liquid US stocks for RSI extremes, PCR fear/greed, IV Rank, and unusual options flow — scores each setup 0–10 and pushes top signals to subscribers
3. **Every 30 min during market hours** — Fetches latest news for signal stocks, snapshots the **options put/call ratio (PCR)** so you can see how the market is positioned around each news item
4. **2:05 PM (Taiwan time)** — After market close, resolves the prediction, runs the full TW signal scan, and sends a Telegram report with today's best stock picks
5. **Web dashboard** (lokistock.com) — Moomoo-style TWS stock management, high-low band charts, options screener, live CTBC trading (place orders, view positions/balance, trade history), backtesting
6. **iOS app** (LokiStock Oracle) — Browse TW/US signals, bet virtual coins on the daily prediction, enhanced stock detail with RSI gauge + foreign flow bars, CTBC portfolio view, trade history
7. **CTBC broker integration** — Place Taiwan stock limit orders from the web dashboard; trade journal tracks every order with status, filled price, and realized P&L

---

## US Options Screener

Runs twice daily on weekdays (9:45 AM and 3:30 PM ET). Scans ~200 pre-filtered stocks:

**Universe pre-filter (priority order):**
1. Finviz unusual options volume — highest-signal subset (~30-80 tickers)
2. Recent weekly contrarian signal tickers — continuity with the weekly pipeline
3. S&P 500 fill — fills remaining budget up to 200 tickers

**Metrics computed per ticker:**
| Metric | Source | How |
|--------|--------|-----|
| RSI(14) | yfinance 30d OHLCV | Wilder exponential smoothing |
| PCR | yfinance options chain (2 nearest expiries) | put_vol / call_vol |
| Avg IV | yfinance impliedVolatility | Mean across liquid strikes |
| IV Rank | Accumulated `options_iv_snapshots` | (IV_today − IV_52w_low) / (IV_52w_high − IV_52w_low) × 100 |
| Vol/OI ratio | Options chain | (put_vol + call_vol) / open_interest |

**Signal rules:**
| Type | Condition | What it means |
|------|-----------|---------------|
| `buy_signal` | RSI < 30 **and** PCR > 1.0 **and** IV Rank < 50 | Oversold + fear + cheap options |
| `sell_signal` | RSI > 70 **and** PCR < 0.6 **and** IV Rank < 50 | Overbought + greed + cheap options |
| `unusual_activity` | Vol/OI > 3.0× (any RSI) | Informed flow detected |

**Score (0–10):** RSI depth (4 pts) + PCR extreme (3 pts) + IV Rank cheap (2 pts) + unusual vol (1 pt)

**IV Rank cold-start:** `null` for the first ~2 weeks while daily snapshots accumulate. Signals still fire — the IV condition is treated as met (conservative). Becomes accurate after 30+ pipeline runs.

**Subscriber delivery:**
- iOS push notification: top 3 signals → all registered devices
- Telegram broadcast: top 5 signals → all active subscribers (set `OPTIONS_DRY_RUN=false`)
- `/options` Telegram command for on-demand results

---

## Signal Logic

A stock passes only when **all three** conditions are true at the same time:

| Check | Rule | What it means |
|-------|------|---------------|
| Long-term trend | Price above MA120 | The stock has been healthy for 6 months |
| Short-term dip | Bias < −2% (price ≥ 2% below 20-day average) | It temporarily pulled back |
| Oversold | RSI (14-period) < 35 | Sellers are exhausted — bounce is likely |

**Score (0–10):** RSI depth (4 pts) + Bias depth (3 pts) + volume quality (2 pts) + MA120 margin (1 pt). Higher = cleaner setup.

Additional enrichment per signal: foreign investor (外資) flow z-score, short interest, news sentiment (VADER), Ledoit-Wolf 5-day target price.

---

## Put/Call Ratio (PCR) — News Sentiment

For each news item in the past 12 hours, Oracle shows whether options traders are hedging (puts) or buying (calls):

| PCR Range | Label | Meaning |
|-----------|-------|---------|
| > 1.5 | Extreme Fear | Heavy put buying — contrarian buy signal historically |
| 1.0–1.5 | Fear | Elevated hedging around the news |
| 0.6–1.0 | Neutral | Balanced positioning |
| 0.4–0.6 | Greed | More calls than puts — bullish bias |
| < 0.4 | Extreme Greed | Complacency — watch for reversal |

**US stocks:** Real PCR from yfinance options chain (nearest expiry, all strikes summed).  
**Taiwan stocks:** VADER NLP sentiment proxy — TAIFEX options not accessible via public APIs.

The PCR is snapshotted every 30 minutes while a news item is fresh, building a **PCR timeline** that shows how market positioning shifted after the news broke.

---

## Architecture

```
Cloud Scheduler
  ├─ 08:00 TST Mon-Fri ──► Cloud Run Job: oracle-predict
  │                            compute Bull/Bear prediction
  │                            → save oracle_history.csv → GCS
  │                            → Telegram prediction message
  │                            → push notification to iOS users
  │
  ├─ 14:05 TST Mon-Fri ──► Cloud Run Job: oracle-resolve
  │                            sync OHLCV data from TWSE
  │                            resolve today's prediction
  │                            → settle virtual coin bets
  │                            run TW + US signal scan
  │                            → upload current_trending.csv → GCS
  │                            → Telegram reports (heatmap, buy list)
  │                            → push notifications
  │
  ├─ */30 01-06 Mon-Fri ──► Cloud Run Job: oracle-news-poller  (TW market hours)
  │                            fetch Google News RSS for signal tickers
  │                            snapshot PCR via yfinance options chain
  │                            compute cross-related news links (Jaccard)
  │                            → write to PostgreSQL news_items + news_pcr_snapshots
  │
  ├─ */30 13-21 Mon-Fri ──► Cloud Run Job: oracle-news-poller  (US market hours)
  │                            same as above, for US tickers
  │
  ├─ 09:45 ET Mon-Fri ───► Cloud Run Job: oracle-options-screener  (morning)
  │                            scan ~200 US stocks for RSI + PCR + IV Rank signals
  │                            → write options_signals + options_iv_snapshots to DB
  │                            → iOS push + Telegram broadcast (if OPTIONS_DRY_RUN=false)
  │
  └─ 15:30 ET Mon-Fri ───► Cloud Run Job: oracle-options-screener  (afternoon)
                               same as above, captures end-of-day positioning

Cloud Run Services
  ├─ oracle-api (min 0 → scales to zero, max 10)
  │    reads oracle_history.csv    ◄── GCS
  │    reads current_trending.csv  ◄── GCS  (cached 1h in memory)
  │    serves iOS app + web dashboard
  │
  ├─ oracle-web  (Next.js dashboard, min 0 → max 5)
  │    two-pane news feed + PCR timeline charts
  │    proxies /api/* → oracle-api
  │
  └─ oracle-telegram-bot (min 1 → always on)
       polls Telegram
       responds to ticker lookups and broker commands

Cloud SQL PostgreSQL
  └─ users, bets, stock_bets, watchlist, posts, reactions, subscribers,
     news_items, news_pcr_snapshots

GCS bucket (YOUR_PROJECT_ID-oracle-signals)
  ├─ current_trending.csv           ← written by resolve job, read by API
  ├─ data_us/current_trending.csv   ← written by US pipeline, read by API
  └─ data/index/oracle_history.csv  ← written by predict+resolve, read by API
```

---

## Run Locally

**Requirements:** Docker Desktop, a `.env` file.

```bash
# 1. Copy env template and fill in secrets (see .env section below)
cp .env.example .env

# 2. Start PostgreSQL + FastAPI
docker compose up api postgres

# 3. Run DB migrations
alembic upgrade head

# 4. (optional) Run the signal pipeline once to generate data
docker compose --profile pipeline run pipeline python master_run.py --step resolve

# 5. (optional) Run the news poller once
python news_pipeline.py
```

API is at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

**Web dashboard (separate):**
```bash
cd web
npm install
ORACLE_API_URL=http://localhost:8000 npm run dev
# → http://localhost:3000
```

### `.env` secrets

**Required for local dev:**
```env
DATABASE_URL=postgresql+psycopg2://oracle:oracle_dev_password@localhost:5433/oracle
JWT_SECRET=any-random-string-32-chars-minimum
INTERNAL_API_SECRET=another-random-string
```
> Port 5433 is used locally to avoid conflicts with other Postgres instances.

**Required for pipeline + Telegram:**
```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_channel_id
```

**Required for AI analysis:**
```env
ANTHROPIC_API_KEY=sk-ant-...
```

**Required for CTBC trading:**
```env
CTBC_ID=your-ctbc-account-id
CTBC_PASSWORD=your-ctbc-password
CTBC_DRY_RUN=true             # false = submit real orders
NEXT_PUBLIC_INTERNAL_SECRET=same-as-INTERNAL_API_SECRET  # web Trading page auth
```

**Optional (GCS, auth):**
```env
GCS_BUCKET=                   # leave empty in local dev; set in prod
GOOGLE_CLIENT_ID=             # Google OAuth
APPLE_TEAM_ID=                # Apple Sign-In
APPLE_CLIENT_ID=              # Apple Sign-In bundle ID
ORACLE_API_BASE=http://localhost:8000   # pipeline → API callouts
ORACLE_API_URL=http://localhost:8000    # web dashboard → API proxy
```

---

## Deploy to GCP

### Step 1 — One-time infrastructure setup

```bash
# Edit the PROJECT_ID at the top of the script, then:
./setup-gcp.sh
```

This script (~3 min + 5 min for Cloud SQL) does everything:
- Enables all required APIs
- Creates Artifact Registry repo `oracle`
- Creates GCS bucket `YOUR_PROJECT_ID-oracle-signals`
- Creates Cloud SQL PostgreSQL instance `oracle-db` (db-f1-micro)
- Creates service account `oracle-sa` with correct IAM roles
- Generates `JWT_SECRET` and `INTERNAL_API_SECRET` automatically
- Creates all secrets in Secret Manager
- Grants Cloud Build the IAM roles it needs
- Creates Cloud Scheduler jobs (predict + resolve)
- Patches `YOUR_PROJECT_ID` in all YAML files automatically

### Step 2 — Fill in the secrets the script can't auto-generate

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

Cloud Build runs 16 steps automatically:
1. Build slim API Docker image (`Dockerfile.api`)
2. Build full pipeline Docker image (`Dockerfile`)
3–4. Push both images to Artifact Registry
5. Deploy Alembic migration job
6. Run the migration (creates all tables in Cloud SQL)
7. Deploy `oracle-api` Cloud Run service
8. Deploy `oracle-telegram-bot` Cloud Run service
9. Deploy `oracle-predict` Cloud Run Job
10. Deploy `oracle-resolve` Cloud Run Job
11. Build Next.js web dashboard image
12. Push web image to Artifact Registry
13. Deploy `oracle-web` Cloud Run service
14. Deploy `oracle-news-poller` Cloud Run Job
15. Deploy `oracle-weekly-signals` Cloud Run Job
16. Deploy `oracle-options-screener` Cloud Run Job

### Step 4 — Post-deploy secrets

```bash
# Get the API URL
gcloud run services describe oracle-api --region=us-central1 --format='value(status.url)'
# → https://oracle-api-xxxx-uc.a.run.app

# Update both secrets so pipelines + web dashboard point at the real API
gcloud secrets versions add ORACLE_API_BASE --data-file=- <<< 'https://oracle-api-xxxx-uc.a.run.app'
gcloud secrets versions add ORACLE_API_URL  --data-file=- <<< 'https://oracle-api-xxxx-uc.a.run.app'
```

> All Cloud Scheduler jobs (predict, resolve, news poller ×2, weekly signals, options screener ×2) are created automatically by `setup-gcp.sh`. No manual scheduler setup needed.

### Step 5 — First-time DB seeding

After the first deployment the database tables are empty — web pages will show a "no signals yet" empty state until a pipeline run has populated them. You have two options:

**Option A — trigger Cloud Run jobs immediately:**
```bash
# Options screener (safe — OPTIONS_DRY_RUN=false only sends iOS/Telegram notifications)
gcloud run jobs execute oracle-options-screener --region=us-central1 --wait

# Weekly contrarian signals (safe — WEEKLY_DRY_RUN=false only submits real broker trades)
gcloud run jobs execute oracle-weekly-signals --region=us-central1 --wait

# News + PCR
gcloud run jobs execute oracle-news-poller --region=us-central1 --wait
```

**Option B — seed locally (no cloud needed):**
```bash
# Copy your prod DATABASE_URL to .env, then:
OPTIONS_DRY_RUN=true python options_screener_pipeline.py
WEEKLY_DRY_RUN=true python weekly_signal_pipeline.py
python news_pipeline.py
```

Verify the DB is seeded:
```bash
curl https://oracle-api-xxxx-uc.a.run.app/api/options/db-status
# → {"seeded": true, "options_signals": 42, ...}
```

### Step 6 — Test everything

```bash
# Health check
curl https://oracle-api-xxxx-uc.a.run.app/health

# Run news poller manually
gcloud run jobs execute oracle-news-poller --region=us-central1 --wait

# Check news feed
curl "https://oracle-api-xxxx-uc.a.run.app/api/news/feed?market=US&limit=5"

# Check Cloud Scheduler
gcloud scheduler jobs list --location=us-central1
```

---

## Cron Schedule

| Job | When (UTC) | Days | What it does | Max runtime |
|-----|-----------|------|-------------|-------------|
| `oracle-predict` | 00:00 (08:00 TST) | Mon–Fri | Compute TAIEX Bull/Bear prediction → GCS → Telegram + push | 10 min |
| `oracle-resolve` | 06:05 (14:05 TST) | Mon–Fri | Sync OHLCV → resolve Oracle → settle bets → signals → GCS → Telegram | 15 min |
| `oracle-news-poller` | `*/30 1-6` (TW hours) | Mon–Fri | Fetch news + PCR snapshots for TW tickers | 5 min |
| `oracle-news-poller` | `*/30 13-21` (US hours) | Mon–Fri | Fetch news + PCR snapshots for US tickers | 5 min |
| `oracle-options-screener` | `45 9` ET (09:45 ET) | Mon–Fri | Options screener — RSI + PCR + IV Rank, push signals | 20 min |
| `oracle-options-screener` | `30 15` ET (15:30 ET) | Mon–Fri | Options screener — afternoon run, end-of-day positioning | 20 min |
| `oracle-weekly-signals` | `30 10` ET Mon (10:30 ET) | Mon | US ±5% contrarian trades — buy dip, sell rip | 15 min |

The Telegram bot (`oracle-telegram-bot`) runs continuously and responds in real-time to commands.

---

## API Endpoints

### Public / JWT-protected
| Route | Auth | Description |
|-------|------|-------------|
| `GET /health` | — | Service + DB health check |
| `GET /api/signals/tw` | — | Taiwan signal stocks |
| `GET /api/signals/us` | — | US signal stocks |
| `GET /api/signals/search?q=AAPL&market=US` | — | Ticker / name search |
| `GET /api/oracle/today` | — | Today's TAIEX prediction |
| `GET /api/oracle/history` | — | Last 30 resolved predictions |
| `GET /api/oracle/stats` | — | Win rate, streak, cumulative score |
| `GET /api/oracle/live` | — | Live TAIEX level (15-min delayed) |
| `GET /api/news/feed?market=US&hours=12` | — | 12h news feed with PCR (5-min cache) |
| `GET /api/news/{id}/pcr-history` | — | PCR snapshot timeline for one news item |
| `GET /api/news/{id}/related` | — | Cross-related news items |
| `GET /api/agents/analyze?ticker=X&market=US` | — | 6-agent AI analysis (1h cache) |
| `GET /api/agents/batch?market=US` | — | Batch AI for top signal stocks |
| `POST /api/auth/apple` | — | Apple Sign-In → JWT |
| `POST /api/auth/google` | — | Google OAuth → JWT |
| `POST /api/auth/device` | — | Anonymous device-ID → JWT |
| `GET /api/sandbox/me` | JWT | Coin balance, bets, rank |
| `POST /api/sandbox/bet` | JWT | Place Bull/Bear bet (locked after 09:00 TST) |
| `GET /api/sandbox/leaderboard` | — | Top 20 players |
| `GET /api/watchlist` | JWT | My saved tickers |
| `POST /api/watchlist` | JWT | Add ticker |
| `DELETE /api/watchlist/{ticker}` | JWT | Remove ticker |
| `GET /api/watchlist/alerts` | JWT | Watchlisted tickers with a signal today |
| `GET /api/feed` | optional JWT | Community posts (paginated) |
| `POST /api/feed` | JWT | Create post (max 280 chars, 10/hour) |
| `POST /api/feed/{id}/react` | JWT | Toggle 🐂🐻🔥 reaction |
| `GET /api/weekly/signals` | — | Weekly ±5% contrarian signals with PCR |
| `GET /api/weekly/signals/{ticker}/history` | — | 52-week signal history for one ticker |
| `GET /api/options/screener` | — | Latest options signals (RSI+PCR+IV Rank, 5-min cache) |
| `GET /api/options/screener/{ticker}/history` | — | 30-day options signal history for one ticker |
| `GET /api/options/overview` | — | VIX, market PCR, buy/sell/unusual counts, top 3 signals |
| `GET /api/options/db-status` | — | Row counts for options tables |
| `GET /subscribe` | — | Telegram subscription web page |
| `POST /api/subscribe` | — | Subscribe Telegram chat ID |

### TWS (Taiwan Stock Management)
| Route | Auth | Description |
|-------|------|-------------|
| `GET /api/tws/universe` | — | Enriched TW stock list (signal + sector + sort filters) |
| `GET /api/tws/stock/{ticker}` | — | Single stock detail from universe |
| `GET /api/tws/lookup/{ticker}` | — | DB-first lookup: DB cache → universe → yfinance+store |
| `POST /api/tws/cache/invalidate` | — | Clear in-memory universe cache |

### Charts
| Route | Auth | Description |
|-------|------|-------------|
| `GET /api/charts/ohlcv/{ticker}?period=3mo&market=US` | — | OHLCV bars with MA20/MA50 (yfinance) |
| `GET /api/charts/search?q=AAPL` | — | Fast ticker info lookup |

### Backtest
| Route | Auth | Description |
|-------|------|-------------|
| `GET /api/backtest/options` | — | Options RSI+PCR win-rate (1h cache) |
| `GET /api/backtest/signals` | — | TW mean-reversion backtest with equity curve |

### Broker / Trading (requires `X-Internal-Secret` header)
| Route | Auth | Description |
|-------|------|-------------|
| `GET /api/broker/status` | Secret | Connection status + dry-run flag |
| `GET /api/broker/balance` | Secret | Live CTBC cash + total value + unrealized P&L |
| `GET /api/broker/positions` | Secret | Live open positions |
| `GET /api/broker/orders?days=7` | Secret | Recent orders from CTBC |
| `POST /api/broker/order` | Secret | Place limit order; records in `trades` table |
| `GET /api/broker/trades` | Secret | Trade journal from DB (filterable by ticker/status/days) |
| `GET /api/broker/trades/{ticker}` | Secret | Trade history for one ticker |

### Internal (pipeline → API)
| Route | Auth | Description |
|-------|------|-------------|
| `POST /api/sandbox/settle` | X-API-Secret | Settle Oracle bets |
| `POST /api/notify/broadcast` | X-API-Secret | Send push notifications |
| `POST /api/stocks/settle` | X-API-Secret | Settle stock bets |

---

## Database Schema

```
users               id, auth_provider (apple/google/device), auth_id, email,
                    display_name, avatar_url, coins, push_token

subscribers         telegram_id, active  (Telegram opt-in)

bets                user_id→users, date, direction (Bull/Bear), amount, payout

stock_bets          user_id→users, ticker, direction, entry/exit price, payout

watchlist           user_id→users, ticker, market  [unique: user+ticker+market]

posts               user_id→users, ticker, content (280 chars), signal_type

reactions           user_id→users, post_id→posts, emoji_type  [unique: user+post]

news_items          external_id (sha1 dedup), ticker, market (US/TW/MARKET),
                    headline, source, url, published_at, sentiment_score,
                    related_ids (JSON array)

news_pcr_snapshots  news_item_id→news_items, ticker, snapshot_at,
                    put_volume, call_volume, pcr, pcr_label

weekly_signals      ticker, week_ending, return_pct, signal_type (buy/sell),
                    last_price, pcr, pcr_label, put_volume, call_volume,
                    executed, order_side, order_qty
                    [unique: ticker + week_ending]

options_iv_snapshots  ticker, snapshot_at, avg_iv
                      (accumulates daily for IV Rank; accurate after 30+ snapshots)

options_signals     ticker, snapshot_at, price, rsi_14, pcr, avg_iv, iv_rank,
                    total_oi, volume_oi_ratio, signal_type, signal_score, signal_reason
                    [unique: ticker + snapshot_at]

trades              broker, ticker, market, side (buy/sell), qty, order_type,
                    limit_price, broker_order_id, status (pending/filled/cancelled/rejected),
                    filled_qty, filled_price, commission, realized_pnl, signal_source
                    [unique: broker + broker_order_id]

tws_stock_cache     ticker (unique), name, industry, price, open_price,
                    high_52w, low_52w, volume, market_cap, pe_ratio, roe,
                    dividend_yield, rsi_14, ma20, ma120, bias, fetched_at, updated_at
                    (DB-first cache for TWS ticker lookup; refreshed every 4h)
```

**Migrations:**
```
0001_initial_schema.py     — base 7 tables
0002_news_and_pcr.py       — news_items + news_pcr_snapshots
0003_weekly_signals.py     — weekly_signals
0004_options_signals.py    — options_signals + options_iv_snapshots
0005_add_trades_table.py   — trades (CTBC order journal)
0006_add_tws_stock_cache.py — tws_stock_cache (ticker lookup cache)
```

---

## Mobile App Setup

```bash
cd mobile
npm install
npx expo start          # local dev (points to localhost:8000)
```

**Build for TestFlight:**
```bash
eas build --platform ios --profile preview
```

**Before production build**, update `mobile/app.json`:
- `extra.apiBaseProd` → your Cloud Run URL
- `ios.bundleIdentifier` → `com.yourco.oracle`
- `extra.easProjectId` → your EAS project ID

**App tabs:**

| Tab | Description |
|-----|-------------|
| 📊 Signals | TW + US signal stocks · RSI/score · tap for AI detail |
| 🔮 Oracle | TAIEX prediction · bet virtual coins · view history |
| 📰 News | 12h news feed · put/call ratio bars · PCR timeline · related news |
| 👥 Community | Post trade ideas · react with 🐂🐻🔥 · market filter |
| ⭐ Watchlist | Saved tickers · today's signal alerts |
| 👤 Profile | Coins · leaderboard rank · CTBC portfolio (balance, holdings, P&L) · sign out |

**Stock detail screen** (`/stock/[ticker]`):
- RSI arc gauge (pure View-based, no SVG dependency)
- Foreign investor flow bars (F5 / F20 / F60 day net buy/sell)
- Signal banner for mean-reversion and high-value moat stocks
- NT$ price formatting for Taiwan market
- "View Chart" button → opens lokistock.com/charts in browser

**Trade history screen** (`/trade-history`):
- Full CTBC order journal with buy/sell badges, filled price, realized P&L
- Filter pills: All / Buy / Sell / Pending / Filled

**Build for TestFlight / App Store:**
```bash
eas build --platform ios --profile preview    # TestFlight
eas build --platform ios --profile production # App Store
```
Bundle ID: `com.lokistock.oracle` · Min iOS: 16.0

---

## Web Dashboard Setup

```bash
cd web
npm install
ORACLE_API_URL=http://localhost:8000 npm run dev
# → http://localhost:3000
```

**Pages:**

| Route | Description |
|-------|-------------|
| `/tws` | **Moomoo-style TWS stock management** — left list (RSI bar, signal badge, bias%) + right detail panel (inline high-low chart, RSI arc gauge, foreign flow bars, fundamentals). Enter a ticker number and press Enter to trigger DB-first lookup (DB cache → universe → yfinance fetch+store). |
| `/charts` | **High-low band chart** — Recharts stacked Area (high-low range) + close/MA20/MA50 lines + volume bar chart. Period pills (1mo/3mo/6mo/1y), market toggle (TW/US), ticker search. |
| `/trading` | **CTBC live trading dashboard** — account balance bar, open positions table, order form (ticker + buy/sell + qty + limit price + confirm modal), trade history with filters. |
| `/backtest` | **Backtesting** — options RSI+PCR win-rate cards (buy/sell/combined) + signals mean-reversion equity curve + trades table. |
| `/options` | Options screener + RSI/PCR dual-axis chart + **P&L calculator** (call/put payoff at expiry). |
| `/news` | Two-pane: news list with PCR bars (left) + PCR timeline chart + related news (right). |
| `/weekly` | Two-pane: ±5% contrarian signals + PCR bar + history table. |
| `/subscribe` | Telegram subscription page. |

**Build for production:**
```bash
cd web && npm run build
```

The web dashboard deploys to Cloud Run as `oracle-web` and proxies `/api/*` to `oracle-api`. Sitemap is served at `/sitemap.xml`.

---

## Telegram Commands

| Command | What it does |
|---------|-------------|
| Send a 4-digit code | Fundamentals + AI target price for any Taiwan stock |
| `/options` | Top 5 US options signals (RSI + PCR + IV Rank) from latest screener run |
| `/balance` | Cash + net value across connected brokers |
| `/positions` | Open holdings |
| `/orders [days]` | Recent order history (default: 7 days) |

**Daily automated reports (sent to `TELEGRAM_CHAT_ID`):**

| Time (TST) | Report |
|-----------|--------|
| 08:00 | TAIEX Bull/Bear prediction + 5-factor breakdown + confidence % |
| 14:05 | Prediction result + TAIEX change + points earned + streak |
| 14:05 | Full-market heatmap (1068 stocks) + sector zoom charts |
| 14:05 | Signal buy list — RSI, bias, score, foreign flow, sentiment per ticker |

**Subscribe to Telegram notifications:**  
Visit `/subscribe` on the web dashboard or API server. Enter your Telegram Chat ID (get it from [@userinfobot](https://t.me/userinfobot)).

> **Note:** Broker commands (`/balance`, `/positions`, `/orders`) require a local broker daemon (IBKR TWS, Moomoo OpenD). These won't work on Cloud Run unless you run the bot locally with the daemons active.

---

## Project Layout

```
stock_analysis/
│
├── api/                         FastAPI backend
│   ├── config.py                  All settings (reads from .env / Secret Manager)
│   ├── db.py                      SQLAlchemy models (14 tables)
│   ├── auth.py                    JWT + Apple/Google token verification
│   ├── main.py                    App entry point, CORS, rate limiting
│   ├── services/
│   │   └── broker_service.py      CTBC Playwright wrapper (asyncio.to_thread)
│   └── routers/
│       ├── auth.py                POST /api/auth/{apple,google,device}
│       ├── oracle.py              GET  /api/oracle/{today,history,stats,live}
│       ├── signals.py             GET  /api/signals/{tw,us,search}  ← GCS cached
│       ├── news.py                GET  /api/news/{feed,pcr-history,related}
│       ├── weekly.py              GET  /api/weekly/signals + /{ticker}/history
│       ├── options.py             GET  /api/options/{screener,overview} + /{ticker}/history
│       ├── agents.py              GET  /api/agents/{analyze,batch}  ← Claude AI
│       ├── sandbox.py             GET/POST /api/sandbox/  (betting game)
│       ├── watchlist.py           CRUD /api/watchlist + /api/watchlist/alerts
│       ├── feed.py                GET/POST /api/feed + reactions
│       ├── notify.py              POST /api/notify/broadcast
│       ├── stocks.py              POST /api/stocks/settle (internal)
│       ├── subscribe.py           Telegram subscription page + API
│       ├── broker.py              GET/POST /api/broker/* (CTBC; X-Internal-Secret)
│       ├── tws.py                 GET /api/tws/universe|stock|lookup (TWS management)
│       ├── charts.py              GET /api/charts/ohlcv/{ticker} (yfinance OHLCV)
│       └── backtest.py            GET /api/backtest/{options,signals}
│
├── news/                        News + PCR pipeline package
│   ├── fetcher.py                 Google News RSS with deduplication (sha1)
│   ├── pcr.py                     yfinance put/call ratio extraction
│   └── related.py                 Jaccard keyword clustering for cross-links
│
├── tws/                         Taiwan signal pipeline
│   ├── core.py                    OHLCV sync + fundamentals (Yahoo Finance)
│   ├── taiwan_trending.py         apply_filters() — MA120 / Bias / RSI gate
│   ├── index_tracker.py           Oracle prediction + GCS read/write
│   ├── telegram_notifier.py       Telegram report builder (heatmap, buy list)
│   ├── models.py                  Ledoit-Wolf 5-day target price
│   └── utils.py                   TWSE fetchers, VADER sentiment
│
├── us/                          US signal pipeline (S&P 500)
│   ├── core.py                    USStockEngine — yfinance download + S&P 500 tickers
│   ├── finviz_data.py             Finviz screener wrapper (unusual vol, movers)
│   └── us_trending.py             Same filters as TW
│
├── options/                     US options screener package
│   ├── universe.py                get_options_universe() — Finviz + weekly + S&P 500 pre-filter
│   ├── fetcher.py                 fetch_options_metrics() — RSI, PCR, IV, OI per ticker
│   └── signals.py                 classify_signal() — buy/sell/unusual + 0-10 score
│
├── ai/                          AI analysis layer (Claude)
│   ├── agents.py                  6-agent + orchestrator (Haiku + Sonnet)
│   └── analyst.py                 Claude client singleton + prompts
│
├── brokers/                     Broker integrations (local only)
│   ├── ibkr.py                    Interactive Brokers
│   ├── moomoo.py                  Moomoo/Futu
│   ├── robinhood.py               Robinhood
│   └── manager.py                 BrokerManager aggregator
│
├── alembic/                     DB migrations
│   └── versions/
│       ├── 0001_initial_schema.py    Base 7 tables
│       ├── 0002_news_and_pcr.py      news_items + news_pcr_snapshots
│       ├── 0003_weekly_signals.py    weekly_signals
│       ├── 0004_options_signals.py   options_signals + options_iv_snapshots
│       ├── 0005_add_trades_table.py  trades (CTBC order journal)
│       └── 0006_add_tws_stock_cache.py  tws_stock_cache
│
├── web/                         Next.js 14 web dashboard (LokiStock brand)
│   ├── app/tws/                   Moomoo-style TWS stock management + ticker lookup
│   ├── app/charts/                High-low band chart (Recharts stacked Area)
│   ├── app/trading/               CTBC live trading — balance, positions, orders
│   ├── app/backtest/              Options + signals backtest + equity curve
│   ├── app/options/               Options screener + P&L calculator
│   ├── app/news/                  Two-pane PCR dashboard
│   ├── app/weekly/                Weekly ±5% contrarian signals
│   ├── app/subscribe/             Telegram subscription page
│   ├── app/sitemap.ts             Next.js native sitemap (SEO)
│   ├── app/layout.tsx             LokiStock brand, nav, footer
│   ├── components/                PcrChart, PcrBar, NewsCard, PcrLabel, etc.
│   ├── lib/api.ts                 fetch wrappers for all domains incl. broker
│   ├── lib/types.ts               TypeScript interfaces (single source of truth)
│   └── Dockerfile.web             Multi-stage Node 20 build
│
├── mobile/                      iOS app (Expo Router — LokiStock Oracle)
│   ├── app/(tabs)/                Tabs: Signals, Oracle, News, Community, Watchlist, Profile
│   ├── app/stock/[ticker].tsx     Enhanced: RSI gauge, foreign flow bars, signal banner
│   ├── app/trade-history.tsx      CTBC trade journal with filter pills
│   ├── app/create-post.tsx        Community post modal
│   ├── app/auth.tsx               Sign-in screen
│   ├── app.json                   Bundle: com.lokistock.oracle, min iOS 16.0
│   ├── eas.json                   EAS build profiles (preview + production)
│   ├── components/
│   │   ├── NewsCard.tsx           PCR bar + sentiment indicator card
│   │   ├── PcrBar.tsx             Red/green put/call volume split bar
│   │   └── PcrTimeline.tsx        Horizontal PCR snapshot history scroll
│   ├── store/auth.ts              Zustand — JWT + user state
│   ├── store/watchlist.ts         Zustand — watchlist (optimistic updates)
│   └── lib/api.ts                 Axios with Bearer token interceptor + broker namespace
│
├── master_run.py                Daily cron entry point
│                                  --step predict  (08:00 TST)
│                                  --step resolve  (14:05 TST)
├── news_pipeline.py             News + PCR poller (every 30 min market hours)
├── weekly_signal_pipeline.py    Monday contrarian trades — buy dip / sell rip
├── options_screener_pipeline.py Daily options screener (09:45 + 15:30 ET)
│                                  OPTIONS_DRY_RUN=true/false gates notifications
├── options_backtester.py        Validate RSI+PCR win rate vs WeeklySignal history
├── app.py                       Interactive Telegram bot — /options command added
├── backtester.py                Mean-reversion backtest engine
│
├── Dockerfile                   Full pipeline image (Playwright, brokers)
├── Dockerfile.api               Slim API image (no Chromium, ~300MB)
├── docker-compose.yml           Local dev: postgres + api + pipeline
│
├── setup-gcp.sh                 ← Run once to set up all GCP infrastructure
├── cloudbuild.yaml              CI/CD: 14 steps — build/push/deploy all services
├── cloud-run-service.yaml       oracle-api service spec
├── cloud-run-telegram.yaml      oracle-telegram-bot service spec (min 1 instance)
├── cloud-run-job-predict.yaml           oracle-predict Cloud Run Job spec
├── cloud-run-job-resolve.yaml           oracle-resolve Cloud Run Job spec
├── cloud-run-job-news.yaml              oracle-news-poller Cloud Run Job spec
├── cloud-run-job-weekly.yaml            oracle-weekly-signals Cloud Run Job spec
└── cloud-run-job-options-screener.yaml  oracle-options-screener Cloud Run Job spec
                                           (includes Cloud Scheduler gcloud commands)
```

---

## Claude Code MCP Integration

Oracle ships an MCP server that connects Claude Code to the Oracle API (and optionally TradingView Desktop).

### Setup

```bash
cd mcp
npm install
```

The `.claude/mcp.json` file in this repo registers it automatically when you open the project in Claude Code. Verify it's loaded:

```
/mcp
```

You should see `oracle` listed with status `connected`. No Oracle API running? Start it first:

```bash
docker compose up api postgres
```

### Available tools

**Oracle tools** (work without TradingView):
- `oracle_options_screener` — latest RSI+PCR+IV Rank signals scored 0-10
- `oracle_options_overview` — VIX, market PCR, signal counts
- `oracle_options_history` — 30-day signal history for one ticker
- `oracle_weekly_signals` — weekly ±5% contrarian signals
- `oracle_news_feed` — news + PCR sentiment feed
- `oracle_signal_search` — search TW/US signal stocks
- `oracle_backtest_results` — RSI+PCR win rate backtest
- `oracle_prediction` — today's TAIEX Oracle prediction + stats

**TradingView tools** (requires TV Desktop with `--remote-debugging-port=9222`):
- `chart_get_state`, `chart_set_symbol`, `chart_set_timeframe`, `chart_set_type`
- `chart_manage_indicator`, `chart_get_visible_range`, `chart_scroll_to_date`
- `pine_get_source`, `pine_set_source`, `pine_compile`, `pine_get_errors`
- `capture_screenshot`

See [mcp/SETUP.md](mcp/SETUP.md) for TradingView launch flags and security notes.

---

## Roadmap

### Completed
- [x] Taiwan + US signal pipeline (RSI + Bias + MA120, Ledoit-Wolf, institutional flow)
- [x] TAIEX Market Oracle (daily prediction + virtual coin scoring game)
- [x] Multi-agent AI analysis (6 Claude agents + orchestrator)
- [x] iOS app — LokiStock Oracle (Apple/Google auth, community feed, watchlist)
- [x] FastAPI backend on GCP Cloud Run + Cloud SQL (PostgreSQL)
- [x] GCP Cloud Scheduler cron jobs (predict + resolve + options screener + news)
- [x] News feed with put/call ratio — 12h rolling, PCR timeline, cross-related news
- [x] LokiStock web dashboard — TWS, Charts, Trading, Backtest, Options, News, Weekly pages
- [x] Telegram subscription page + subscriber count + daily automated reports
- [x] US weekly contrarian pipeline — ±5% movers, broker-executed trades
- [x] US options screener — RSI + PCR + IV Rank + unusual flow, twice daily, push delivery
- [x] Moomoo-style TWS stock management page (split pane, RSI gauge, foreign flow, inline chart)
- [x] High-low band chart page (Recharts stacked Area, period selector, volume)
- [x] Options P&L calculator (call/put payoff at expiry, configurable strikes)
- [x] Options + signals backtesting page (equity curve, win-rate cards, trades table)
- [x] CTBC Win168 broker integration — live balance, positions, orders, order placement
- [x] Trade journal (`trades` table) — full order history, status, realized P&L
- [x] TWS DB-first ticker lookup — DB cache → universe → yfinance fetch+persist
- [x] iOS enhanced stock detail — RSI gauge, foreign flow bars (F5/F20/F60), signal banner
- [x] iOS trade history screen with filter pills
- [x] iOS CTBC portfolio section in Profile tab
- [x] App Store readiness — bundle `com.lokistock.oracle`, iOS 16.0 min, privacy manifest
- [x] SEO sitemap at `/sitemap.xml`

### In Progress / Upcoming
- [ ] IV Rank accuracy improves after 30 trading days of snapshot accumulation
- [ ] EAS credentials + first TestFlight build (fill in `appleId`, `ascAppId` in `eas.json`)
- [ ] CTBC `alembic upgrade head` in production (migrations 0005 + 0006 pending on live DB)
- [ ] App Store submission
- [ ] Push notification for TWS signal stocks (when signal fires, notify watchlisted users)
- [ ] LSTM / Transformer deep-learning price prediction
- [ ] Multi-broker support (IBKR, Moomoo) via the existing `brokers/` adapters
