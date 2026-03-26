import os
import pandas as pd
import numpy as np
import glob
import re
from datetime import datetime

def get_valid_tickers(tickers_dir):
    """
    載入高成長候選名單，排除 ETF (00開頭) 與標頭
    """
    files = glob.glob(os.path.join(tickers_dir, "top20_*.csv"))
    valid_tickers = set()
    
    for f in files:
        try:
            # 讀取檔案並確保格式為字串
            df = pd.read_csv(f, header=None, dtype=str)
            for val in df[0].tolist():
                val = val.strip()
                # 確保是數字代碼且非 ETF (排除 00 開頭)
                if re.fullmatch(r'\d+', val) and not val.startswith('00'):
                    valid_tickers.add(val)
        except Exception:
            continue
            
    print(f"   - 已載入 {len(valid_tickers)} 檔候選個股 (已排除 ETF)")
    return valid_tickers

def calculate_rsi(df, window=14):
    """
    計算相對強弱指數 (RSI)
    """
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def apply_filters(df):
    """
    短線交易策略：MA120 生命線 + MA20 短期動能 + RSI 超賣訊號
    Returns (is_signal: bool, reasons: list[str], metrics: dict)
    """
    reasons = []
    metrics = {}

    if len(df) < 120:
        return False, ["Insufficient Data"], metrics

    # 計算移動平均線
    df['MA120'] = df['Close'].rolling(window=120).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()

    # 計算 RSI
    df['RSI'] = calculate_rsi(df, window=14)

    last = df.iloc[-1]
    price = float(last['Close'])
    ma120 = float(last['MA120'])
    ma20 = float(last['MA20'])
    rsi = float(last['RSI'])

    metrics.update({'price': price, 'MA120': ma120, 'MA20': ma20, 'RSI': rsi})

    # 條件：長期趨勢健康 (price > MA120) 且 短期回調 (price < MA20) 且 RSI 超賣
    is_healthy = price > ma120
    is_short_pullback = price < ma20
    is_oversold = rsi < 35  # slightly looser for daytrading

    if not is_healthy:
        reasons.append('Below MA120')
    if is_short_pullback:
        reasons.append('Below MA20')
    if is_oversold:
        reasons.append('RSI Oversold')

    is_signal = is_healthy and is_short_pullback and is_oversold
    if is_signal:
        reasons.insert(0, 'Mean Reversion Signal')

    return is_signal, reasons, metrics

def run_taiwan_trending(base_dir):
    """
    主執行函式：由根目錄的 master_run.py 呼叫並傳入根目錄路徑
    """
    # 統一路徑設定
    tickers_dir = os.path.join(base_dir, "data", "tickers")
    ohlcv_dir = os.path.join(base_dir, "data", "ohlcv")
    output_file = os.path.join(base_dir, "current_trending.csv")

    valid_tickers = get_valid_tickers(tickers_dir)
    results = []
    stats = {"Total": 0, "Signal": 0, "Below MA120": 0, "Not Oversold": 0}

    print(f"--- 執行台股短線分析: {datetime.now().date()} ---")

    # fetch institutional data (外資) range and short interest
    from .utils import (
        fetch_twse_institutional,
        fetch_twse_institutional_range,
        fetch_twse_short_interest,
        fetch_google_news_many,
        get_sentiment_score,
        compute_foreign_metrics,
    )
    today_str = datetime.now().strftime('%Y%m%d')
    # fetch last 60 trading days map
    inst_range = fetch_twse_institutional_range(today_str, days=60)
    # latest day map
    inst_latest = {d['symbol']: d for d in fetch_twse_institutional(today_str)}
    short_map = fetch_twse_short_interest(today_str)

    for ticker in valid_tickers:
        pattern = os.path.join(ohlcv_dir, f"{ticker}_*.csv")
        existing_files = glob.glob(pattern)
        
        if not existing_files:
            continue
            
        f = existing_files[0]
        try:
            # 讀取數據
            df = pd.read_csv(f, index_col=0)
            df.index = pd.to_datetime(df.index, format='mixed', errors='coerce')
            
            # 數據清理
            cols_to_fix = ['Open', 'High', 'Low', 'Close', 'Volume']
            for col in cols_to_fix:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df = df.dropna(subset=cols_to_fix)
            
            if len(df) < 120:
                continue

            stats["Total"] += 1
            is_signal, reasons, metrics = apply_filters(df)

            # fetch external data: 外資 rolling metrics and news sentiment
            foreign_net = None
            f_metrics = {'f5': None, 'f20': None, 'f60': None, 'zscore': None}
            if ticker in inst_latest:
                foreign_net = inst_latest[ticker]['foreign_net']
            if ticker in inst_range:
                f_metrics = compute_foreign_metrics(inst_range[ticker])

            short_interest = short_map.get(ticker)

            headlines = fetch_google_news_many(ticker, "", days=7, max_items=5)
            sentiment = get_sentiment_score(headlines)

            if is_signal:
                stats["Signal"] += 1
                results.append({
                    'ticker': ticker,
                    'price': metrics.get('price'),
                    'MA120': round(metrics.get('MA120', 0), 2),
                    'MA20': round(metrics.get('MA20', 0), 2),
                    'RSI': round(metrics.get('RSI', 0), 2),
                    'foreign_net': foreign_net,
                    'f5': f_metrics.get('f5'),
                    'f20': f_metrics.get('f20'),
                    'f60': f_metrics.get('f60'),
                    'f_zscore': f_metrics.get('zscore'),
                    'short_interest': short_interest,
                    'news_sentiment': round(sentiment, 3),
                    'last_date': df.index[-1].strftime('%Y-%m-%d')
                })
            else:
                for r in reasons:
                    if r in stats:
                        stats[r] += 1
                
        except Exception as e:
            print(f"   ! 處理 {ticker} 時出錯: {e}")

    # 日誌摘要
    print(f"   掃描: {stats['Total']} | 🚀 訊號: {stats['Signal']} | 📉 生命線下: {stats['Below MA120']} | 📈 未超賣: {stats['Not Oversold']}")
    
    if results:
        pd.DataFrame(results).to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"[OK] 短線訊號股名單已存至 {output_file}")
    else:
        if os.path.exists(output_file):
            os.remove(output_file)
        print("[!] 今日無符合短線訊號之個股。")

if __name__ == "__main__":
    # 支援獨立執行測試
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    run_taiwan_trending(ROOT)