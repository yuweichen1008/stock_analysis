# TWS automation (tws)

This folder contains code for short-term and day-trading automation for Taiwan Stock Exchange (TWS). It is designed to run as a scheduled task (cron or Cloud Scheduler -> Cloud Function). The pipeline:

- Run short-term signal scans (MA120 + RSI mean-reversion) via `taiwan_trending.py`
- Persist results to `current_trending.csv`
- Optionally push results into BigQuery via `bq_helper.py`
- Notify subscribers via Telegram using `telegram_notifier.py`

Files
- `taiwan_trending.py` — main scan and algorithm logic (MA120 + RSI short-term signals). 120-day MA to indicate health; RSI < 30 for oversold mean-reversion setups.
- `telegram_notifier.py` — builds and sends a Markdown report to Telegram subscribers (uses `tws.utils.TelegramTool`).
- `utils.py` — small utilities and `TelegramTool` wrapper.
- `models.py` — simple AI helper to produce a 5-day target price estimate.
- `bq_helper.py` — helper to push trending results to BigQuery.
- `cloud_function.py` — GCP Cloud Function entrypoint (HTTP or Pub/Sub) that runs the scan, writes to BigQuery, and notifies Telegram.

Design & Algorithm Notes
- Short-term (day/short swing) algorithm:
  - Universe: tickers read from `data/tickers/top20_*.csv`, excluding ETF codes (00 prefix).
  - Data: OHLCV CSVs in `data/ohlcv/*` named as `<ticker>_YYYYMMDD.csv`.
  - Filters: require at least 120 rows; compute MA120 and RSI(14).
  - Signal: price > MA120 (trend healthy) AND RSI < 30 (oversold) -> mean reversion trigger.
  - Output: `current_trending.csv` with tickers and metrics.

Automation & GCP Deployment
- Cloud Function configuration (recommended):
  - Runtime: Python 3.11 (or 3.10)
  - Entry point: `tws.cloud_function.tws_handler`
  - Trigger: HTTP (protected with IAP or a secret token) or Pub/Sub from Cloud Scheduler
  - Memory: 256MB+ (Selenium not used in cloud function path)
  - Environment variables:
    - TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    - GOOGLE_CLOUD_PROJECT (or GCP_PROJECT)
    - BQ_DATASET (optional)
    - BQ_TABLE (optional)

- Cloud Scheduler (recommended approach):
  - Create an HTTP job that calls the Cloud Function URL (or publish to a Pub/Sub topic that triggers `pubsub_tws`).
  - Schedule: every trading day (cron e.g., `0 9 * * 1-5` — adjust for exchange holidays).

Local development & cron
- You can run `taiwan_trending.run_taiwan_trending(<repo_root>)` locally or run `python -m tws.taiwan_trending` from the repository root.
- To run from a traditional server cron, call the script in the repo and ensure environment variables are set for Telegram and GCP credentials (if pushing to BigQuery).

Security & Notes
- Do NOT commit `.env` or credentials to the repo. Add them to Secret Manager in GCP and load at runtime.
- If you must store secrets locally for testing, keep them out of git and add them to `.gitignore`.

Next improvements
- Replace simple CSV storage with a small managed store (Cloud Storage) for raw OHLCV and use BigQuery for structured access.
- Add unit tests for parsing and notification code. Use mocks for `requests` and BigQuery.
- Optionally add Playwright-based scrapers for live market sources and run them in Cloud Run if Selenium is required.
To help you manage your Taiwan Stock Screener project, I have drafted a professional `README.md` that reflects the new architecture, including the **Company Mapping**, **Trend Analysis**, and **News Integration** features.

## ⚙️ Configuration

**Clone the repository** and install dependencies:
```bash
pip install pandas yfinance requests python-dotenv
```

### 📁 Project Structure Overview

Based on our recent updates, your folder should now look like this:

```text
tws/
├── data/
│   ├── tickers/          # Daily Top 20 lists from TWSE
│   ├── ohlcv/            # Historical price data (CSV)
│   └── company/          # company_mapping.csv (Names, Industry, PE)
├── init_historical_data.py # Data sync & ETF filtering
├── get_company_info.py     # TWSE API Industry & PE mapping
├── current_trending.py     # MA5/20/120 Trend Screener
├── telegram_notifier.py    # Top 10 + Google News + Telegram Bot
└── README.md               # Instructions & Logic documentation
```


---

### 📝 Updated README.md

```markdown
# 🚀 Taiwan Stock Trend Screener & Notifier

An automated tool for identifying high-volume, upward-trending Taiwan stocks. It filters out ETFs, applies strict Moving Average (MA) discipline, and sends a daily Top 10 report with real-time news context to Telegram.

## 🛠️ System Architecture

1. **Initialization (`init_historical_data.py`)**: 
   - Fetches Top 20 high-volume tickers daily.
   - Padds leading zeros (e.g., `2330`) and filters out ETFs (starting with `00`).
   - Syncs 250 days of OHLCV data for MA120 calculation.
2. **Company Mapping (`get_company_info.py`)**: 
   - Maps tickers to Chinese company names and industries using TWSE OpenAPI.
   - Collects daily P/E ratios and handles null/nan values.
3. **Trend Screener (`current_trending.py`)**: 
   - Applies the "Life Line" filter: **Price must be above MA120**.
   - Identifies short-term strength: **Price > MA5 and Price > MA20**.
4. **Notifier (`telegram_notifier.py`)**: 
   - Selects the **Top 10** candidates.
   - Scrapes **Google News RSS** for the latest 24h headlines (Rising Reasons).
   - Delivers a formatted report to Telegram.

## 📈 Investment Discipline (投資紀律)

- **The Life Line**: Never touch a stock below the MA120 (長期生死線).
- **No Fantasy**: Exit unconditionally if the price breaks below the MA5 or MA20.
- **Risk Management**: Strict 3% Stop-Loss; take partial profits at 20%.

## 🚀 Execution Guide

### 1. Install Dependencies
```bash
pip install pandas yfinance requests
```

### 2. Manual Run Sequence
```bash
python get_company_info.py      # Update company names/sectors
python init_historical_data.py  # Sync historical prices
python current_trending.py      # Run the screener
python telegram_notifier.py     # Send news & report
```

## ⏰ Automation Setup (Crontab)

To ensure the virtual environment is utilized, point the crontab directly to the environment's python binary:

1. Get your venv path: `source .venv/bin/activate && which python`
2. Add to `crontab -e`:
   `30 15 * * 1-5 /path/to/tws/.venv/bin/python /path/to/tws/master_run.py >> /path/to/tws/cron.log 2>&1`
