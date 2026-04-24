"""
Fetch news from Google News RSS and persist to DB.

Extends the existing tws/utils.py approach with:
- Full RSS item parsing (link, source, pubDate)
- SHA1-based deduplication via external_id
- Support for market-wide queries (ticker=None, market="MARKET")
- 24h window (when:1d) for tight recency
"""
from __future__ import annotations

import hashlib
import logging
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from tws.utils import get_sentiment_score

logger = logging.getLogger(__name__)

# Broad market-level queries — produce items with ticker=None, market="MARKET"
BROAD_QUERIES = [
    ("S&P 500 market today", "MARKET"),
    ("NASDAQ earnings today", "MARKET"),
    ("stock market news today", "MARKET"),
    ("Federal Reserve interest rates", "MARKET"),
    ("options market unusual activity", "MARKET"),
]


def _external_id(ticker: Optional[str], headline: str, pubdate: str) -> str:
    raw = f"{ticker or ''}{headline[:80]}{pubdate}"
    return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()


def _parse_pubdate(pubdate_str: Optional[str]) -> datetime:
    if not pubdate_str:
        return datetime.now(timezone.utc)
    try:
        dt = parsedate_to_datetime(pubdate_str)
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return datetime.now(timezone.utc)


def fetch_news_items(
    query: str,
    ticker: Optional[str],
    market: str,
    max_items: int = 10,
    lang: str = "en",
    gl: str = "US",
    ceid: str = "US:en",
) -> list[dict]:
    """
    Fetch news from Google News RSS and return parsed item dicts.

    Each dict has keys: external_id, ticker, market, headline, source, url,
    published_at (naive UTC datetime), fetched_at, sentiment_score.
    """
    encoded = requests.utils.quote(query)
    url = (
        f"https://news.google.com/rss/search"
        f"?q={encoded}+when:1d&hl={lang}&gl={gl}&ceid={ceid}"
    )
    items: list[dict] = []
    now_utc = datetime.utcnow()

    try:
        res = requests.get(url, timeout=8)
        root = ET.fromstring(res.content)
        for it in root.findall(".//item")[:max_items]:
            title_el  = it.find("title")
            link_el   = it.find("link")
            source_el = it.find("source")
            pubdate_el = it.find("pubDate")

            if title_el is None or not title_el.text:
                continue

            headline   = title_el.text.split(" - ")[0].strip()
            url_val    = link_el.text.strip() if link_el is not None and link_el.text else None
            source_val = source_el.text.strip() if source_el is not None and source_el.text else None
            pubdate    = pubdate_el.text.strip() if pubdate_el is not None and pubdate_el.text else ""
            pub_dt     = _parse_pubdate(pubdate)
            ext_id     = _external_id(ticker, headline, pubdate)
            sentiment  = get_sentiment_score([headline])

            items.append({
                "external_id":     ext_id,
                "ticker":          ticker,
                "market":          market,
                "headline":        headline,
                "source":          source_val,
                "url":             url_val,
                "published_at":    pub_dt,
                "fetched_at":      now_utc,
                "sentiment_score": sentiment,
            })
    except Exception as exc:
        logger.warning("fetch_news_items(%s) error: %s", query, exc)

    return items


def fetch_ticker_news(ticker: str, market: str, max_items: int = 8) -> list[dict]:
    """Fetch news for a specific ticker symbol."""
    if market == "TW":
        query = f"{ticker} 股價 新聞"
        return fetch_news_items(
            query, ticker, market, max_items,
            lang="zh-TW", gl="TW", ceid="TW:zh-Hant",
        )
    return fetch_news_items(
        f"{ticker} stock news", ticker, market, max_items,
    )


def fetch_broad_market_news() -> list[dict]:
    """Fetch market-wide news (S&P 500, NASDAQ, Fed, etc.)."""
    items: list[dict] = []
    for query, market in BROAD_QUERIES:
        items.extend(fetch_news_items(query, None, market, max_items=5))
    return items
