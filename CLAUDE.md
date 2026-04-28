# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend API
```bash
uvicorn api.main:app --reload --port 8000   # dev server; docs at /docs
pytest                                        # run tests
alembic upgrade head                          # apply migrations
alembic revision --autogenerate -m "desc"    # generate new migration
```

### Mobile (Expo / React Native)
```bash
cd mobile
npm install
npm start          # Expo dev server
npm run ios        # iOS simulator
```

### Web (Next.js)
```bash
cd web
npm install
npm run dev        # localhost:3000
npm run build
npm run lint
```

### Local Dev Stack
```bash
docker compose up                              # PostgreSQL + API (port 8000)
docker compose --profile pipeline up pipeline  # include data pipeline
```

### Pipelines (run locally or via Cloud Run jobs)
```bash
WEEKLY_DRY_RUN=true python weekly_signal_pipeline.py   # Monday ±5% movers (dry run)
python news_pipeline.py                                  # news + PCR poller
python app.py                                            # Telegram bot
```

### Cloud Deployment
```bash
gcloud builds submit --config cloudbuild.yaml   # full deploy (all services + jobs)
bash setup-gcp.sh                               # one-time GCP infrastructure setup
```

## Architecture

### System Overview
Oracle is a multi-platform stock signal + options sentiment app with three client surfaces: an iOS app (React Native/Expo), a web dashboard (Next.js), and a Telegram bot. All clients talk to a FastAPI backend on Cloud Run backed by Cloud SQL (PostgreSQL) and GCS.

### Backend: `api/`
- **`api/main.py`** — FastAPI app entry point; mounts all routers, configures CORS
- **`api/db.py`** — SQLAlchemy models for all 10+ tables (`users`, `bets`, `stock_bets`, `watchlist`, `posts`, `reactions`, `news_items`, `news_pcr_snapshots`, `weekly_signals`, `subscribers`)
- **`api/routers/`** — one file per domain: `oracle.py`, `signals.py`, `sandbox.py`, `stocks.py`, `news.py`, `weekly.py`, `feed.py`, `watchlist.py`, `agents.py`, `graph.py`, `auth.py`, `notify.py`, `subscribe.py`
- Auth is JWT-based; login via Apple ID, Google OAuth, or anonymous device ID (`api/auth.py`)
- Trending signals are cached in memory (1h TTL); raw CSVs live in GCS

### Signal Pipelines
There are two signal domains:

**Taiwan (TAIEX-based):**
- `tws/core.py` — syncs OHLCV from TWSE, computes RSI/MA/bias, scores 0–10
- Signal criteria: price above MA120 **and** bias < −2% **and** RSI(14) < 35
- Daily Cloud Run jobs: `predict` (08:00 TST) → `resolve` (14:05 TST)

**US (weekly contrarian):**
- `us/core.py` — downloads 4500+ NASDAQ tickers, computes weekly returns
- `weekly_signal_pipeline.py` — BUY stocks down ≥5%, SELL stocks up ≥5% (fade momentum)
- Executes $5 real trades via broker integrations in `brokers/`; controlled by `WEEKLY_DRY_RUN` env var

**News + PCR (every 30 min, market hours):**
- `news/fetcher.py` — Google News RSS for signal tickers
- `news/pcr.py` — US: real put/call ratio from yfinance options chain; TW: VADER NLP proxy
- `news/related.py` — Jaccard similarity for related articles
- Results stored in `news_items` + `news_pcr_snapshots` tables

### Mobile App: `mobile/`
- Expo 54 / React Native; tabs: Movers, Signals, Weekly, Backtest, News, Community, Oracle, Profile
- `mobile/lib/api.ts` — Axios client and all API response types (single source of truth for mobile types)
- State management: Zustand (`mobile/store/`)
- Auth flow: `mobile/app/auth.tsx` → JWT stored in SecureStore

### Web Dashboard: `web/`
- Next.js 14 + TailwindCSS + Recharts
- `web/lib/types.ts` — TypeScript interfaces mirroring API responses
- `web/lib/api.ts` — fetch wrapper
- Pages: `/news` (feed + PCR timeline charts), `/weekly` (contrarian signals), `/subscribe` (Telegram)
- `next.config.js` proxies `/api/*` → Cloud Run API service

### AI Agents: `ai/`
Called from `api/routers/agents.py` via Anthropic Claude API. Used for stock analysis and news sentiment.

### Infrastructure
- **Two Docker images:** `Dockerfile.api` (slim, for API + web services) and `Dockerfile` (full, includes Playwright for scraping, used by pipeline jobs)
- **Cloud Run Jobs:** `predict`, `resolve`, `oracle-news-poller`, `oracle-weekly-signals`
- **Cloud Run Services:** `oracle-api`, `oracle-web`, `oracle-telegram-bot`
- **`cloudbuild.yaml`** — 15-step build: builds images → runs Alembic migration → deploys all services and jobs
- **Migrations:** Alembic; files in `alembic/versions/`; always run `alembic upgrade head` after pulling

### Key Environment Variables
```
DATABASE_URL          # PostgreSQL connection string
GCS_BUCKET            # {project}-oracle-signals
INTERNAL_API_SECRET   # for internal Cloud Run job → API calls
ANTHROPIC_API_KEY     # Claude AI agents
TELEGRAM_BOT_TOKEN
WEEKLY_DRY_RUN        # true/false — gates live broker trades
ROBINHOOD_USERNAME / ROBINHOOD_PASSWORD
```
