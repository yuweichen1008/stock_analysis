import warnings
from urllib3.exceptions import NotOpenSSLWarning
from pathlib import Path

# suppress noisy urllib3 warning about LibreSSL when using requests
warnings.filterwarnings("ignore", category=NotOpenSSLWarning)

import pandas as pd
import requests
from datetime import datetime

# write the output next to this script (avoid duplicating a `data/data` path)
HOLIDAY_OUTPUT_CSV = Path(__file__).parent / "twse_holidays.csv"

def get_holidays_df(start_year: int) -> pd.DataFrame:
    """
    呼叫 TWSE holidaySchedule API，回傳該年度的 holidays_df。
    欄位：date (datetime.date), description (str)。
    """
    # API 規則：date 帶當年 1 月 1 日即可，例如 20210101、20240101
    # date_param = f"{year}0101"
    # url = f"https://www.twse.com.tw/rwd/en/holidaySchedule/holidaySchedule?date={date_param}"
    current_year = datetime.today().year
    dfs = []

    for year in range(start_year, current_year + 1):
        date_param = f"{year}0101"
        url = f"https://www.twse.com.tw/rwd/en/holidaySchedule/holidaySchedule?date={date_param}"
        
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        if data.get("stat") != "ok":
            raise RuntimeError(f"API return stat={data.get('stat')} for year {year}")
        
        # fields: ["Date","Description"]
        # data: [[ "2021-01-01","New Year" ], ...]
        rows = data.get("data", [])
        
        # 轉成 DataFrame
        df = pd.DataFrame(rows, columns=data["fields"])
        # 轉成標準欄位名稱
        df = df.rename(columns={"Date": "date", "Description": "description"})
        
        # 字串日期轉 datetime.date
        df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d").dt.date
        
        dfs.append(df)

    return pd.concat(dfs, ignore_index=True)


if __name__ == "__main__":
    holidays_df = get_holidays_df(start_year=2021)
    # ensure parent directory exists
    out_path = Path(HOLIDAY_OUTPUT_CSV)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    holidays_df.to_csv(out_path, index=False)
    print(f"已儲存 TWSE 休市日至 {out_path}")