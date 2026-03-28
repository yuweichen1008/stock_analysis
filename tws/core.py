import os
import requests
import pandas as pd
import yfinance as yf
import glob
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

def _last_trading_date(ref: datetime = None) -> datetime:
    """Most recent Mon–Fri date (no TW holiday calendar)."""
    d = (ref or datetime.now()).date()
    if d.weekday() == 5:
        d -= timedelta(days=1)
    elif d.weekday() == 6:
        d -= timedelta(days=2)
    return datetime.combine(d, datetime.min.time())

class TaiwanStockEngine:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.tickers_dir = os.path.join(base_dir, "data", "tickers")
        self.ohlcv_dir = os.path.join(base_dir, "data", "ohlcv")
        self.mapping_file = os.path.join(base_dir, "data", "company", "company_mapping.csv")
        self.history_file = os.path.join(base_dir, "data", "company", "company_history.csv")
        self.trending_file = os.path.join(base_dir, "current_trending.csv")
        
        # 完整的產業代碼映射表 (解決數字代號問題)
        self.INDUSTRY_MAP = {
            '01': '水泥工業', '02': '食品工業', '03': '塑膠工業', '04': '紡織纖維',
            '05': '電機機械', '06': '電器電纜', '07': '化學工業', '08': '玻璃陶瓷',
            '09': '造紙工業', '10': '鋼鐵工業', '11': '橡膠工業', '12': '汽車工業',
            '14': '建材營造業', '15': '航運業', '16': '觀光事業', '17': '金融保險業',
            '18': '貿易百貨業', '19': '綜合', '20': '其他', '21': '化學生技',
            '22': '生技醫療業', '23': '油電燃氣業', '24': '半導體業', '25': '電腦週邊業',
            '26': '光電業', '27': '通信網路業', '28': '電子零組件業', '29': '電子通路業',
            '30': '資訊服務業', '31': '其他電子業', '32': '文化創意業', '33': '農業科技',
            '34': '電子商務', '35': '綠能環保', '36': '數位雲端', '37': '運動休閒', '38': '居家生活'
        }

        self.MAJOR_TICKERS = ["2330", "2317", "2454", "2308", "2382", "2357", "2881", "2603", "2618", "2615", "1215"]

        for d in [self.tickers_dir, self.ohlcv_dir, os.path.dirname(self.mapping_file)]:
            os.makedirs(d, exist_ok=True)

    def sync_daily_data(self):
        """同步數據並確保產生清單檔案，解決 Scanned: 0 問題"""
        now = datetime.now()
        trading_dt = _last_trading_date(now)
        today_str  = trading_dt.strftime("%Y%m%d")

        if now.date().weekday() >= 5:
            lag = (now.date() - trading_dt.date()).days
            print(f"[!] 今日非交易日 ({now.strftime('%A')})，使用最近交易日 {trading_dt.strftime('%Y-%m-%d')} (前 {lag} 天)")

        ticker_file = os.path.join(self.tickers_dir, f"top20_{today_str}.csv")
        tickers = []

        print(f"[*] 正在獲取交易清單 ({today_str})...")
        try:
            url = f"https://www.twse.com.tw/exchangeReport/MI_INDEX20?response=json&date={today_str}"
            res = requests.get(url, timeout=10)
            data = res.json()
            raw_data = data.get('data8') or data.get('data7')
            if data.get('stat') == 'OK' and raw_data:
                tickers = [row[1] for row in raw_data if row[1].isdigit() and not row[1].startswith('00')]
        except: pass

        if not tickers:
            recent_files = sorted(glob.glob(os.path.join(self.tickers_dir, "top20_*.csv")), reverse=True)
            if recent_files:
                print(f"[!] 使用歷史清單: {os.path.basename(recent_files[0])}")
                tickers = pd.read_csv(recent_files[0], dtype=str).iloc[:, 0].tolist()
            else:
                print("[!] 冷啟動：使用保底權值股並建立清單檔案。")
                tickers = self.MAJOR_TICKERS
        
        pd.DataFrame({'ticker': tickers}).to_csv(ticker_file, index=False)

        print(f"[*] 正在同步 {len(tickers)} 檔 K 線數據...")
        with ThreadPoolExecutor(max_workers=5) as executor:
            executor.map(self._download_ohlcv, tickers)
        return tickers

    def _download_ohlcv(self, ticker):
        """下載 250 日數據並存儲 CSV"""
        try:
            # Small sleep avoids yfinance thread-safety issues where concurrent
            # requests can return the same cached DataFrame for different tickers.
            time.sleep(0.3)
            tick = yf.Ticker(f"{ticker}.TW")
            df = tick.history(period="250d", auto_adjust=True)
            if df.empty:
                return
            # yfinance Ticker.history() returns a plain (non-MultiIndex) DataFrame
            # with columns Open/High/Low/Close/Volume — safe for concurrent use.
            df.index = df.index.tz_localize(None)
            start = df.index[0].strftime("%Y%m%d")
            end   = df.index[-1].strftime("%Y%m%d")
            for old_f in glob.glob(os.path.join(self.ohlcv_dir, f"{ticker}_*.csv")):
                os.remove(old_f)
            df[['Open', 'High', 'Low', 'Close', 'Volume']].to_csv(
                os.path.join(self.ohlcv_dir, f"{ticker}_{start}_{end}.csv")
            )
        except Exception:
            pass

    def fetch_stock_info(self, ticker):
        """強化抓取邏輯：解決 ROE/PE N/A 問題"""
        try:
            yt = yf.Ticker(f"{ticker}.TW")
            info = yt.info
            pe = info.get('trailingPE') or info.get('forwardPE')
            if pe is None:
                price = info.get('currentPrice') or info.get('regularMarketPrice', 0)
                eps = info.get('trailingEps', 0)
                pe = price / eps if eps != 0 else "N/A"

            roe = info.get('returnOnEquity') or info.get('returnOnAssets', "N/A")
            div = info.get('dividendYield') or info.get('trailingAnnualDividendYield', "N/A")

            return {
                'ticker': str(ticker),
                'last_update_date': datetime.now().strftime('%Y-%m-%d'),
                'pe_ratio': pe,
                'roe': roe,
                'debt_to_equity': info.get('debtToEquity', "N/A"),
                'target_price': info.get('targetMeanPrice', "N/A"),
                'recommendation': info.get('recommendationKey', "N/A"),
                'dividend_yield': div
            }
        except:
            return {'ticker': str(ticker), 'last_update_date': datetime.now().strftime('%Y-%m-%d'), 'pe_ratio': "N/A"}

    def update_mapping_with_trending(self):
        """核心修正：解決 KeyError: 'ticker' 與 產業別代碼問題"""
        # 1. 抓取官方清單
        res = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", timeout=10)
        df_basic = pd.DataFrame(res.json())[['公司代號', '公司名稱', '產業別']]
        df_basic.columns = ['ticker', 'name', 'ind_raw']
        df_basic['ticker'] = df_basic['ticker'].astype(str).str.strip().str.zfill(4)
        
        # 轉換產業中文
        df_basic['industry'] = df_basic['ind_raw'].apply(lambda x: self.INDUSTRY_MAP.get(str(x).strip(), str(x)))
        df_basic = df_basic.drop(columns=['ind_raw'])

        # 2. 讀取現有數據，防禦性處理空 DataFrame
        if os.path.exists(self.mapping_file):
            mapping_df = pd.read_csv(self.mapping_file, dtype={'ticker': str})
        else:
            # 初始化具備欄位的空 DataFrame
            mapping_df = pd.DataFrame(columns=['ticker', 'roe', 'pe_ratio', 'last_update_date'])

        # 3. 確定更新範圍
        target_tickers = []
        if os.path.exists(self.trending_file):
            target_tickers = pd.read_csv(self.trending_file, dtype={'ticker': str})['ticker'].tolist()
        
        # 4. 判斷誰需要補全
        to_update = []
        for t in target_tickers:
            # 🛡️ 核心修正：安全檢查 ticker 是否存在於 mapping 中
            row = mapping_df[mapping_df['ticker'] == t] if 'ticker' in mapping_df.columns else pd.DataFrame()
            if row.empty or str(row.iloc[0].get('roe')) in ['nan', 'N/A']:
                to_update.append(t)

        # 5. 執行數據抓取
        if to_update:
            print(f"[*] 補全 {len(to_update)} 檔數據並寫入歷史紀錄...")
            with ThreadPoolExecutor(max_workers=10) as executor:
                new_data = list(executor.map(self.fetch_stock_info, to_update))
            
            self._save_to_history(new_data)
            
            df_new = pd.DataFrame(new_data)
            
            # 🛡️ 核心修正：合併邏輯，確保不會因空欄位崩潰
            if not mapping_df.empty and 'ticker' in mapping_df.columns:
                mapping_df = mapping_df[~mapping_df['ticker'].isin(to_update)]
                mapping_df = pd.concat([mapping_df, df_new], ignore_index=True)
            else:
                mapping_df = df_new

        # 6. 最終對齊：拋棄 Yahoo 雜亂欄位，強制使用官方中文名稱
        cols_to_keep = ['ticker', 'pe_ratio', 'roe', 'debt_to_equity', 'target_price', 'recommendation', 'dividend_yield', 'last_update_date']
        mapping_clean = mapping_df[[c for c in cols_to_keep if c in mapping_df.columns]]
        
        df_output = pd.merge(df_basic, mapping_clean, on='ticker', how='left').fillna("N/A")
        df_output.to_csv(self.mapping_file, index=False, encoding='utf-8-sig')
        print("[✓] 數據補全與產業別校正完成。")
        return True

    def _save_to_history(self, new_data_list):
        """增量存儲歷史資料 (回測核心)"""
        df_new = pd.DataFrame(new_data_list)
        if not os.path.exists(self.history_file):
            df_new.to_csv(self.history_file, index=False, encoding='utf-8-sig')
        else:
            df_old = pd.read_csv(self.history_file, dtype={'ticker': str})
            df_combined = pd.concat([df_old, df_new], ignore_index=True)
            # 數值沒變則不重複紀錄
            df_combined = df_combined.drop_duplicates(subset=['ticker', 'pe_ratio', 'roe'], keep='first')
            df_combined.to_csv(self.history_file, index=False, encoding='utf-8-sig')