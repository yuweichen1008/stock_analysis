# -*- coding: utf-8 -*-
"""
Top 100 Taiwan Day-Trading Movers Screener (Skeleton)
資料來源（可依需求增減）:
- Goodinfo 現股當沖張數(當日) 排名  [需要你後續補上正確解析]
- Yahoo 台股漲幅排行
- TradingView Taiwan Top Gainers / Most Active
"""

import datetime as dt
import requests
import pandas as pd
from bs4 import BeautifulSoup
import time
import atexit
import functools
import random
from typing import Optional
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options

# =========================
# 基本設定
# =========================

TODAY = dt.date.today().strftime("%Y%m%d")
OUTPUT_FILE = f"tw_top100_daytrading_{TODAY}.xlsx"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# Global session and driver manager (reuse across fetches to avoid repeated driver installs)
SESSION = requests.Session()
SESSION.headers.update(HEADERS)


class DriverManager:
    """Lazy Selenium driver manager. Creates one ChromeDriver instance and reuses it.

    This avoids repeated downloads/installs of the chromedriver and reinitialization
    overhead when calling multiple fetch functions.
    """

    def __init__(self):
        self._driver: Optional[webdriver.Chrome] = None
        self._service: Optional[Service] = None

    def get_driver(self, headless: bool = True) -> webdriver.Chrome:
        if self._driver is not None:
            return self._driver

        chrome_options = Options()
        if headless:
            chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument(f'user-agent={HEADERS["User-Agent"]}')

        # Install driver once; webdriver-manager caches the binary so this is cheap on subsequent runs
        self._service = Service(ChromeDriverManager().install())
        self._driver = webdriver.Chrome(service=self._service, options=chrome_options)
        return self._driver

    def quit_driver(self) -> None:
        try:
            if self._driver:
                self._driver.quit()
        except Exception:
            pass
        finally:
            self._driver = None
            self._service = None


DRIVER_MANAGER = DriverManager()


# ensure the driver is quit on exit
atexit.register(lambda: DRIVER_MANAGER.quit_driver())

# configure module logger
logger = logging.getLogger(__name__)
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def retry(max_attempts: int = 3, backoff: float = 0.5):
    """Simple retry decorator with jittered exponential backoff for network calls."""

    def deco(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    attempt += 1
                    if attempt >= max_attempts:
                        raise
                    sleep_time = backoff * (2 ** (attempt - 1))
                    sleep_time = sleep_time * (0.8 + 0.4 * random.random())
                    time.sleep(sleep_time)

        return wrapper

    return deco

# =========================
# 資料來源 1: Yahoo 台股漲幅排行
# 網址: https://tw.stock.yahoo.com/rank/change-up
# =========================

def fetch_yahoo_top_gainers(max_rows: int = 200) -> pd.DataFrame:
    """
    抓 Yahoo 台股漲幅排行（當日），回傳欄位至少包含:
    ['symbol', 'name', 'change_pct']
    使用 Selenium 來處理 JavaScript 渲染的頁面。
    """
    url = "https://tw.stock.yahoo.com/rank/change-up"
    data = []

    driver = None
    try:
        driver = DRIVER_MANAGER.get_driver(headless=True)
        driver.get(url)

        # Wait for either a table or a list element to appear (slightly longer timeout)
        try:
            WebDriverWait(driver, 12).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table, [data-test-locator], .list, .rank-list"))
            )
        except Exception:
            # continue anyway, we'll try parsing page source
            pass

        # Prefer pandas.read_html when a proper table exists - it's faster and robust
        page = driver.page_source

        try:
            tables = pd.read_html(page)
            # pick the largest table by number of rows
            if tables:
                main = max(tables, key=lambda t: t.shape[0])
                # try to infer columns: symbol/name/change
                for _, row in main.head(max_rows).iterrows():
                    text = " ".join([str(x) for x in row.values if pd.notna(x)])
                    import re
                    symbol_match = re.search(r'\b(\d{4})\b', text)
                    change_match = re.search(r'([+-]?\d+\.?\d*)\s*%', text)
                    name_match = re.search(r'([\u4e00-\u9fff]+)', text)
                    if not symbol_match or not change_match:
                        continue
                    data.append({
                        "symbol": symbol_match.group(1),
                        "name": name_match.group(1) if name_match else "",
                        "yahoo_change_pct": float(change_match.group(1)),
                    })
                if data:
                    return pd.DataFrame(data)
        except Exception:
            # fallback to BeautifulSoup parsing below
            pass

        soup = BeautifulSoup(page, "lxml")
        rows = soup.select("table tbody tr")
        if not rows:
            rows = soup.select("tr[data-test-locator]")
        if not rows:
            rows = soup.select(".list-item, .rank-item, [class*='row']")

        import re
        for r in rows[:max_rows]:
            cells = r.find_all(["td", "div"])
            if len(cells) < 1:
                continue
            text_content = r.get_text(" ", strip=True)
            symbol_match = re.search(r'\b(\d{4})\b', text_content)
            if not symbol_match:
                continue
            change_match = re.search(r'([+-]?\d+\.?\d*)\s*%', text_content)
            if not change_match:
                continue
            name_match = re.search(r'([\u4e00-\u9fff]+)', text_content)
            try:
                change_pct = float(change_match.group(1))
            except Exception:
                continue
            data.append({
                "symbol": symbol_match.group(1),
                "name": name_match.group(1) if name_match else "",
                "yahoo_change_pct": change_pct,
            })

    except Exception as e:
        logger.exception("Error fetching Yahoo data: %s", e)
    return pd.DataFrame(data)


# =========================
# 資料來源 2: TradingView Taiwan Top Gainers
# 網址: https://www.tradingview.com/markets/stocks-taiwan/market-movers-gainers/
# =========================

def fetch_tradingview_gainers(max_rows: int = 200) -> pd.DataFrame:
    """
    簡易解析 TradingView 台股 top gainers 頁面。
    回傳欄位至少包含:
    ['symbol', 'tv_last', 'tv_change_pct', 'tv_volume']
    """
    url = "https://www.tradingview.com/markets/stocks-taiwan/market-movers-gainers/"
    data = []

    # TradingView is heavily dynamic. Attempt a simple requests fetch first, with retries.
    try:
        @retry(max_attempts=3, backoff=0.5)
        def _get():
            r = SESSION.get(url, timeout=10)
            r.raise_for_status()
            return r.text

        text = _get()

        # Try to extract tables using pandas first
        try:
            tables = pd.read_html(text)
            if tables:
                main = max(tables, key=lambda t: t.shape[0])
                # naive extraction from table
                for _, row in main.head(max_rows).iterrows():
                    text_row = " ".join([str(x) for x in row.values if pd.notna(x)])
                    import re
                    symbol_match = re.search(r'\b(\d{4})\b', text_row)
                    change_match = re.search(r'([+-]?\d+\.?\d*)\s*%', text_row)
                    last_match = re.search(r'([\d,]+\.?\d*)', text_row)
                    if not symbol_match:
                        continue
                    data.append({
                        "symbol": symbol_match.group(1),
                        "tv_last": float(last_match.group(1).replace(',', '')) if last_match else None,
                        "tv_change_pct": float(change_match.group(1)) if change_match else None,
                    })
                if data:
                    return pd.DataFrame(data)
        except Exception:
            pass

        # Fallback: try simple BeautifulSoup selectors (skeleton)
        soup = BeautifulSoup(text, "lxml")
        rows = soup.select(".tv-data-table__row, .tv-widget-table__row, tr")
        import re
        for r in rows[:max_rows]:
            text_content = r.get_text(" ", strip=True)
            symbol_match = re.search(r'\b(\d{4})\b', text_content)
            change_match = re.search(r'([+-]?\d+\.?\d*)\s*%', text_content)
            last_match = re.search(r'([\d,]+\.?\d*)', text_content)
            if not symbol_match:
                continue
            data.append({
                "symbol": symbol_match.group(1),
                "tv_last": float(last_match.group(1).replace(',', '')) if last_match else None,
                "tv_change_pct": float(change_match.group(1)) if change_match else None,
            })

    except Exception as e:
        logger.exception("Error fetching TradingView data: %s", e)

    return pd.DataFrame(data)


# =========================
# 資料來源 3: Goodinfo 現股當沖張數(當日) 排名
# 網址(示意): 熱門排行 -> 現股當沖張數(當日) 排名
# e.g. https://goodinfo.tw/tw/StockList.asp?MARKET_CAT=熱門排行&INDUSTRY_CAT=現股當沖張數(當日)排名
# =========================

def fetch_goodinfo_daytrading_volume(max_rows: int = 300) -> pd.DataFrame:
    """
    抓 Goodinfo「現股當沖張數(當日) 排名」。
    回傳欄位至少包含:
    ['symbol', 'name', 'dt_volume', 'dt_ratio']
    使用 Selenium 來處理 JavaScript 渲染和重定向。
    """
    url = (
        "https://goodinfo.tw/tw/StockList.asp"
        "?MARKET_CAT=%E7%86%B1%E9%96%80%E6%8E%92%E8%A1%8C"
        "&INDUSTRY_CAT=%E7%8F%BE%E8%82%A1%E7%95%B6%E6%B2%96%E5%BC%B5%E6%95%B8%28%E7%95%B6%E6%97%A5%29%E6%8E%92%E5%90%8D"
    )
    data = []
    driver = None
    try:
        driver = DRIVER_MANAGER.get_driver(headless=True)
        driver.get(url)

        # Wait for table to appear
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "table"))
            )
        except Exception:
            # proceed to parse whatever is available
            pass

        page = driver.page_source

        # Try pandas.read_html first (fast if a well-formed table exists)
        try:
            tables = pd.read_html(page)
            if tables:
                main = max(tables, key=lambda t: t.shape[0])
                # assume columns have useful info; iterate rows
                import re
                for _, row in main.head(max_rows).iterrows():
                    text = " ".join([str(x) for x in row.values if pd.notna(x)])
                    symbol_match = re.search(r'\b(\d{4})\b', text)
                    if not symbol_match:
                        continue
                    name_match = re.search(r'([\u4e00-\u9fff]+)', text)
                    vol_match = re.search(r'([\d,]+)', text)
                    ratio_match = re.search(r'([+-]?\d+\.?\d*)\s*%', text)
                    dt_volume = int(vol_match.group(1).replace(',', '')) if vol_match else None
                    dt_ratio = float(ratio_match.group(1)) if ratio_match else None
                    data.append({
                        "symbol": symbol_match.group(1),
                        "name": name_match.group(1) if name_match else "",
                        "dt_volume": dt_volume,
                        "dt_ratio": dt_ratio,
                    })
                if data:
                    return pd.DataFrame(data)
        except Exception:
            pass

        # Fallback: BeautifulSoup parse of the largest table
        soup = BeautifulSoup(page, "lxml")
        tables = soup.find_all("table")
        main_table = None
        max_rows_count = 0
        for t in tables:
            rows = t.find_all("tr")
            if len(rows) > max_rows_count:
                max_rows_count = len(rows)
                main_table = t

        if not main_table:
            return pd.DataFrame(data)

        import re
        for tr in main_table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 1:
                continue
            text_content = tr.get_text(" ", strip=True)
            symbol_match = re.search(r'\b(\d{4})\b', text_content)
            if not symbol_match:
                continue
            name_match = re.search(r'([\u4e00-\u9fff]+)', text_content)
            # Look for numbers (volume) and percentage
            vol_match = re.search(r'([\d,]+)', text_content)
            ratio_match = re.search(r'([+-]?\d+\.?\d*)\s*%', text_content)
            dt_volume = int(vol_match.group(1).replace(',', '')) if vol_match else None
            dt_ratio = float(ratio_match.group(1)) if ratio_match else None
            data.append({
                "symbol": symbol_match.group(1),
                "name": name_match.group(1) if name_match else "",
                "dt_volume": dt_volume,
                "dt_ratio": dt_ratio,
            })
            if len(data) >= max_rows:
                break

    except Exception as e:
        logger.exception("Error fetching Goodinfo data: %s", e)

    return pd.DataFrame(data)


# =========================
# 合併 & 打分數邏輯 (Skeleton)
# =========================

def build_daytrading_universe(top_n: int = 100) -> pd.DataFrame:
    """
    將多來源資料合併，輸出 Top N day-trading movers。
    這裡給一個簡單 scoring skeleton，你可以自己 tune。
    """

    # get data from Yahoo and Goodinfo
    logger.info("Fetching Yahoo gainers ...")
    df_yahoo = fetch_yahoo_top_gainers()      # [web:48]
    logger.info("  Yahoo rows: %d", len(df_yahoo))

    logger.info("Fetching Goodinfo day-trading volume ...")
    df_gi = fetch_goodinfo_daytrading_volume()  # [web:38]
    logger.info("  Goodinfo rows: %d", len(df_gi))

    # merge data from Yahoo and Goodinfo
    #   先標準化欄位名稱
    def norm_symbol(s):
        return str(s).strip()

    if not df_yahoo.empty:
        df_yahoo["symbol"] = df_yahoo["symbol"].map(norm_symbol)
    if not df_gi.empty:
        df_gi["symbol"] = df_gi["symbol"].map(norm_symbol)

    # 從 Goodinfo 當沖池開始，左併 Yahoo
    # 如果所有來源都是空的，返回空 DataFrame
    if df_gi.empty and df_yahoo.empty:
        logger.warning("All data sources returned empty results.")
        return pd.DataFrame()

    # 如果 Goodinfo 是空的，嘗試從 Yahoo 開始
    if df_gi.empty:
        if not df_yahoo.empty:
            base = df_yahoo.copy()
        else:
            return pd.DataFrame()
    else:
        base = df_gi.copy()

    if not df_yahoo.empty:
        base = base.merge(
            df_yahoo[["symbol", "yahoo_change_pct"]],
            on="symbol",
            how="left",
        )

    # 3) 簡單 scoring：
    #   - Yahoo 漲幅 > 0 給分
    #   - dt_volume & dt_ratio 大者優先
    #   - 你可以自己改成更 fancy 的 scoring
    base["score"] = 0.0

    if "yahoo_change_pct" in base.columns:
        base["score"] += base["yahoo_change_pct"].fillna(0) * 1.0

    if "dt_volume" in base.columns:
        base["score"] += (base["dt_volume"].fillna(0) / 1000.0)  # 規模縮小

    if "dt_ratio" in base.columns:
        base["score"] += base["dt_ratio"].fillna(0) * 2.0        # 當沖率權重

    # 4) 簡單過濾條件（你可以自己調參）
    #   - 漲幅 >= 3%
    #   - 當沖張數不為 None
    # 檢查是否有必要的欄位再進行過濾
    if base.empty:
        return base
    
    filt = pd.Series([True] * len(base), index=base.index)
    
    if "dt_volume" in base.columns:
        filt &= base["dt_volume"].notna()
    
    if "yahoo_change_pct" in base.columns:
        filt &= (base["yahoo_change_pct"].fillna(0) >= 3)

    base = base.loc[filt].copy()

    # 5) 依 score 排序，取前 top_n
    if base.empty:
        return base
    
    base = base.sort_values("score", ascending=False).head(top_n)

    # 6) 排個名次欄位
    if not base.empty:
        base.insert(0, "rank", range(1, len(base) + 1))

    return base


# =========================
# 匯出 Excel
# =========================

def export_to_excel(df: pd.DataFrame, filename: str = OUTPUT_FILE) -> None:
    if df.empty:
        logger.info("No data to export.")
        return

    with pd.ExcelWriter(filename, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Top100_DayTrading", index=False)

    logger.info("Saved to: %s", filename)


# =========================
# main
# =========================

if __name__ == "__main__":
    movers = build_daytrading_universe(top_n=100)
    logger.info("Result sample:\n%s", movers.head())
    export_to_excel(movers)
    # Ensure driver is closed when finished
    DRIVER_MANAGER.quit_driver()
