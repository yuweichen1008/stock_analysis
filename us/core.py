import glob
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from io import StringIO

import pandas as pd
import requests
import yfinance as yf


def get_us_universe() -> list:
    """~4500 common US stocks from NASDAQ Trader FTP. Falls back to S&P 500."""
    tickers: set = set()
    files = [
        "ftp://ftp.nasdaqtrader.com/SymbolDirectory/nasdaqlisted.txt",
        "ftp://ftp.nasdaqtrader.com/SymbolDirectory/otherlisted.txt",
    ]
    try:
        for url in files:
            with urllib.request.urlopen(url, timeout=30) as f:
                text = f.read().decode("latin-1")
            for line in text.splitlines()[1:]:
                parts = line.split("|")
                if len(parts) < 7:
                    continue
                sym  = parts[0].strip()
                etf  = parts[-3].strip()
                test = parts[-2].strip()
                if etf == "Y" or test == "Y":
                    continue
                if not sym or not sym.isalpha():
                    continue
                tickers.add(sym)
        return sorted(tickers)
    except Exception:
        engine = USStockEngine(base_dir=".")
        return engine.get_sp500_tickers()


def compute_weekly_returns(tickers: list, batch_size: int = 100) -> list:
    """
    Returns list of dicts with ticker, week_ending (YYYY-MM-DD), return_pct,
    last_price for the most recently completed trading week.
    """
    results = []
    batches = [tickers[i:i + batch_size] for i in range(0, len(tickers), batch_size)]
    for batch in batches:
        try:
            raw = yf.download(
                " ".join(batch),
                period="14d",
                interval="1d",
                auto_adjust=True,
                threads=True,
                progress=False,
            )
            if raw.empty:
                continue
            if len(batch) == 1:
                closes = raw[["Close"]].rename(columns={"Close": batch[0]})
            else:
                closes = raw["Close"]
            weekly = closes.resample("W-FRI").last()
            if len(weekly) < 2:
                continue
            prev_week  = weekly.iloc[-2]
            this_week  = weekly.iloc[-1]
            week_label = str(this_week.name.date())
            for ticker in batch:
                if ticker not in closes.columns:
                    continue
                p = prev_week.get(ticker)
                c = this_week.get(ticker)
                if p and c and float(p) > 0:
                    ret = round((float(c) - float(p)) / float(p), 4)
                    results.append({
                        "ticker":      ticker,
                        "week_ending": week_label,
                        "return_pct":  ret,
                        "last_price":  round(float(c), 4),
                    })
        except Exception:
            continue
        time.sleep(0.5)
    return results


class USStockEngine:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.us_data_dir = os.path.join(self.base_dir, "data_us")
        self.ohlcv_dir = os.path.join(self.us_data_dir, "ohlcv")
        os.makedirs(self.ohlcv_dir, exist_ok=True)

    def get_sp500_tickers(self):
        """
        Fetches the list of S&P 500 tickers from Wikipedia.
        """
        try:
            url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
            headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36'}
            response = requests.get(url, headers=headers)
            tables = pd.read_html(StringIO(response.text))
            sp500_table = tables[0]
            # Replace dots with dashes in ticker symbols (e.g., BRK.B -> BRK-B)
            tickers = sp500_table['Symbol'].apply(lambda s: s.replace('.', '-')).tolist()
            return tickers
        except Exception as e:
            print(f"Error fetching S&P 500 tickers: {e}")
            return []

    def sync_daily_data(self):
        """
        Downloads historical data for S&P 500 tickers.
        """
        tickers = self.get_sp500_tickers()
        if not tickers:
            print("No tickers to sync.")
            return

        print(f"Syncing data for {len(tickers)} S&P 500 tickers...")
        with ThreadPoolExecutor(max_workers=10) as executor:
            executor.map(self._download_ohlcv, tickers)

    def _download_ohlcv(self, ticker):
        """Downloads 250 days of OHLCV data for a given ticker.

        Uses yf.Ticker().history() with a small sleep to avoid the yfinance
        thread-safety issue where concurrent yf.download() calls return the
        same cached DataFrame for different tickers (mirrors tws/core.py).
        """
        try:
            time.sleep(0.3)
            df = yf.Ticker(ticker).history(period="250d", auto_adjust=True)
            if df.empty:
                return
            df.index = df.index.tz_localize(None)
            start = df.index[0].strftime("%Y%m%d")
            end   = df.index[-1].strftime("%Y%m%d")
            for old_f in glob.glob(os.path.join(self.ohlcv_dir, f"{ticker}_*.csv")):
                os.remove(old_f)
            df[["Open", "High", "Low", "Close", "Volume"]].to_csv(
                os.path.join(self.ohlcv_dir, f"{ticker}_{start}_{end}.csv")
            )
        except Exception as e:
            print(f"Error downloading {ticker}: {e}")

if __name__ == '__main__':
    engine = USStockEngine(base_dir='.')
    engine.sync_daily_data()