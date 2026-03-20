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
