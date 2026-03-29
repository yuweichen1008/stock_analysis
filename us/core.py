import pandas as pd
import requests
import yfinance as yf
import os
import glob
from concurrent.futures import ThreadPoolExecutor
from io import StringIO

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
        """Downloads 250 days of OHLCV data for a given ticker."""
        try:
            # yfinance uses '-' for sub-classes, e.g. BRK-B, BF-B
            df = yf.download(ticker, period="250d", progress=False)
            if not df.empty:
                start, end = df.index[0].strftime("%Y%m%d"), df.index[-1].strftime("%Y%m%d")
                for old_f in glob.glob(os.path.join(self.ohlcv_dir, f"{ticker}_*.csv")):
                    os.remove(old_f)
                df.to_csv(os.path.join(self.ohlcv_dir, f"{ticker}_{start}_{end}.csv"))
        except Exception as e:
            print(f"Error downloading {ticker}: {e}")

if __name__ == '__main__':
    engine = USStockEngine(base_dir='.')
    engine.sync_daily_data()