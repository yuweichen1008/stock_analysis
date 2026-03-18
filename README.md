# 📈 Stock Analysis & AI Trading Framework

A professional collection of stock analysis tools, AI trading algorithms, and automated screening pipelines. This repository supports both machine learning research and rule-based technical analysis for global and Taiwan markets.

## 🌟 Key Features

* **TWS Market Automation**: A complete daily pipeline for the Taiwan Stock Exchange (TWSE) including data fetching, trend screening, and Telegram reporting.
* **AI Trading Algorithms**: Implementations of triple-barrier labeling and financial time series forecasting.
* **Broker Integration**: Real-time connectivity with Moomoo API and database persistence via Supabase.
* **Technical Screening**: Specialized filters for MA5, MA20, and the MA120 "Life Line" trend identification.

---

## 🇹🇼 Taiwan Stock Analysis (TWS) Pipeline

The `tws/` directory contains an automated daily workflow designed to find high-growth "Leading Tickers" while strictly adhering to investment discipline.

### 📂 Directory Structure
```text
tws/
├── data/
│   ├── tickers/          # Daily Top 20 high-volume lists
│   ├── ohlcv/            # Cleaned historical price data
│   └── company/          # Mapping of Names, Industries, and PE
├── master_run.py           # Central automation controller
├── get_company_info.py     # Updates company fundamentals (PE, Sector)
├── init_historical_data.py  # Syncs 250-day price history (Excludes ETFs)
├── current_trending.py     # Multi-MA trend screening engine
└── telegram_notifier.py    # Telegram reporting with real-time news
```


# Purpose

A collection of AI trading algorithms and tools for automated trading strategies. The project includes implementations for:
- Triple-barrier labeling for financial time series data
- Integration with Moomoo broker API for real-time trading
- Database connectivity with Supabase for data persistence

## Setup
This repository contains various trading algorithms and tools for both learning and development purposes. The codebase includes:
- Jupyter notebooks with examples and tutorials
- Production-ready broker integration code
- Data processing and labeling utilities

# Installation

The project has different dependencies based on your operating system:

For macOS with Apple Silicon (M1/M2):
- Install TensorFlow with Metal support following the [tensor-metal guide](https://developer.apple.com/metal/tensorflow-plugin/)
- Install dependencies with: