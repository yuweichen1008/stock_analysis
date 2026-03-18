import requests
import pandas as pd
from datetime import datetime, timedelta
import time

API_URL = "https://www.twse.com.tw/rwd/en/afterTrading/MI_INDEX20?date={date}"

START_DATE = datetime(2025, 12, 1)
TODAY = datetime.today()

OUTPUT_CSV = "top20_2026.csv"
HOLIDAY_CSV = "twse_holidays.csv"



# ==================== 工具函數 ====================
import requests
import pandas as pd
from datetime import datetime


def get_holidays_df(start_year: int) -> pd.DataFrame:
    # read from local CSV if exists
    try:
        holidays_df = pd.read_csv(HOLIDAY_CSV)
        # parse as datetime64 (keep time-like dtype so .dt accessor works)
        holidays_df["date"] = pd.to_datetime(holidays_df["date"], format="%Y-%m-%d")
        # only return starting from start_year
        holidays_df = holidays_df[holidays_df["date"].dt.year >= start_year].reset_index(drop=True)
        return holidays_df
    except FileNotFoundError:
        # If a local holiday CSV doesn't exist, return an empty DataFrame with the expected columns
        print(f"Warning: {HOLIDAY_CSV} not found — continuing without holiday exclusions.")
        return pd.DataFrame(columns=["date", "description"]) 

# -------- 產生交易日清單（平日扣掉休市日） --------
def get_trading_dates(start_date, end_date):
    """
    生成指定範圍內的所有日期（暫時全部，稍後 API 會自動跳過假日）
    """
    dates = []
    current = start_date
    holidays_df = get_holidays_df(start_date.year)
    # 確保是 datetime
    if not holidays_df.empty:
        holidays_df["date"] = pd.to_datetime(holidays_df["date"])
        holiday_set = set(holidays_df["date"].dt.date)
    else:
        holiday_set = set()

    while current <= TODAY:
        # 0=Monday ... 4=Friday
        if current.weekday() < 5 and current.date() not in holiday_set:
            dates.append(current.strftime("%Y%m%d"))
        current += timedelta(days=1)

    print(f"爬蟲範圍：{start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')} 總共 {len(dates)} 個交易日")
    return dates

def fetch_top20_by_date(date_str):
    """
    根據日期抓該日的前 20 名成交量股票資料
    date_str: 格式為 'YYYYMMDD'
    回傳: dict (JSON) 或 None (若該日無資料或網路錯誤)
    """
    url = API_URL.format(date=date_str)
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        # 檢查是否有有效資料
        if "data" in data and len(data["data"]) > 0:
            return data
        else:
            return None
    except requests.exceptions.RequestException as e:
        print(f"  ⚠ {date_str} 取得失敗: {e}")
        return None

def parse_api_response(api_response, date_str):
    """
    解析 API JSON 回應，提取前 20 名的 OHLCV 資訊
    回傳: list of dict，每一筆包含 date, symbol, name, open, high, low, close, volume
    """
    rows = []
    
    if not api_response or "data" not in api_response:
        return rows
    
    for record in api_response["data"]:
        # 根據實際 JSON 結構調整欄位名稱
        # 典型結構可能是: [rank, symbol, name, volume, trades, open, high, low, close, change, ...]
        try:
            row_dict = {
                "date": date_str,
                "symbol": record[1],      # 證券代號
                "volume": int(record[2].replace(",", "")),       # 成交股數（去逗號）
                "transaction": int(record[3].replace(",", "")),  # 成交次數（去逗號）
                "open": float(record[4].replace(",", "")) ,     # 開盤價
                "high": float(record[5].replace(",", "")) ,      # 最高價
                "low": float(record[6].replace(",", "")) ,      # 最低價
                "close": float(record[7].replace(",", ""))      # 收盤價
            }
            rows.append(row_dict)
        except (IndexError, ValueError) as e:
            print(f"    解析記錄失敗 {date_str}: {e}, record: {record}")
            continue
    
    return rows

def main():

    # 1. 產生日期列表
    dates = get_trading_dates(START_DATE, TODAY)
    print(f"共需檢查 {len(dates)} 個日期\n")
    
    # 2. 逐日抓資料
    all_records = []
    success_count = 0
    fail_count = 0
    
    for idx, date_str in enumerate(dates, 1):
        # 進度顯示
        if idx % 10 == 0:
            print(f"進度: {idx}/{len(dates)} ({100*idx//len(dates)}%)")
        
        # 抓 API
        api_data = fetch_top20_by_date(date_str)
        
        if api_data:
            records = parse_api_response(api_data, date_str)
            if records:
                all_records.extend(records)
                success_count += 1
        else:
            fail_count += 1
        
        # 避免 rate limit，每次請求間隔 0.1 秒
        time.sleep(0.1)
    
    print(f"\n爬蟲完成！成功日期: {success_count}, 失敗/無資料日期: {fail_count}")
    print(f"共取得 {len(all_records)} 筆記錄\n")
    
    # 3. 轉換成 DataFrame
    if all_records:
        df = pd.DataFrame(all_records)
        
        # 日期轉成標準格式（YYYY-MM-DD）
        df["date"] = pd.to_datetime(df["date"], format="%Y%m%d").dt.strftime("%Y-%m-%d")
        
        # 按日期和成交量排序（同一天的資料按成交量由高到低）
        df = df.sort_values(["date", "volume"], ascending=[True, False]).reset_index(drop=True)
        
        # 4. 存成 CSV
        df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
        print(f"✓ 已存成 CSV: {OUTPUT_CSV}")
        
        
        print(f"\n資料統計：")
        print(f"  日期範圍: {df['date'].min()} 至 {df['date'].max()}")
        print(f"  不同股票數: {df['symbol'].nunique()}")
        print(f"  總記錄數: {len(df)}")
    else:
        print("❌ 未取得任何資料，請檢查 API 或網路連線")

if __name__ == "__main__":
    main()
