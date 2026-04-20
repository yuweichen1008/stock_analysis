# Oracle — AI Stock Screener

An iOS app that shows you which Taiwan and US stocks are worth looking at today. Every trading day it scans thousands of stocks, scores them, runs AI analysis, and sends a Telegram report — all automatically on Google Cloud.

---

## What It Does (ELI5)

Imagine you want to buy a stock that's temporarily on sale but is fundamentally healthy. Oracle finds those stocks for you every day:

1. **8:00 AM (Taiwan time)** — Oracle predicts whether the TAIEX index will go up or down today, using 5 market signals (S&P 500 overnight, VIX fear gauge, momentum, etc.)
2. **2:05 PM** — After the market closes, Oracle checks if it was right, runs the signal scan, and sends you a Telegram report with today's best stock picks
3. **iOS app** — Browse signals, bet virtual coins on the daily prediction, save stocks to a watchlist, read community trade ideas

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

## Architecture

```
Cloud Scheduler
  ├─ 08:00 TST Mon-Fri ──► Cloud Run Job: oracle-predict
  │                            compute Bull/Bear prediction
  │                            → save oracle_history.csv → GCS
  │                            → Telegram prediction message
  │                            → push notification to iOS users
  │
  └─ 14:05 TST Mon-Fri ──► Cloud Run Job: oracle-resolve
                               sync OHLCV data from TWSE
                               resolve today's prediction
                               → settle virtual coin bets (POST /api/sandbox/settle)
                               run TW + US signal scan
                               → upload current_trending.csv → GCS
                               → Telegram reports (heatmap, buy list)
                               → push notifications (POST /api/notify/broadcast)

Cloud Run Services
  ├─ oracle-api (min 0 → scales to zero, max 10)
  │    reads oracle_history.csv    ◄── GCS
  │    reads current_trending.csv  ◄── GCS  (cached 1h in memory)
  │    serves the iOS app
  │
  └─ oracle-telegram-bot (min 1 → always on)
       polls Telegram
       responds to ticker lookups and broker commands

Cloud SQL PostgreSQL
  └─ users, bets, stock_bets, watchlist, posts, reactions, subscribers

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

# 3. (optional) Run the signal pipeline once to generate data
docker compose --profile pipeline run pipeline python master_run.py --step resolve
```

API is at `http://localhost:8080`. Interactive docs at `http://localhost:8080/docs`.

### `.env` secrets

**Required for local dev:**
```env
DATABASE_URL=postgresql+psycopg2://oracle:oracle_dev_password@localhost:5432/oracle
JWT_SECRET=any-random-string-32-chars-minimum
INTERNAL_API_SECRET=another-random-string
```

**Required for pipeline + Telegram:**
```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_channel_id
```

**Required for AI analysis:**
```env
ANTHROPIC_API_KEY=sk-ant-...
```

**Optional (GCS, auth):**
```env
GCS_BUCKET=                   # leave empty in local dev; set in prod
GOOGLE_CLIENT_ID=             # Google OAuth
APPLE_TEAM_ID=                # Apple Sign-In
APPLE_CLIENT_ID=              # Apple Sign-In bundle ID
ORACLE_API_BASE=http://localhost:8080   # pipeline → API callouts
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
- Creates all 11 secrets in Secret Manager
- Grants Cloud Build the IAM roles it needs
- Creates the two Cloud Scheduler jobs (predict + resolve)
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

Cloud Build does 10 steps automatically:
1. Build slim API Docker image (`Dockerfile.api`)
2. Build full pipeline Docker image (`Dockerfile`)
3–4. Push both images to Artifact Registry
5. Deploy Alembic migration job (schema setup)
6. Run the migration (creates all 7 tables in Cloud SQL)
7. Deploy `oracle-api` Cloud Run service
8. Deploy `oracle-telegram-bot` Cloud Run service
9. Deploy `oracle-predict` Cloud Run Job
10. Deploy `oracle-resolve` Cloud Run Job

### Step 4 — Update `ORACLE_API_BASE` after first deploy

The pipeline jobs call the API to settle bets and send push notifications. After step 3, get your Cloud Run URL and update the secret:

```bash
gcloud run services describe oracle-api --region=us-central1 --format='value(status.url)'
# → https://oracle-api-xxxx-uc.a.run.app

gcloud secrets versions add ORACLE_API_BASE --data-file=- <<< 'https://oracle-api-xxxx-uc.a.run.app'
```

### Step 5 — Test everything

```bash
# Health check (should show db: "ok")
curl https://oracle-api-xxxx-uc.a.run.app/health

# Manually trigger predict job
gcloud run jobs execute oracle-predict --region=us-central1 --wait

# Check Cloud Scheduler
gcloud scheduler jobs list --location=us-central1
```

---

## Cron Schedule

| Job | When (TST) | Days | What it does | Max runtime |
|-----|-----------|------|-------------|-------------|
| `oracle-predict` | 08:00 | Mon–Fri | Compute TAIEX Bull/Bear prediction → GCS → Telegram + push | 10 min |
| `oracle-resolve` | 14:05 | Mon–Fri | Sync OHLCV → resolve Oracle → settle bets → TW signals → GCS → Telegram | 15 min |

The Telegram bot (`oracle-telegram-bot`) runs continuously and responds in real-time to commands.

For the **US pipeline** (S&P 500, after 16:00 ET = ~05:00 TST next day), run manually or add a third scheduler job:
```bash
gcloud run jobs execute oracle-resolve --region=us-central1 \
  --override-args="--market,US"
```

---

## API Endpoints

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
| `POST /api/sandbox/settle` | X-API-Secret | Settle bets (called by pipeline) |
| `POST /api/notify/broadcast` | X-API-Secret | Send push notifications (called by pipeline) |
| `POST /api/stocks/settle` | X-API-Secret | Settle stock bets (called by pipeline) |

---

## Database Schema

```
users           id, auth_provider (apple/google/device), auth_id, email,
                display_name, avatar_url, coins, push_token

subscribers     telegram_id, active  (Telegram opt-in for daily reports)

bets            user_id→users, date, direction (Bull/Bear), amount, payout

stock_bets      user_id→users, ticker, direction, entry/exit price, payout

watchlist       user_id→users, ticker, market  [unique per user+ticker+market]

posts           user_id→users, ticker, content (280 chars), signal_type

reactions       user_id→users, post_id→posts, emoji_type  [unique per user+post]
```

Migrations managed by Alembic → `alembic/versions/0001_initial_schema.py`.

---

## Mobile App Setup

```bash
cd mobile
npm install
npx expo start          # local dev (point to localhost:8080)
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
| 👥 Community | Post trade ideas · react with 🐂🐻🔥 · market filter |
| ⭐ Watchlist | Saved tickers · today's signal alerts |
| 👤 Profile | Coins · leaderboard rank · sign out |

---

## Telegram Commands

| Command | What it does |
|---------|-------------|
| Send a 4-digit code | Fundamentals + AI target price for any Taiwan stock |
| `/balance` | Cash + net value across connected brokers |
| `/positions` | Open holdings |
| `/orders [days]` | Recent order history (default: 7 days) |

**Daily automated reports (sent to `TELEGRAM_CHAT_ID`):**

| Time (TST) | Report |
|-----------|--------|
| 08:00 | TAIEX Bull/Bear prediction + 5-factor breakdown + confidence % |
| 14:05 | Prediction result + TAIEX change + points earned + streak |
| 14:05 | Full-market heatmap (1068 stocks, 4000×2400 px) + sector zoom charts |
| 14:05 | Signal buy list — RSI, bias, score, foreign flow, sentiment per ticker |

> **Note:** Broker commands (`/balance`, `/positions`, `/orders`) require a local broker daemon (IBKR TWS, Moomoo OpenD). These won't work on Cloud Run unless you run the bot locally with the daemons active.

---

## Project Layout

```
stock_analysis/
│
├── api/                         FastAPI backend
│   ├── config.py                  All settings (reads from .env / Secret Manager)
│   ├── db.py                      SQLAlchemy models (7 tables)
│   ├── auth.py                    JWT + Apple/Google token verification
│   ├── main.py                    App entry point, CORS, rate limiting
│   └── routers/
│       ├── auth.py                POST /api/auth/{apple,google,device}
│       ├── oracle.py              GET  /api/oracle/{today,history,stats,live}
│       ├── signals.py             GET  /api/signals/{tw,us,search}  ← GCS cached
│       ├── agents.py              GET  /api/agents/{analyze,batch}  ← Claude AI
│       ├── sandbox.py             GET/POST /api/sandbox/  (betting game)
│       ├── watchlist.py           CRUD /api/watchlist + /api/watchlist/alerts
│       ├── feed.py                GET/POST /api/feed + reactions
│       ├── notify.py              POST /api/notify/broadcast (internal)
│       ├── stocks.py              POST /api/stocks/settle (internal)
│       └── subscribe.py           Telegram subscription page + API
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
│   ├── core.py                    USStockEngine — yfinance download
│   └── us_trending.py             Same filters as TW
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
│   └── versions/0001_initial_schema.py
│
├── mobile/                      iOS app (Expo Router)
│   ├── app/(tabs)/                5 main tabs
│   ├── app/stock/[ticker].tsx     Stock detail + AI analysis screen
│   ├── app/create-post.tsx        Community post modal
│   ├── app/auth.tsx               Sign-in screen
│   ├── store/auth.ts              Zustand — JWT + user state
│   ├── store/watchlist.ts         Zustand — watchlist (optimistic updates)
│   └── lib/api.ts                 Axios with Bearer token interceptor
│
├── master_run.py                Daily cron entry point
│                                  --step predict  (08:00 TST)
│                                  --step resolve  (14:05 TST)
│                                  --market US     (manual US run)
├── app.py                       Interactive Telegram bot (always-on)
├── backtester.py                Mean-reversion backtest engine
│
├── Dockerfile                   Full pipeline image (Playwright, brokers)
├── Dockerfile.api               Slim API image (no Chromium, ~300MB)
├── docker-compose.yml           Local dev: postgres + api + pipeline
│
├── setup-gcp.sh                 ← Run once to set up all GCP infrastructure
├── cloudbuild.yaml              CI/CD: builds both images, runs migrations, deploys all
├── cloud-run-service.yaml       oracle-api service spec
├── cloud-run-telegram.yaml      oracle-telegram-bot service spec (min 1 instance)
├── cloud-run-job-predict.yaml   oracle-predict Cloud Run Job spec
└── cloud-run-job-resolve.yaml   oracle-resolve Cloud Run Job spec
```

---

## Roadmap

- [x] Taiwan + US signal pipeline (RSI + Bias + MA120, Ledoit-Wolf, institutional flow)
- [x] TAIEX Market Oracle (daily prediction + scoring game)
- [x] Multi-agent AI analysis (6 Claude agents + orchestrator)
- [x] iOS app — 5 tabs, Apple/Google auth, community feed, watchlist
- [x] FastAPI backend on GCP Cloud Run + Cloud SQL
- [x] GCP Cloud Scheduler cron jobs (predict + resolve)
- [ ] US pipeline auto-scheduled on Cloud Scheduler
- [ ] LSTM / Transformer deep-learning price prediction
- [ ] App Store release
