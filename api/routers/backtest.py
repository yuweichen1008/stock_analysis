"""
Backtesting API — run signal strategy backtests from the web dashboard.

GET /api/backtest/options   — RSI+PCR options strategy (WeeklySignal history)
GET /api/backtest/signals   — TWS mean-reversion backtest on OHLCV CSVs
"""
from __future__ import annotations

import asyncio
import glob
import os
import time

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/backtest", tags=["backtest"])

_cache_options: dict = {"data": None, "ts": 0.0}
_OPTIONS_TTL = 3600.0  # 1 hour — DB rarely changes


@router.get("/options")
async def get_options_backtest():
    """Run the RSI+PCR options screener strategy backtest against WeeklySignal history."""
    if _cache_options["data"] is not None and time.time() - _cache_options["ts"] < _OPTIONS_TTL:
        return _cache_options["data"]

    def _run():
        from options_backtester import run_backtest
        return run_backtest()

    try:
        result = await asyncio.to_thread(_run)
        _cache_options["data"] = result
        _cache_options["ts"] = time.time()
        return result
    except Exception as exc:
        return {
            "error": str(exc),
            "note": "Requires WeeklySignal rows with pcr and return_pct populated. "
                    "Run the weekly signal pipeline first.",
        }


@router.get("/signals")
async def get_signals_backtest(
    start_date:      str   = Query("2024-01-01", description="Backtest start date YYYY-MM-DD"),
    end_date:        str   = Query("2026-01-01", description="Backtest end date YYYY-MM-DD"),
    holding_days:    int   = Query(5,  ge=1, le=30),
    stop_loss_pct:   float = Query(0.05, ge=0.01, le=0.5),
    take_profit_pct: float = Query(0.10, ge=0.01, le=1.0),
    max_tickers:     int   = Query(30, ge=1, le=100),
):
    """Run the TWS mean-reversion backtest on locally cached OHLCV CSV data."""

    def _run():
        from backtester import Backtester

        root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        ohlcv_dir = os.path.join(root, "data", "ohlcv")
        all_files = glob.glob(os.path.join(ohlcv_dir, "*.csv"))
        tickers = list({os.path.basename(f).split("_")[0] for f in all_files})[:max_tickers]

        if not tickers:
            return {
                "error": "No OHLCV data found",
                "note": "Run `python tws/core.py` to download OHLCV data first.",
            }

        bt = Backtester(start_date=start_date, end_date=end_date)
        trades_df, summary = bt.run(
            tickers,
            holding_days=holding_days,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
        )

        if trades_df.empty:
            return {
                "summary": summary,
                "trades": [],
                "equity_curve": [],
                "tickers_tested": len(tickers),
            }

        # Build equity curve
        capital = 100_000.0
        invest_per_trade = capital / 10
        equity_curve = [{"date": start_date, "equity": round(capital, 0)}]
        for _, row in trades_df.sort_values("exit_date").iterrows():
            if row["entry_price"] > 0:
                shares = invest_per_trade / row["entry_price"]
                capital += row["net_profit"] * shares
            equity_curve.append({"date": row["exit_date"], "equity": round(capital, 0)})

        trades = trades_df.to_dict(orient="records")

        return {
            "summary": summary,
            "trades": trades[:200],
            "equity_curve": equity_curve,
            "tickers_tested": len(tickers),
        }

    try:
        return await asyncio.to_thread(_run)
    except Exception as exc:
        return {"error": str(exc)}
