import os
import requests
import pandas as pd
import io

# ==================== 配置 ====================
COMPANY_DIR = "data/company"
MAPPING_FILE = os.path.join(COMPANY_DIR, "company_mapping.csv")
os.makedirs(COMPANY_DIR, exist_ok=True)

def fetch_clean_company_info():
    """修正產業代碼與 PE 顯示問題"""
    # 1. 抓取上市公司基本資料 (保證產業別為中文)
    basic_url = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
    print("[*] 正在抓取 TWSE 官方產業對照表...")
    
    try:
        res = requests.get(basic_url, timeout=15)
        # 直接抓取：公司代號, 公司名稱, 產業別
        df_basic = pd.DataFrame(res.json())[['公司代號', '公司名稱', '產業別']]
        df_basic.columns = ['ticker', 'name', 'industry']
        df_basic['ticker'] = df_basic['ticker'].str.strip().str.zfill(4)
    except Exception as e:
        print(f"基本資料抓取失敗: {e}")
        return

    # 2. 抓取本益比資料 (處理 nan)
    val_url = "https://www.twse.com.tw/exchangeReport/BWIBHTU_d?response=csv"
    try:
        v_res = requests.get(val_url, timeout=15)
        # 跳過前兩行標題，讀取數據
        df_val = pd.read_csv(io.StringIO(v_res.text), skiprows=1).iloc[:, [0, 2]]
        df_val.columns = ['ticker', 'pe_ratio']
        df_val['ticker'] = df_val['ticker'].astype(str).str.strip('"').str.zfill(4)
        df_val['pe_ratio'] = pd.to_numeric(df_val['pe_ratio'], errors='coerce').fillna('N/A')
    except:
        df_val = pd.DataFrame(columns=['ticker', 'pe_ratio'])

    # 合併並存檔
    df_final = pd.merge(df_basic, df_val, on='ticker', how='left').fillna('N/A')
    df_final.to_csv(MAPPING_FILE, index=False, encoding='utf-8-sig')
    print(f"[✓] 已更新對照表。範例：2801 -> {df_final[df_final['ticker']=='2801']['industry'].values}")

if __name__ == "__main__":
    fetch_clean_company_info()