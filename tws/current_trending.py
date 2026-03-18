import os
import pandas as pd
import glob
import re
from datetime import datetime

# ==================== Configuration ====================
TICKERS_DIR = "data/tickers"
OHLCV_DIR = "data/ohlcv"
OUTPUT_FILE = "current_trending.csv"

def get_valid_tickers():
    """Requirement 1: Load numeric tickers from CSV, ignore ETFs ('00') and headers."""
    files = glob.glob(os.path.join(TICKERS_DIR, "top20_*.csv"))
    valid_tickers = set()
    
    for f in files:
        # Read file; skip the header if it exists and treat all as strings
        try:
            df = pd.read_csv(f, header=None, dtype=str)
            for val in df[0].tolist():
                val = val.strip()
                # Ensure it's numerical and NOT an ETF (does not start with '00')
                if re.fullmatch(r'\d+', val) and not val.startswith('00'):
                    valid_tickers.add(val)
        except Exception:
            continue
            
    print(f"Loaded {len(valid_tickers)} unique high-growth candidates (ETFs excluded).")
    return valid_tickers

def apply_filters(df):
    """Requirement 3: Apply Trend Filters (MA5, MA20, MA120)."""
    if len(df) < 120:
        return False, "Insufficient Data"
    
    # Calculate Moving Averages
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA120'] = df['Close'].rolling(window=120).mean()
    
    last = df.iloc[-1]
    price = last['Close']
    ma5, ma20, ma120 = last['MA5'], last['MA20'], last['MA120']
    
    # Logic: (price < MA5 || price < MA20) && price < MA120 -> IGNORE
    if (price < ma5 or price < ma20) and (price < ma120):
        return False, "Death Zone"
    
    # Life-line Discipline: Below MA120 is an automatic ignore
    if price < ma120:
        return False, "Below MA120"
        
    return True, "Trending"

def run_analysis():
    valid_tickers = get_valid_tickers()
    results = []
    stats = {"Total": 0, "Dead Zone": 0, "Trending": 0}

    print(f"--- Starting Local Trend Analysis: {datetime.now().date()} ---")

    for ticker in valid_tickers:
        pattern = os.path.join(OHLCV_DIR, f"{ticker}_*.csv")
        existing_files = glob.glob(pattern)
        
        if not existing_files:
            continue
            
        f = existing_files[0]
        try:
            # Fix Requirement 2: Explicit date format
            df = pd.read_csv(f, index_col=0)
            df.index = pd.to_datetime(df.index, format='ISO8601', errors='coerce')
            
            # FIX: Convert columns to numeric to prevent "No numeric types to aggregate"
            # errors='coerce' turns non-numeric junk into NaN, which dropna() then removes
            cols_to_fix = ['Open', 'High', 'Low', 'Close', 'Volume']
            for col in cols_to_fix:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df = df.dropna() # Remove any rows with missing/malformed numeric data
            
            if len(df) < 120:
                continue
                
            stats["Total"] += 1
            is_trending, status = apply_filters(df)
            
            if is_trending:
                stats["Trending"] += 1
                last = df.iloc[-1]
                results.append({
                    'ticker': ticker,
                    'price': round(float(last['Close']), 2),
                    'MA5': round(float(last['MA5']), 2),
                    'MA20': round(float(last['MA20']), 2),
                    'MA120': round(float(last['MA120']), 2),
                    'last_date': df.index[-1].strftime('%Y-%m-%d')
                })
            elif status == "Below MA120" or status == "Death Zone":
                stats["Dead Zone"] += 1
                
        except Exception as e:
            # This will now catch fewer "Aggregate" errors and more genuine file issues
            print(f"Error processing {ticker}: {e}")

    # Log Summary
    print(f"Scanned: {stats['Total']} | 💀 Dead Zone: {stats['Dead Zone']} | 🚀 Trending: {stats['Trending']}")
    
    if results:
        pd.DataFrame(results).to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig')
        print(f"[OK] Trending tickers saved to {OUTPUT_FILE}")
    else:
        print("[!] No tickers currently match the uptrend criteria.")

if __name__ == "__main__":
    run_analysis()