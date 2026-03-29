import os
import pandas as pd
import numpy as np
import glob
from datetime import datetime

# Assuming the filter logic is generic enough to be reused.
# We might need to adjust the parameters for the US market.
from tws.taiwan_trending import apply_filters

def get_valid_tickers(ohlcv_dir):
    """
    Get a list of tickers from the downloaded OHLCV files.
    """
    files = glob.glob(os.path.join(ohlcv_dir, "*.csv"))
    tickers = [os.path.basename(f).split('_')[0] for f in files]
    return tickers

def run_us_trending(base_dir):
    """
    Runs the trending analysis for US stocks.
    """
    us_data_dir = os.path.join(base_dir, "data_us")
    ohlcv_dir = os.path.join(us_data_dir, "ohlcv")
    output_file = os.path.join(us_data_dir, "current_trending.csv")

    valid_tickers = get_valid_tickers(ohlcv_dir)
    results = []
    stats = {"Total": 0, "Signal": 0}

    print(f"--- Running US stock analysis: {datetime.now().date()} ---")

    for ticker in valid_tickers:
        pattern = os.path.join(ohlcv_dir, f"{ticker}_*.csv")
        existing_files = glob.glob(pattern)
        
        if not existing_files:
            continue
            
        f = existing_files[0]
        try:
            df = pd.read_csv(f, index_col=0)
            print(f"--- content of {f} ---")
            print(df.head())
            df.index = pd.to_datetime(df.index)
            
            cols_to_fix = ['Open', 'High', 'Low', 'Close', 'Volume']
            for col in cols_to_fix:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df = df.dropna(subset=cols_to_fix)
            
            if len(df) < 120:
                continue

            stats["Total"] += 1
            is_signal, reasons, metrics = apply_filters(df.copy())

            if is_signal:
                stats["Signal"] += 1
                results.append({
                    'ticker': ticker,
                    'price': metrics.get('price'),
                    'MA120': round(metrics.get('MA120', 0), 2),
                    'MA20': round(metrics.get('MA20', 0), 2),
                    'RSI': round(metrics.get('RSI', 0), 2),
                    'bias': metrics.get('bias'),
                    'score': metrics.get('score'),
                    'last_date': df.index[-1].strftime('%Y-%m-%d')
                })
                
        except Exception as e:
            print(f"   ! Error processing {ticker}: {e}")

    print(f"   Scanned: {stats['Total']} | Signals: {stats['Signal']}")
    
    if results:
        pd.DataFrame(results).to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"[OK] US trending stocks list saved to {output_file}")
    else:
        if os.path.exists(output_file):
            os.remove(output_file)
        print("[!] No US stocks matching the signal today.")

if __name__ == "__main__":
    # To run this standalone for testing
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    run_us_trending(BASE_DIR)