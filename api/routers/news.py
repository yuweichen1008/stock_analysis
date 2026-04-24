"""
News feed API — 12-hour rolling news with PCR (put/call ratio) indicators.

Endpoints:
  GET /api/news/feed          — recent news with latest PCR per item
  GET /api/news/{id}/pcr-history  — PCR timeline snapshots for one news item
  GET /api/news/{id}/related  — related news items cross-linked by ticker/keywords
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.db import NewsItem, NewsPcrSnapshot, get_db

router = APIRouter(prefix="/api/news", tags=["news"])

# 5-minute in-memory feed cache (same pattern as signals.py / stocks.py)
_feed_cache: dict = {"data": None, "ts": 0.0, "key": ""}
_FEED_TTL = 5 * 60


def _sentiment_label(score: Optional[float]) -> str:
    if score is None:
        return "neutral"
    if score > 0.05:
        return "positive"
    if score < -0.05:
        return "negative"
    return "neutral"


def _item_to_dict(item: NewsItem, latest_pcr: Optional[NewsPcrSnapshot], pcr_count: int, related_count: int) -> dict:
    return {
        "id":                 item.id,
        "ticker":             item.ticker,
        "market":             item.market,
        "headline":           item.headline,
        "source":             item.source,
        "url":                item.url,
        "published_at":       item.published_at.isoformat() + "Z" if item.published_at else None,
        "sentiment_score":    item.sentiment_score,
        "sentiment_label":    _sentiment_label(item.sentiment_score),
        "pcr":                latest_pcr.pcr if latest_pcr else None,
        "pcr_label":          latest_pcr.pcr_label if latest_pcr else None,
        "put_volume":         latest_pcr.put_volume if latest_pcr else None,
        "call_volume":        latest_pcr.call_volume if latest_pcr else None,
        "pcr_snapshot_count": pcr_count,
        "related_count":      related_count,
    }


@router.get("/feed")
def news_feed(
    hours:  int = Query(default=12, ge=1, le=24),
    market: str = Query(default="all"),
    limit:  int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Return recent news items with latest PCR snapshot.

    market: all | US | TW | MARKET
    hours:  lookback window (default 12, max 24)
    """
    # Cache key includes query params that affect results
    cache_key = f"{hours}:{market}"
    now = time.time()
    if (
        _feed_cache["data"] is not None
        and _feed_cache["key"] == cache_key
        and now - _feed_cache["ts"] < _FEED_TTL
    ):
        data = _feed_cache["data"]
        return data[offset: offset + limit]

    cutoff = datetime.utcnow() - timedelta(hours=hours)
    q = db.query(NewsItem).filter(NewsItem.published_at >= cutoff)

    if market.upper() != "ALL":
        q = q.filter(NewsItem.market == market.upper())

    items = q.order_by(NewsItem.published_at.desc()).all()

    # Build latest PCR + count maps
    item_ids = [it.id for it in items]
    pcr_rows = (
        db.query(NewsPcrSnapshot)
        .filter(NewsPcrSnapshot.news_item_id.in_(item_ids))
        .order_by(NewsPcrSnapshot.snapshot_at.desc())
        .all()
    ) if item_ids else []

    latest_pcr: dict[int, NewsPcrSnapshot] = {}
    pcr_count:  dict[int, int] = {}
    for row in pcr_rows:
        pcr_count[row.news_item_id] = pcr_count.get(row.news_item_id, 0) + 1
        if row.news_item_id not in latest_pcr:
            latest_pcr[row.news_item_id] = row

    result = []
    for item in items:
        related = []
        try:
            related = json.loads(item.related_ids) if item.related_ids else []
        except Exception:
            pass
        result.append(_item_to_dict(
            item,
            latest_pcr.get(item.id),
            pcr_count.get(item.id, 0),
            len(related),
        ))

    _feed_cache["data"] = result
    _feed_cache["ts"]   = now
    _feed_cache["key"]  = cache_key

    return result[offset: offset + limit]


@router.get("/{news_id}/pcr-history")
def pcr_history(news_id: int, db: Session = Depends(get_db)):
    """
    Return the PCR snapshot timeline for a single news item.

    Used to render the PCR chart in both the iOS app and web dashboard.
    """
    item = db.query(NewsItem).filter_by(id=news_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="News item not found")

    snapshots = (
        db.query(NewsPcrSnapshot)
        .filter_by(news_item_id=news_id)
        .order_by(NewsPcrSnapshot.snapshot_at.asc())
        .all()
    )

    return {
        "news_id": news_id,
        "ticker":  item.ticker,
        "snapshots": [
            {
                "snapshot_at":  s.snapshot_at.isoformat() + "Z" if s.snapshot_at else None,
                "pcr":          s.pcr,
                "pcr_label":    s.pcr_label,
                "put_volume":   s.put_volume,
                "call_volume":  s.call_volume,
            }
            for s in snapshots
        ],
    }


@router.get("/{news_id}/related")
def related_news(news_id: int, db: Session = Depends(get_db)):
    """
    Return news items cross-linked to the given item.

    Related IDs are pre-computed by the news pipeline (Jaccard similarity + same ticker).
    """
    item = db.query(NewsItem).filter_by(id=news_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="News item not found")

    related_ids: list[int] = []
    try:
        related_ids = json.loads(item.related_ids) if item.related_ids else []
    except Exception:
        pass

    if not related_ids:
        return {"news_id": news_id, "related": []}

    related_items = db.query(NewsItem).filter(NewsItem.id.in_(related_ids)).all()

    pcr_rows = (
        db.query(NewsPcrSnapshot)
        .filter(NewsPcrSnapshot.news_item_id.in_(related_ids))
        .order_by(NewsPcrSnapshot.snapshot_at.desc())
        .all()
    )
    latest_pcr: dict[int, NewsPcrSnapshot] = {}
    pcr_count:  dict[int, int] = {}
    for row in pcr_rows:
        pcr_count[row.news_item_id] = pcr_count.get(row.news_item_id, 0) + 1
        if row.news_item_id not in latest_pcr:
            latest_pcr[row.news_item_id] = row

    return {
        "news_id": news_id,
        "related": [
            _item_to_dict(
                it,
                latest_pcr.get(it.id),
                pcr_count.get(it.id, 0),
                0,  # don't nest related-of-related
            )
            for it in related_items
        ],
    }
