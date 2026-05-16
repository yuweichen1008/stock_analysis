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
WEEKLY_DRY_RUN=true python weekly_signal_pipeline.py        # Monday ±5% movers (dry run)
OPTIONS_DRY_RUN=true python options_screener_pipeline.py    # RSI+PCR+IV screener (dry run)
python news_pipeline.py                                      # news + PCR poller
python app.py                                                # Telegram bot
```

### Tests
```bash
pytest                                  # all Python tests
pytest tests/test_options_signals.py   # signal logic unit tests only
cd web && npm test                      # Vitest web helper tests
```

### MCP Server
```bash
cd mcp && npm install
node mcp/server.js                     # verify it starts
```
Add to `.claude/settings.json` mcpServers — see `mcp/server.js` header for config.

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
- **`api/db.py`** — SQLAlchemy models for all 14 tables:
  `users`, `bets`, `stock_bets`, `watchlist`, `posts`, `reactions`,
  `news_items`, `news_pcr_snapshots`, `weekly_signals`, `subscribers`,
  `options_iv_snapshots`, `options_signals`, `trades`, `tws_stock_cache`
- **`api/routers/`** — one file per domain:
  `oracle.py`, `signals.py`, `sandbox.py`, `stocks.py`, `news.py`, `weekly.py`,
  `feed.py`, `watchlist.py`, `agents.py`, `graph.py`, `auth.py`, `notify.py`,
  `subscribe.py`, `options.py`, `broker.py`, `tws.py`, `charts.py`, `backtest.py`
- Auth is JWT-based; login via Apple ID, Google OAuth, or anonymous device ID (`api/auth.py`)
- Trending signals are cached in memory (1h TTL); raw CSVs live in GCS
- Broker endpoints (`/api/broker/*`) require `X-Internal-Secret` header

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

**Options Screener (twice daily, market hours):**
- `options_screener_pipeline.py` — RSI(14) + put/call ratio + IV Rank for ~200 US tickers
- `options/signals.py` — `classify_signal()`: unusual_activity | buy_signal | sell_signal, scored 0–10
- `options/fetcher.py` — yfinance options chain + RSI computation
- Results stored in `options_signals` + `options_iv_snapshots` tables
- Cloud Run job: `oracle-options-screener` (14:45 UTC / 20:30 UTC weekdays)
- Controlled by `OPTIONS_DRY_RUN` env var (true = no notifications)

**News + PCR (every 30 min, market hours):**
- `news/fetcher.py` — Google News RSS for signal tickers
- `news/pcr.py` — US: real put/call ratio from yfinance options chain; TW: VADER NLP proxy
- `news/related.py` — Jaccard similarity for related articles
- Results stored in `news_items` + `news_pcr_snapshots` tables

### MCP Server: `mcp/`
- `mcp/server.js` — MCP entry point; registers all tool groups
- `mcp/tools/chart.js` — chart control (symbol, timeframe, type, indicators, scroll)
- `mcp/tools/pine.js` — Pine Script read/write/compile/errors
- `mcp/tools/capture.js` — screenshot capture
- `mcp/tools/data.js` — OHLCV data, indicator values, price alerts, Pine console
- `mcp/tools/oracle.js` — Oracle API tools (options screener, weekly signals, prediction)
- Requires TradingView Desktop with `--remote-debugging-port=9222`

### Tests
- `tests/test_options_signals.py` — 53 unit tests for signal classification logic (no DB/network)
- `tests/test_options_fetcher.py` — 10 tests for RSI computation
- `tests/test_options_api.py` — 22 integration tests via FastAPI TestClient + SQLite StaticPool
- `web/__tests__/helpers.test.ts` — 28 Vitest tests for web helper functions

### Mobile App: `mobile/`
- Expo 54 / React Native; tabs: Movers, Signals, Weekly, Backtest, News, Community, Oracle, Profile
- `mobile/lib/api.ts` — Axios client and all API response types (single source of truth for mobile types)
- State management: Zustand (`mobile/store/`)
- Auth flow: `mobile/app/auth.tsx` → JWT stored in SecureStore

### Web Dashboard: `web/`
- Next.js 14 + TailwindCSS + Recharts; brand: **LokiStock** (lokistock.com)
- `web/lib/types.ts` — TypeScript interfaces mirroring API responses
- `web/lib/api.ts` — fetch wrapper with broker namespace (passes `X-Internal-Secret`)
- `web/app/sitemap.ts` — Next.js native sitemap for SEO
- Pages:
  - `/tws` — Moomoo-style TWS stock management: left list + right detail with inline chart, RSI gauge, foreign flow bars; Enter-key ticker lookup (DB-first → yfinance)
  - `/charts` — High-low band chart (stacked Recharts Area), period/market selector, volume
  - `/backtest` — Options win-rate backtest + signals equity curve + trades table
  - `/trading` — CTBC live trading dashboard: balance, positions, order form, trade history
  - `/options` — Options screener + RSI/PCR chart + P&L calculator
  - `/news` — News feed + PCR timeline
  - `/weekly` — Weekly ±5% contrarian signals
  - `/subscribe` — Telegram subscription
- `next.config.js` proxies `/api/*` → Cloud Run API service

### AI Agents: `ai/`
Called from `api/routers/agents.py` via Anthropic Claude API. Used for stock analysis and news sentiment.

### Infrastructure
- **Two Docker images:** `Dockerfile.api` (slim, for API + web services) and `Dockerfile` (full, includes Playwright for scraping, used by pipeline jobs)
- **Cloud Run Jobs:** `predict`, `resolve`, `oracle-news-poller`, `oracle-weekly-signals`, `oracle-options-screener`
- **Cloud Run Services:** `oracle-api`, `oracle-web`, `oracle-telegram-bot`
- **`cloudbuild.yaml`** — 16-step build: builds images → runs Alembic migration → deploys all services and jobs
- **Migrations:** Alembic; files in `alembic/versions/`; always run `alembic upgrade head` after pulling

### Key Environment Variables
```
DATABASE_URL                  # PostgreSQL connection string (port 5433 in local dev)
GCS_BUCKET                    # {project}-oracle-signals
INTERNAL_API_SECRET           # guards /api/broker/* and pipeline → API calls
ANTHROPIC_API_KEY             # Claude AI agents
TELEGRAM_BOT_TOKEN
WEEKLY_DRY_RUN                # true/false — gates live broker trades
OPTIONS_DRY_RUN               # true/false — gates push notifications for options signals
ORACLE_API_BASE               # Oracle API URL (for pipelines + Telegram bot)
ORACLE_API_URL                # Oracle API URL (for Next.js → API proxy)
CTBC_ID                       # CTBC Win168 account ID
CTBC_PASSWORD                 # CTBC Win168 password
CTBC_DRY_RUN                  # true = log orders only, false = submit real orders
NEXT_PUBLIC_INTERNAL_SECRET   # same as INTERNAL_API_SECRET — used by web Trading page
NEXT_PUBLIC_API_BASE          # API base URL for web (empty = relative, set for external)
ROBINHOOD_USERNAME / ROBINHOOD_PASSWORD
```

### Alembic Migrations
```
0001_initial_schema.py    — base 7 tables (users, bets, watchlist, posts…)
0002_news_and_pcr.py      — news_items + news_pcr_snapshots
0003_weekly_signals.py    — weekly_signals
0004_options_signals.py   — options_signals + options_iv_snapshots
0005_add_trades_table.py  — trades (broker-executed orders)
0006_add_tws_stock_cache.py — tws_stock_cache (DB-first ticker lookup)
```
Run `alembic upgrade head` whenever pulling — especially required after 0005/0006 for the Trading and TWS pages.

<!-- rtk-instructions v2 -->
# RTK (Rust Token Killer) - Token-Optimized Commands

## Golden Rule

**Always prefix commands with `rtk`**. If RTK has a dedicated filter, it uses it. If not, it passes through unchanged. This means RTK is always safe to use.

**Important**: Even in command chains with `&&`, use `rtk`:
```bash
# ❌ Wrong
git add . && git commit -m "msg" && git push

# ✅ Correct
rtk git add . && rtk git commit -m "msg" && rtk git push
```

## RTK Commands by Workflow

### Build & Compile (80-90% savings)
```bash
rtk cargo build         # Cargo build output
rtk cargo check         # Cargo check output
rtk cargo clippy        # Clippy warnings grouped by file (80%)
rtk tsc                 # TypeScript errors grouped by file/code (83%)
rtk lint                # ESLint/Biome violations grouped (84%)
rtk prettier --check    # Files needing format only (70%)
rtk next build          # Next.js build with route metrics (87%)
```

### Test (60-99% savings)
```bash
rtk cargo test          # Cargo test failures only (90%)
rtk go test             # Go test failures only (90%)
rtk jest                # Jest failures only (99.5%)
rtk vitest              # Vitest failures only (99.5%)
rtk playwright test     # Playwright failures only (94%)
rtk pytest              # Python test failures only (90%)
rtk rake test           # Ruby test failures only (90%)
rtk rspec               # RSpec test failures only (60%)
rtk test <cmd>          # Generic test wrapper - failures only
```

### Git (59-80% savings)
```bash
rtk git status          # Compact status
rtk git log             # Compact log (works with all git flags)
rtk git diff            # Compact diff (80%)
rtk git show            # Compact show (80%)
rtk git add             # Ultra-compact confirmations (59%)
rtk git commit          # Ultra-compact confirmations (59%)
rtk git push            # Ultra-compact confirmations
rtk git pull            # Ultra-compact confirmations
rtk git branch          # Compact branch list
rtk git fetch           # Compact fetch
rtk git stash           # Compact stash
rtk git worktree        # Compact worktree
```

Note: Git passthrough works for ALL subcommands, even those not explicitly listed.

### GitHub (26-87% savings)
```bash
rtk gh pr view <num>    # Compact PR view (87%)
rtk gh pr checks        # Compact PR checks (79%)
rtk gh run list         # Compact workflow runs (82%)
rtk gh issue list       # Compact issue list (80%)
rtk gh api              # Compact API responses (26%)
```

### JavaScript/TypeScript Tooling (70-90% savings)
```bash
rtk pnpm list           # Compact dependency tree (70%)
rtk pnpm outdated       # Compact outdated packages (80%)
rtk pnpm install        # Compact install output (90%)
rtk npm run <script>    # Compact npm script output
rtk npx <cmd>           # Compact npx command output
rtk prisma              # Prisma without ASCII art (88%)
```

### Files & Search (60-75% savings)
```bash
rtk ls <path>           # Tree format, compact (65%)
rtk read <file>         # Code reading with filtering (60%)
rtk grep <pattern>      # Search grouped by file (75%). Format flags (-c, -l, -L, -o, -Z) run raw.
rtk find <pattern>      # Find grouped by directory (70%)
```

### Analysis & Debug (70-90% savings)
```bash
rtk err <cmd>           # Filter errors only from any command
rtk log <file>          # Deduplicated logs with counts
rtk json <file>         # JSON structure without values
rtk deps                # Dependency overview
rtk env                 # Environment variables compact
rtk summary <cmd>       # Smart summary of command output
rtk diff                # Ultra-compact diffs
```

### Infrastructure (85% savings)
```bash
rtk docker ps           # Compact container list
rtk docker images       # Compact image list
rtk docker logs <c>     # Deduplicated logs
rtk kubectl get         # Compact resource list
rtk kubectl logs        # Deduplicated pod logs
```

### Network (65-70% savings)
```bash
rtk curl <url>          # Compact HTTP responses (70%)
rtk wget <url>          # Compact download output (65%)
```

### Meta Commands
```bash
rtk gain                # View token savings statistics
rtk gain --history      # View command history with savings
rtk discover            # Analyze Claude Code sessions for missed RTK usage
rtk proxy <cmd>         # Run command without filtering (for debugging)
rtk init                # Add RTK instructions to CLAUDE.md
rtk init --global       # Add RTK to ~/.claude/CLAUDE.md
```

## Token Savings Overview

| Category | Commands | Typical Savings |
|----------|----------|-----------------|
| Tests | vitest, playwright, cargo test | 90-99% |
| Build | next, tsc, lint, prettier | 70-87% |
| Git | status, log, diff, add, commit | 59-80% |
| GitHub | gh pr, gh run, gh issue | 26-87% |
| Package Managers | pnpm, npm, npx | 70-90% |
| Files | ls, read, grep, find | 60-75% |
| Infrastructure | docker, kubectl | 85% |
| Network | curl, wget | 65-70% |

Overall average: **60-90% token reduction** on common development operations.
<!-- /rtk-instructions -->