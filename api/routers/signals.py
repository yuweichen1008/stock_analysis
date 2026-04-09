"""
Signal list endpoints — reads current_trending.csv files directly.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from fastapi import APIRouter

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

router = APIRouter(prefix="/api/signals", tags=["signals"])

_NUMERIC = ["score", "price", "RSI", "bias", "vol_ratio",
            "MA120", "MA20", "foreign_net", "f60"]


def _load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        df = pd.read_csv(path, dtype={"ticker": str})
        for col in _NUMERIC:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        # Replace NaN with None for JSON serialisation
        df = df.where(pd.notna(df), None)
        return df.to_dict(orient="records")
    except Exception:
        return []


@router.get("/tw")
def get_tw_signals():
    """Today's Taiwan mean-reversion signals."""
    path = BASE_DIR / "current_trending.csv"
    rows = _load_csv(path)
    signals   = [r for r in rows if r.get("is_signal") or r.get("category") == "mean_reversion"]
    watchlist = [r for r in rows if r.get("category") == "high_value_moat"]
    return {"signals": signals, "watchlist": watchlist, "total": len(rows)}


@router.get("/us")
def get_us_signals():
    """Today's US mean-reversion signals and finviz watchlist."""
    path = BASE_DIR / "data_us" / "current_trending.csv"
    rows = _load_csv(path)
    signals   = [r for r in rows if str(r.get("is_signal", "")).lower() == "true"]
    watchlist = [r for r in rows if r.get("category") == "finviz_watch"]
    return {"signals": signals, "watchlist": watchlist, "total": len(rows)}
