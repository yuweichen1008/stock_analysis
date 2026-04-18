"""
Stock bets + Finviz top-mover feeds + quick backtesting.

Endpoints
---------
GET  /api/stocks/movers          → real-time Finviz top movers (cached 15 min)
GET  /api/stocks/backtest        → quick 90-day backtest for a list of tickers
POST /api/stocks/bet             → place a Bull/Bear bet on a ticker
POST /api/stocks/settle          → settle all pending stock bets (pipeline call)
GET  /api/stocks/history/{id}    → user's stock bet history
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import yfinance as yf
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from api.db import StockBet, User, get_db

router = APIRouter(prefix="/api/stocks", tags=["stocks"])

STOCK_MIN_BET  = 50
STOCK_MAX_BET  = 500
MAX_DAILY_BETS = 3       # max stock bets per user per day
COIN_FLOOR     = 100


# ── Finviz movers cache (15-min TTL) ─────────────────────────────────────────

_movers_cache: dict = {"data": None, "ts": 0.0}
_CACHE_TTL = 15 * 60   # 15 minutes


def _fetch_movers() -> dict:
    now = time.time()
    if _movers_cache["data"] and now - _movers_cache["ts"] < _CACHE_TTL:
        return _movers_cache["data"]

    result: dict[str, list] = {
        "top_gainers":  [],
        "oversold":     [],
        "high_volume":  [],
    }

    try:
        from us.finviz_data import get_screener_results

        # Top gainers — fallback through time windows so weekends/after-hours still return data
        df_gain = pd.DataFrame()
        for perf_filter in ("Today +5%", "Week +5%", "Month +10%"):
            df_gain = get_screener_results(
                {"Performance": perf_filter, "Price": "Over $5", "Average Volume": "Over 500K"},
                order_by="Change",
            )
            if not df_gain.empty:
                break
        if not df_gain.empty:
            result["top_gainers"] = _normalise_fv(df_gain.head(10), "top_gainer")

        time.sleep(1)   # polite rate-limiting between Finviz calls

        # Oversold — RSI < 30, mid+ cap
        df_over = get_screener_results(
            {"RSI (14)": "Oversold (30)", "Market Cap.": "+Mid (over $2bln)"},
            order_by="RSI (14)",
        )
        if not df_over.empty:
            result["oversold"] = _normalise_fv(df_over.head(10), "oversold")

        time.sleep(1)

        # High volume — unusual activity
        df_vol = get_screener_results(
            {"Average Volume": "Over 500K", "Volume": "Over 2M", "Price": "Over $5"},
            order_by="Volume",
        )
        if not df_vol.empty:
            result["high_volume"] = _normalise_fv(df_vol.head(10), "high_volume")

    except Exception as e:
        print(f"[stocks] Finviz movers fetch error: {e}")

    # Deduplicated "all movers" list ranked by score
    seen: set = set()
    combined = []
    for cat, rows in result.items():
        for r in rows:
            if r["ticker"] not in seen:
                seen.add(r["ticker"])
                combined.append(r)
    result["all_movers"] = sorted(combined, key=lambda x: x.get("score", 0), reverse=True)

    _movers_cache["data"] = result
    _movers_cache["ts"]   = now
    return result


def _normalise_fv(df: pd.DataFrame, category: str) -> list[dict]:
    """Convert a Finviz screener DataFrame into a clean list of dicts."""
    rows = []
    for _, r in df.iterrows():
        ticker = str(r.get("Ticker", "")).strip()
        if not ticker:
            continue
        change_str = str(r.get("Change", "0%")).replace("%", "").strip()
        try:
            change = float(change_str)
        except ValueError:
            change = 0.0

        rsi_val = r.get("RSI (14)", None)
        try:
            rsi = float(rsi_val) if rsi_val else None
        except (TypeError, ValueError):
            rsi = None

        price_val = r.get("Price", None)
        try:
            price = float(price_val) if price_val else None
        except (TypeError, ValueError):
            price = None

        vol_str = str(r.get("Volume", "0")).replace(",", "").strip()
        try:
            volume = int(float(vol_str)) if vol_str else 0
        except ValueError:
            volume = 0

        # Simple score: higher is more interesting for betting
        score = abs(change) * 10 + (max(0, 30 - (rsi or 30)) if category == "oversold" else 0)

        rows.append({
            "ticker":   ticker,
            "name":     str(r.get("Company", ticker)),
            "sector":   str(r.get("Sector", "")),
            "price":    price,
            "change":   change,
            "volume":   volume,
            "rsi":      rsi,
            "pe":       _safe_float(r.get("P/E")),
            "category": category,
            "score":    round(score, 1),
        })
    return rows


def _safe_float(v) -> Optional[float]:
    try:
        return float(v) if v and str(v) not in ("-", "") else None
    except (TypeError, ValueError):
        return None


# ── Quick backtest (yfinance, 90 days, 1-day hold) ───────────────────────────

def _quick_backtest(tickers: list[str]) -> list[dict]:
    """
    Lightweight 1-day hold backtest using mean-reversion signal detection.
    Entry = signal-day close. Exit = next close. Win if price goes in bet direction.
    Uses apply_filters() from tws.taiwan_trending for signal detection.
    Returns per-ticker summary dicts.
    """
    from tws.taiwan_trending import apply_filters

    end   = datetime.now()
    start = end - timedelta(days=120)   # extra buffer for 90 trading days
    results = []

    for ticker in tickers[:10]:   # cap at 10 to avoid timeout
        try:
            df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
            if df is None or len(df) < 30:
                continue

            # Flatten multi-level columns if present
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df = df.rename(columns={
                "Open": "Open", "High": "High", "Low": "Low",
                "Close": "Close", "Volume": "Volume",
            })
            df.index = pd.to_datetime(df.index)
            df = df.dropna()

            wins = losses = 0
            total_return = 0.0
            signal_dates = []

            for i in range(20, len(df) - 1):
                window = df.iloc[:i + 1].copy()
                is_signal, _, _ = apply_filters(window)
                if not is_signal:
                    continue
                # 1-day hold: entry = close[i], exit = close[i+1]
                entry = float(df.iloc[i]["Close"])
                exit_ = float(df.iloc[i + 1]["Close"])
                if entry <= 0:
                    continue
                ret = (exit_ - entry) / entry
                total_return += ret
                if ret > 0:
                    wins += 1
                else:
                    losses += 1
                signal_dates.append(str(df.index[i].date()))

            total_trades = wins + losses
            results.append({
                "ticker":       ticker,
                "total_trades": total_trades,
                "wins":         wins,
                "losses":       losses,
                "win_rate":     round(wins / total_trades * 100, 1) if total_trades else 0.0,
                "avg_return":   round(total_return / total_trades * 100, 2) if total_trades else 0.0,
                "last_signal":  signal_dates[-1] if signal_dates else None,
            })
        except Exception as e:
            print(f"[backtest] {ticker} error: {e}")

    return results


# ── Schemas ───────────────────────────────────────────────────────────────────

class StockBetBody(BaseModel):
    device_id:  str
    ticker:     str
    direction:  str          # "Bull" | "Bear"
    bet_amount: int = Field(ge=STOCK_MIN_BET, le=STOCK_MAX_BET)
    category:   Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/movers")
def get_movers():
    """
    Real-time Finviz top movers: top_gainers, oversold, high_volume.
    Results are cached for 15 minutes.
    """
    data = _fetch_movers()
    return {
        **data,
        "cached_at": datetime.fromtimestamp(_movers_cache["ts"], tz=timezone.utc).isoformat()
                     if _movers_cache["ts"] else None,
    }


@router.get("/backtest")
def get_backtest(tickers: str = ""):
    """
    Quick 90-day mean-reversion backtest on a comma-separated list of tickers.
    E.g. /api/stocks/backtest?tickers=AAPL,TSLA,NVDA
    Uses 1-day hold: signal day close → next day close.
    """
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        # Default: fetch top movers and backtest those
        movers = _fetch_movers()
        ticker_list = [m["ticker"] for m in movers.get("all_movers", [])[:8]]
    if not ticker_list:
        return {"results": [], "note": "no tickers"}
    results = _quick_backtest(ticker_list)
    results.sort(key=lambda x: x["win_rate"], reverse=True)
    return {"results": results, "tickers_tested": len(results)}


@router.post("/bet")
def place_stock_bet(body: StockBetBody, db: Session = Depends(get_db)):
    """Place a Bull/Bear bet on a Finviz top-mover ticker."""
    if body.direction not in ("Bull", "Bear"):
        raise HTTPException(400, "direction must be 'Bull' or 'Bear'")

    ticker = body.ticker.strip().upper()
    if not ticker:
        raise HTTPException(400, "ticker is required")

    user = db.get(User, body.device_id)
    if not user:
        raise HTTPException(404, "Device not registered. Call /sandbox/register first.")

    today = datetime.now().strftime("%Y-%m-%d")

    # Max N bets per day
    today_bets = (
        db.query(StockBet)
        .filter(StockBet.device_id == body.device_id, StockBet.bet_date == today)
        .all()
    )
    if len(today_bets) >= MAX_DAILY_BETS:
        raise HTTPException(409, f"Max {MAX_DAILY_BETS} stock bets per day reached")

    # No duplicate ticker on same day
    existing = next((b for b in today_bets if b.ticker == ticker), None)
    if existing:
        raise HTTPException(409, f"Already placed a bet on {ticker} today")

    # Coin checks
    if user.coins < body.bet_amount:
        raise HTTPException(400, f"Insufficient coins: have {user.coins}, need {body.bet_amount}")
    if user.coins - body.bet_amount < COIN_FLOOR:
        max_allowed = max(STOCK_MIN_BET, user.coins - COIN_FLOOR)
        raise HTTPException(400, f"Cannot go below {COIN_FLOOR} coins. Max bet: {max_allowed}")

    # Fetch current price (official close from yfinance history)
    entry_price = None
    try:
        hist = yf.Ticker(ticker).history(period="1d")
        if not hist.empty:
            entry_price = float(hist["Close"].iloc[-1])
    except Exception:
        pass

    bet = StockBet(
        device_id=body.device_id,
        ticker=ticker,
        bet_date=today,
        direction=body.direction,
        bet_amount=body.bet_amount,
        entry_price=entry_price,
        category=body.category,
    )
    db.add(bet)
    db.commit()
    db.refresh(bet)

    return {
        "bet_id":          bet.id,
        "ticker":          ticker,
        "direction":       body.direction,
        "amount":          body.bet_amount,
        "entry_price":     entry_price,
        "status":          "pending",
        "potential_win":   body.bet_amount,
        "potential_loss":  body.bet_amount // 2,
        "note":            "Settles at next trading day close",
    }


@router.post("/settle")
def settle_stock_bets(db: Session = Depends(get_db)):
    """
    Internal endpoint — settle all pending stock bets using latest close prices.
    Called by pipeline after US market close (~18:30 TST).
    """
    pending = db.query(StockBet).filter(StockBet.status == "pending").all()
    if not pending:
        return {"settled": 0}

    # Group by ticker to batch yfinance calls — fetch 5d so we have T and T+1 rows
    tickers_needed = list({b.ticker for b in pending})
    histories: dict[str, pd.DataFrame] = {}
    for ticker in tickers_needed:
        try:
            hist = yf.Ticker(ticker).history(period="5d")
            if not hist.empty:
                hist.index = pd.to_datetime(hist.index).normalize()
                histories[ticker] = hist
        except Exception:
            pass

    settled_count = 0
    for bet in pending:
        hist = histories.get(bet.ticker)
        if hist is None or hist.empty:
            continue   # price unavailable — try again next cycle

        user = db.get(User, bet.device_id)
        if not user:
            continue

        # Find the row for the bet date, then use the NEXT row as exit (T+1 model)
        bet_dt = pd.Timestamp(bet.bet_date).normalize()
        if bet_dt not in hist.index:
            # bet_date not in the 5-day window — data not yet available
            continue
        pos = hist.index.get_loc(bet_dt)
        if pos >= len(hist) - 1:
            # No next-day row yet — market hasn't closed T+1
            continue

        entry = bet.entry_price if bet.entry_price else float(hist.iloc[pos]["Close"])
        exit_ = float(hist.iloc[pos + 1]["Close"])

        moved_up = exit_ > entry

        bet.exit_price = exit_
        bet.is_correct = (bet.direction == "Bull") == moved_up
        if bet.is_correct:
            bet.payout   = bet.bet_amount
            user.coins  += bet.payout
        else:
            bet.payout   = -(bet.bet_amount // 2)
            user.coins   = max(COIN_FLOOR, user.coins + bet.payout)

        bet.status  = "settled"
        settled_count += 1

    db.commit()
    return {"settled": settled_count, "tickers_fetched": len(histories)}


@router.get("/history/{device_id}")
def get_stock_history(device_id: str, limit: int = 30, db: Session = Depends(get_db)):
    """User's personal stock bet history, newest first."""
    user = db.get(User, device_id)
    if not user:
        raise HTTPException(404, "Device not registered.")

    bets = (
        db.query(StockBet)
        .filter(StockBet.device_id == device_id)
        .order_by(StockBet.bet_date.desc(), StockBet.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id":          b.id,
            "ticker":      b.ticker,
            "date":        b.bet_date,
            "direction":   b.direction,
            "amount":      b.bet_amount,
            "entry_price": b.entry_price,
            "exit_price":  b.exit_price,
            "is_correct":  b.is_correct,
            "payout":      b.payout,
            "status":      b.status,
            "category":    b.category,
        }
        for b in bets
    ]


@router.get("/stats/{device_id}")
def get_stock_stats(device_id: str, db: Session = Depends(get_db)):
    """Per-user stock bet win rate and payout stats."""
    user = db.get(User, device_id)
    if not user:
        raise HTTPException(404, "Device not registered.")

    settled = (
        db.query(StockBet)
        .filter(StockBet.device_id == device_id, StockBet.status == "settled")
        .all()
    )
    wins   = sum(1 for b in settled if b.is_correct)
    losses = len(settled) - wins
    total_payout = sum((b.payout or 0) for b in settled)

    # Per-ticker breakdown
    by_ticker: dict[str, dict] = {}
    for b in settled:
        t = b.ticker
        if t not in by_ticker:
            by_ticker[t] = {"wins": 0, "losses": 0, "payout": 0}
        if b.is_correct:
            by_ticker[t]["wins"]   += 1
        else:
            by_ticker[t]["losses"] += 1
        by_ticker[t]["payout"] += b.payout or 0

    ticker_stats = [
        {
            "ticker":   t,
            "trades":   v["wins"] + v["losses"],
            "wins":     v["wins"],
            "win_rate": round(v["wins"] / (v["wins"] + v["losses"]) * 100, 1)
                        if (v["wins"] + v["losses"]) else 0.0,
            "payout":   v["payout"],
        }
        for t, v in sorted(by_ticker.items(), key=lambda x: -x[1]["payout"])
    ]

    return {
        "total_bets":   len(settled),
        "wins":         wins,
        "losses":       losses,
        "win_rate_pct": round(wins / len(settled) * 100, 1) if settled else 0.0,
        "total_payout": total_payout,
        "by_ticker":    ticker_stats,
    }
