import os
import time
import random
import requests
import pandas as pd
import yfinance as yf
import glob
import re
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 使用絕對路徑定義資料夾
TICKERS_DIR = os.path.join(BASE_DIR, "data", "tickers")
OHLCV_DIR = os.path.join(BASE_DIR, "data", "ohlcv")

# 確保自動創建目錄
os.makedirs(TICKERS_DIR, exist_ok=True)
os.makedirs(OHLCV_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def fetch_tickers_daily(date_str):
    """Fetches up to 20 numeric tickers, pads zeros, and filters out ETFs."""
    file_path = os.path.join(TICKERS_DIR, f"top20_{date_str}.csv")
    
    if os.path.exists(file_path):
        df_existing = pd.read_csv(file_path, dtype={'ticker': str})
        return set(df_existing['ticker'].tolist())

    url = f"https://www.twse.com.tw/exchangeReport/MI_INDEX20?response=json&date={date_str}"
    try:
        time.sleep(random.uniform(1.5, 3))
        response = requests.get(url, headers=HEADERS, timeout=15)
        data = response.json()
        
        if data.get('stat') == 'OK' and 'data' in data:
            raw_rows = data['data']
            ticker_list = []
            
            for row in raw_rows:
                val = str(row[1]).strip()
                
                # Check for pure numeric ticker
                if re.fullmatch(r'\d+', val):
                    # Pad leading zeros (e.g., '50' -> '0050')
                    formatted_ticker = val.zfill(4)
                    
                    # Filter out ETFs (starting with '00')
                    if formatted_ticker.startswith('00'):
                        continue
                        
                    ticker_list.append(formatted_ticker)
                
                if len(ticker_list) == 20: 
                    break
            
            # Save with 'ticker' as the only header
            pd.DataFrame(ticker_list, columns=['ticker']).to_csv(file_path, index=False)
            print(f"[+] Top 20 Saved: {date_str} (Count: {len(ticker_list)})")
            return set(ticker_list)
    except Exception as e:
        print(f"[!] TWSE Error {date_str}: {e}")
    return set()

def sync_ohlcv_task(ticker):
    """Incremental sync with 250-day target and explicit date parsing."""
    pattern = os.path.join(OHLCV_DIR, f"{ticker}_*.csv")
    existing_files = glob.glob(pattern)
    existing_file = existing_files[0] if existing_files else None
    
    # Try both suffixes for Taiwan markets
    for suffix in [".TW", ".TWO"]:
        yf_ticker = f"{ticker}{suffix}"
        try:
            if existing_file:
                # Fix UserWarning by specifying format
                df = pd.read_csv(existing_file, index_col=0)
                df.index = pd.to_datetime(df.index, format='ISO8601', errors='coerce')
                df = df.dropna()
                
                last_date = df.index[-1]
                yesterday = datetime.now() - timedelta(days=1)
                
                if last_date.date() >= yesterday.date():
                    return 

                # Fetch missing data
                new_data = yf.download(yf_ticker, start=last_date + timedelta(days=1), progress=False)
                
                if not new_data.empty:
                    df = pd.concat([df, new_data])
                    df = df[~df.index.duplicated(keep='last')]
                    os.remove(existing_file)
                else:
                    if suffix == ".TW": continue
                    return 
            else:
                # Initial 250-day fetch
                df = yf.download(yf_ticker, period="250d", progress=False)

            if df is None or df.empty: 
                continue 

            begin_date = df.index[0].strftime("%Y%m%d")
            end_date = df.index[-1].strftime("%Y%m%d")
            new_name = f"{ticker}_{begin_date}_{end_date}.csv"
            df.to_csv(os.path.join(OHLCV_DIR, new_name))
            print(f"[✓] OHLCV Updated: {new_name} ({len(df)} rows)")
            return
        except Exception:
            continue

def run_init():
    # Setup 90 trading days
    days = []
    curr = datetime.now() - timedelta(days=1)
    while len(days) < 90:
        if curr.weekday() < 5: days.append(curr.strftime("%Y%m%d"))
        curr -= timedelta(days=1)
        
    all_tickers = set()
    print("--- Phase 1: Ticker Fetching (Ignoring ETFs) ---")
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(fetch_tickers_daily, d) for d in days]
        for f in as_completed(futures):
            all_tickers.update(f.result())

    print(f"\n--- Phase 2: OHLCV Syncing ({len(all_tickers)} Tickers) ---")
    with ThreadPoolExecutor(max_workers=3) as executor:
        executor.map(sync_ohlcv_task, all_tickers)

if __name__ == "__main__":
    run_init()