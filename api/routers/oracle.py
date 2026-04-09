"""
Oracle prediction endpoints — reads oracle_history.csv directly.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
from fastapi import APIRouter

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from tws.index_tracker import _load_history, oracle_stats, get_taiex_live

router = APIRouter(prefix="/api/oracle", tags=["oracle"])


def _row_to_dict(row: pd.Series) -> dict:
    factors = {}
    try:
        factors = json.loads(str(row.get("factors_json") or "{}"))
    except Exception:
        pass
    return {
        "date":             row.get("date"),
        "direction":        row.get("direction"),
        "confidence_pct":   row.get("confidence_pct"),
        "factors":          factors,
        "taiex_open":       row.get("taiex_open"),
        "taiex_close":      row.get("taiex_close"),
        "taiex_change_pts": row.get("taiex_change_pts"),
        "score_pts":        row.get("score_pts"),
        "cumulative_score": row.get("cumulative_score"),
        "is_correct":       str(row.get("is_correct", "")).lower() in ("true", "1"),
        "status":           row.get("status"),
    }


@router.get("/today")
def get_today():
    """Today's Oracle prediction (pending or resolved)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d")
    df = _load_history(str(BASE_DIR))
    if df.empty:
        return {"date": today, "status": "no_prediction"}
    rows = df[df["date"] == today]
    if rows.empty:
        return {"date": today, "status": "no_prediction"}
    return _row_to_dict(rows.iloc[-1])


@router.get("/live")
def get_live():
    """Current TAIEX level + intraday change (15-min delayed)."""
    live = get_taiex_live()
    return {
        "current_level": live["current_level"],
        "change_pts":    live["change_pts"],
        "change_pct":    live["change_pct"],
        "last_updated":  live["last_updated"],
    }


@router.get("/history")
def get_history(limit: int = 30):
    """Recent resolved predictions, newest first."""
    df = _load_history(str(BASE_DIR))
    if df.empty:
        return []
    resolved = df[df["status"] == "resolved"].sort_values("date", ascending=False)
    return [_row_to_dict(row) for _, row in resolved.head(limit).iterrows()]


@router.get("/stats")
def get_stats():
    """Aggregate Oracle stats (win rate, cumulative score, streak)."""
    return oracle_stats(str(BASE_DIR))
