import os
import pandas as pd
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

def apply_filters(df):
    """
    趨勢過濾邏輯：MA5, MA20, MA120
    """
    if len(df) < 120:
        return False, "Insufficient Data"
    
    # 計算移動平均線
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA120'] = df['Close'].rolling(window=120).mean()
    
    last = df.iloc[-1]
    price = last['Close']
    ma5, ma20, ma120 = last['MA5'], last['MA20'], last['MA120']
    
    # 死亡區間邏輯：(價格低於 MA5 或 MA20) 且低於生命線 MA120
    if (price < ma5 or price < ma20) and (price < ma120):
        return False, "Death Zone"
    
    # 生命線律令：低於 MA120 一律排除
    if price < ma120:
        return False, "Below MA120"
        
    return True, "Trending"

def run_taiwan_trending(base_dir):
    """
    主執行函式：由根目錄的 master_run.py 呼叫並傳入根目錄路徑
    """
    # 統一路徑設定 (往上一層到根目錄再進入 data)
    tickers_dir = os.path.join(base_dir, "data", "tickers")
    ohlcv_dir = os.path.join(base_dir, "data", "ohlcv")
    output_file = os.path.join(base_dir, "current_trending.csv")

    valid_tickers = get_valid_tickers(tickers_dir)
    results = []
    stats = {"Total": 0, "Dead Zone": 0, "Trending": 0}

    print(f"--- 執行台股趨勢分析: {datetime.now().date()} ---")

    for ticker in valid_tickers:
        pattern = os.path.join(ohlcv_dir, f"{ticker}_*.csv")
        existing_files = glob.glob(pattern)
        
        if not existing_files:
            continue
            
        f = existing_files[0]
        try:
            # 讀取數據並修正日期格式
            df = pd.read_csv(f, index_col=0)
            df.index = pd.to_datetime(df.index, format='mixed',errors='coerce')
            
            # 數值化轉換與資料清理
            cols_to_fix = ['Open', 'High', 'Low', 'Close', 'Volume']
            for col in cols_to_fix:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df = df.dropna()
            
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
            elif status in ["Below MA120", "Death Zone"]:
                stats["Dead Zone"] += 1
                
        except Exception as e:
            print(f"   ! 處理 {ticker} 時出錯: {e}")

    # 日誌摘要
    print(f"   掃描: {stats['Total']} | 💀 死亡區: {stats['Dead Zone']} | 🚀 趨勢中: {stats['Trending']}")
    
    if results:
        pd.DataFrame(results).to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"[OK] 強勢股名單已存至 {output_file}")
    else:
        # 確保如果沒有結果，也刪除舊的 csv 以免誤用
        if os.path.exists(output_file):
            os.remove(output_file)
        print("[!] 今日無符合上漲趨勢之個股。")

if __name__ == "__main__":
    # 支援獨立執行測試
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    run_taiwan_trending(ROOT)