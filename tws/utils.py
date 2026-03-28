import re
import requests
import xml.etree.ElementTree as ET
import os
import logging
import pandas as pd
from datetime import datetime, timedelta
from typing import List

logger = logging.getLogger(__name__)


def get_last_trading_date(ref: datetime = None) -> datetime:
    """
    Return the most recent Taiwan Stock Exchange trading day.

    Rules applied (simple weekday-only, no TW holiday calendar):
      - Monday–Friday  → same day
      - Saturday       → previous Friday
      - Sunday         → previous Friday (2 days back)

    Pass ref=<datetime> to anchor from a specific point in time instead
    of 'now' (useful for back-running the pipeline with a fixed date).
    """
    d = (ref or datetime.now()).date()
    # 0=Mon … 4=Fri, 5=Sat, 6=Sun
    if d.weekday() == 5:        # Saturday
        d -= timedelta(days=1)
    elif d.weekday() == 6:      # Sunday
        d -= timedelta(days=2)
    return datetime.combine(d, datetime.min.time())


def is_trading_day(ref: datetime = None) -> bool:
    """Return True if ref (default: now) falls on a Mon–Fri trading day."""
    d = (ref or datetime.now()).date()
    return d.weekday() < 5


class TelegramTool:
    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{token}/sendMessage"

    def send_markdown(self, text):
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "Markdown"}
        try:
            requests.post(self.api_url, json=payload, timeout=10)
        except Exception as e:
            logger.exception("Telegram send error: %s", e)

    def send_photo(self, photo_bytes, caption: str = None):
        url = f"https://api.telegram.org/bot{self.token}/sendPhoto"
        files = {"photo": ("heatmap.png", photo_bytes)}
        data = {"chat_id": self.chat_id}
        if caption:
            data['caption'] = caption
            data['parse_mode'] = 'Markdown'
        try:
            requests.post(url, data=data, files=files, timeout=15)
        except Exception as e:
            logger.exception("Telegram send_photo error: %s", e)

    @staticmethod
    def fetch_google_news(ticker, name):
        query = f"{ticker} {name} 股價"
        url = f"https://news.google.com/rss/search?q={query}+when:1d&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        try:
            res = requests.get(url, timeout=5)
            root = ET.fromstring(res.content)
            items = root.findall('.//item')
            if items:
                return items[0].find('title').text.split(' - ')[0]
        except Exception as e:
            logger.debug("fetch_google_news error: %s", e)
        return "今日暫無重大新聞"


def fetch_google_news_many(ticker: str, name: str, days: int = 7, max_items: int = 5) -> List[str]:
    """Fetch recent news titles from Google News RSS for the given ticker/name.

    Returns a list of headlines (may be empty). Uses RSS search endpoint.
    """
    query = f"{ticker} {name} 股價"
    url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}+when:{days}d&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    titles = []
    try:
        res = requests.get(url, timeout=6)
        root = ET.fromstring(res.content)
        items = root.findall('.//item')
        for it in items[:max_items]:
            t = it.find('title')
            if t is not None:
                titles.append(t.text.split(' - ')[0])
    except Exception as e:
        logger.debug("fetch_google_news_many error: %s", e)
    return titles


def get_sentiment_score(texts: List[str]) -> float:
    """Return a sentiment score for a list of texts between -1 (neg) and +1 (pos).

    Tries to use VADER if available, otherwise falls back to a tiny rule-based lexicon.
    """
    if not texts:
        return 0.0

    joined = "\n".join(texts)

    # Try VADER
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        analyzer = SentimentIntensityAnalyzer()
        score = analyzer.polarity_scores(joined)['compound']
        return float(score)
    except Exception:
        # fallback simple lexicon
        pos = set(["上漲", "利多", "利好", "買進", "正面", "成長", "優於預期"])
        neg = set(["下跌", "利空", "賣出", "負面", "虧損", "賣超", "恐慌"])
        s = 0
        for t in texts:
            for w in pos:
                if w in t:
                    s += 1
            for w in neg:
                if w in t:
                    s -= 1
        # normalize
        return max(-1.0, min(1.0, s / max(1, len(texts) * 3)))


def fetch_twse_institutional(date_str: str):
    """Fetch TWSE daily institutional buy/sell (三大法人) data for a date (YYYYMMDD).

    This uses a public TWSE endpoint. The JSON structure can vary; we attempt to extract
    symbol, name and foreign net buy/sell (外資買賣超股數) by index.
    Returns a list of dicts: {symbol, name, foreign_net}
    """
    url = f"https://www.twse.com.tw/fund/T86?response=json&date={date_str}&selectType=ALLBUT0999"
    results = []
    try:
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        j = r.json()
        data = j.get('data', [])
        # typical columns: [證券代號, 證券名稱, 外資買進股數, 外資賣出股數, 外資買賣超股數, ...]
        for row in data:
            try:
                symbol = row[0].strip()
                name = row[1].strip()
                foreign_net_raw = row[4]
                # remove commas and parentheses
                if isinstance(foreign_net_raw, str):
                    foreign_net = int(foreign_net_raw.replace(',', '').replace('(', '-').replace(')', ''))
                else:
                    foreign_net = int(float(foreign_net_raw))
                results.append({"symbol": symbol, "name": name, "foreign_net": foreign_net})
            except Exception:
                continue
    except Exception as e:
        logger.debug("fetch_twse_institutional error: %s", e)
    return results


def _previous_trading_days(end_date_str: str, n: int):
    from datetime import datetime, timedelta
    end = datetime.strptime(end_date_str, '%Y%m%d')
    days = []
    d = end
    while len(days) < n:
        if d.weekday() < 5:  # Mon-Fri
            days.append(d.strftime('%Y%m%d'))
        d = d - timedelta(days=1)
    return days


def fetch_twse_institutional_range(end_date_str: str, days: int = 60):
    """Fetch institutional 外資 net data over the past `days` trading days ending at end_date_str.

    Returns a dict: {symbol: [net1, net2, ...]} ordered oldest->newest.
    """
    res_map = {}
    dates = _previous_trading_days(end_date_str, days)
    for dt in reversed(dates):
        rows = fetch_twse_institutional(dt)
        for r in rows:
            sym = r['symbol']
            net = r.get('foreign_net', 0)
            res_map.setdefault(sym, []).append(net)
    return res_map


def compute_foreign_metrics(series_list):
    """Given a list of foreign_net values (oldest->newest), compute sums for 5/20/60 days and z-score of last value."""
    import numpy as np
    if not series_list:
        return {'f5': None, 'f20': None, 'f60': None, 'zscore': None}
    arr = np.array(series_list, dtype=float)
    last = arr[-1]
    def s(n):
        if len(arr) >= n:
            return float(arr[-n:].sum())
        else:
            return float(arr.sum())

    mean = float(arr.mean()) if len(arr) > 1 else float(arr[-1])
    std = float(arr.std(ddof=0)) if len(arr) > 1 else 0.0
    z = None
    if std and std > 0:
        z = float((last - mean) / std)

    return {'f5': s(5), 'f20': s(20), 'f60': s(60), 'zscore': z}


def compute_percent_flows(f_metrics: dict, volume_series: list, base_window: int = 20):
    """Normalize rolling foreign_net sums by average daily volume to get percent flows.

    f_metrics: dict with keys f5,f20,f60
    volume_series: list of recent volumes (oldest->newest). We use average over base_window days.
    Returns dict with f5_pct,f20_pct,f60_pct (float or None)
    """
    import numpy as np
    out = {'f5_pct': None, 'f20_pct': None, 'f60_pct': None}
    if not volume_series:
        return out
    vol = np.array(volume_series, dtype=float)
    if len(vol) == 0:
        return out
    window = min(base_window, len(vol))
    avg_vol = float(vol[-window:].mean())
    if avg_vol == 0:
        return out

    for k, n in [('f5', 5), ('f20', 20), ('f60', 60)]:
        val = f_metrics.get(k)
        if val is None:
            out[f'{k}_pct'] = None
        else:
            denom = avg_vol * min(n, len(vol))
            out[f'{k}_pct'] = float(val / denom)
    return out


def fetch_twse_short_interest(date_str: str):
    """Attempt to fetch short selling (借券賣出) data for a given date.

    Returns dict {symbol: short_qty} if available, else empty dict.
    Note: TWSE endpoints for this data may change; this function tries a couple of known endpoints.
    """
    candidates = [
        f"https://www.twse.com.tw/exchangeReport/TWTB4U?response=json&date={date_str}&selectType=ALL",
        f"https://www.twse.com.tw/exchangeReport/TWTB4U?response=json&date={date_str}&selectType=ALLBUT0999",
    ]
    out = {}
    for url in candidates:
        try:
            r = requests.get(url, timeout=8)
            r.raise_for_status()
            j = r.json()
            fields = j.get('fields', [])
            data = j.get('data', [])
            # find likely header for short qty
            idx = None
            for i, h in enumerate(fields):
                if '借券賣出' in h or '借券' in h or '賣出' in h:
                    idx = i
                    break
            # fallback indices
            if idx is None and data and len(data[0]) >= 6:
                # often short qty sits around index 5
                idx = 5

            if idx is None:
                continue

            for row in data:
                try:
                    sym = row[0].strip()
                    raw = row[idx]
                    if isinstance(raw, str):
                        val = int(raw.replace(',', '').replace('(', '-').replace(')', ''))
                    else:
                        val = int(float(raw))
                    out[sym] = val
                except Exception:
                    continue
            if out:
                return out
        except Exception as e:
            logger.debug('short interest fetch failed for %s: %s', url, e)
    return out


# ---------------------------------------------------------------------------
# Full-market price data (for heatmap + trending industry)
# ---------------------------------------------------------------------------

def _twse_change_direction(html: str) -> int:
    """TWSE encodes direction in HTML: color:red → +1 (up), color:green → -1 (down)."""
    if 'color:red'   in html: return  1
    if 'color:green' in html: return -1
    return 0


def fetch_twse_all_prices(date_str: str) -> pd.DataFrame:
    """
    Fetch ALL TWSE regular-stock closing prices for one trading day.

    Uses the MI_INDEX?type=ALL endpoint which returns ~1000+ rows in table[8]
    (每日收盤行情).  Filters to 4-digit numeric ticker codes that don't start
    with '00' (removes ETFs, warrants, preferred shares, TDRs).

    Columns returned:
      ticker, name, open, high, low, close, volume (shares),
      value (NTD), change_pct (%), is_limit_up, is_limit_down
    """
    url = (
        "https://www.twse.com.tw/exchangeReport/MI_INDEX"
        f"?response=json&type=ALL&date={date_str}"
    )
    try:
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
        data = r.json()
        if data.get('stat') != 'OK':
            logger.warning("fetch_twse_all_prices: stat=%s for %s", data.get('stat'), date_str)
            return pd.DataFrame()

        # table[8] = 每日收盤行情(全部)
        price_table = next(
            (t for t in data.get('tables', []) if '每日收盤行情' in t.get('title', '')),
            None,
        )
        if not price_table:
            return pd.DataFrame()

        def _p(s):
            s = str(s).replace(',', '').strip()
            try:
                v = float(s)
                return v if v != 0 else None
            except ValueError:
                return None

        def _i(s) -> int:
            try:
                return int(str(s).replace(',', '').strip())
            except (ValueError, TypeError):
                return 0

        records = []
        for row in price_table.get('data', []):
            try:
                ticker = row[0].strip()
                if not re.fullmatch(r'[1-9]\d{3}', ticker):
                    continue                    # skip ETFs, warrants, TDRs

                close = _p(row[8])
                if close is None:
                    continue

                direction  = _twse_change_direction(str(row[9]))
                change_amt = abs(_p(row[10]) or 0.0)
                prev_close = close - direction * change_amt
                change_pct = (
                    direction * change_amt / prev_close * 100
                    if prev_close > 0 else 0.0
                )

                records.append({
                    'ticker':        ticker,
                    'name':          row[1].strip(),
                    'open':          _p(row[5]),
                    'high':          _p(row[6]),
                    'low':           _p(row[7]),
                    'close':         close,
                    'volume':        _i(row[2]),
                    'value':         _i(row[4]),
                    'change_pct':    round(change_pct, 2),
                    'is_limit_up':   change_pct >= 9.5,
                    'is_limit_down': change_pct <= -9.5,
                })
            except (IndexError, TypeError):
                continue

        return pd.DataFrame(records)

    except Exception as e:
        logger.exception("fetch_twse_all_prices failed: %s", e)
        return pd.DataFrame()