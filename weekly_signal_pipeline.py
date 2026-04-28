"""
Weekly contrarian strategy pipeline — runs every Monday 10:30 ET.

Scans 4500+ US stocks for the most recently completed trading week.
Stocks up ≥5% → SELL signal (fade momentum).
Stocks down ≥5% → BUY signal (buy the dip).

PCR is snapshotted for every signal ticker to show market positioning.
Actual $5 trades are placed only when WEEKLY_DRY_RUN=false (default: dry run).

Usage:
    WEEKLY_DRY_RUN=true python weekly_signal_pipeline.py
    WEEKLY_DRY_RUN=false python weekly_signal_pipeline.py   # live trading
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from us.core import compute_weekly_returns, get_us_universe
from news.pcr import fetch_pcr
from api.db import SessionLocal, WeeklySignal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

DRY_RUN   = os.getenv("WEEKLY_DRY_RUN", "true").lower() != "false"
THRESHOLD = 0.05   # 5%
TRADE_USD = 5.0


def _place_order(ticker: str, side: str, qty: float) -> bool:
    """Place a market order via BrokerManager. Returns True on success."""
    try:
        from brokers.manager import BrokerManager
        broker_name = os.getenv("WEEKLY_BROKER", "Robinhood")
        manager = BrokerManager()
        manager.connect_all()
        result = manager.place_order(broker_name, ticker, side, qty, "MARKET")
        if result.get("success"):
            logging.info(f"Order placed: {side} {qty} {ticker} via {broker_name}")
            return True
        logging.warning(f"Order failed for {ticker}: {result.get('message')}")
    except Exception as exc:
        logging.error(f"Broker error for {ticker}: {exc}")
    return False


def main() -> None:
    logging.info(f"Weekly signal pipeline starting (dry_run={DRY_RUN})")

    tickers = get_us_universe()
    logging.info(f"Universe: {len(tickers)} tickers")

    returns = compute_weekly_returns(tickers)
    logging.info(f"Weekly returns computed: {len(returns)} tickers")

    signals = [r for r in returns if abs(r["return_pct"]) >= THRESHOLD]
    logging.info(f"Signal count (±{int(THRESHOLD*100)}%): {len(signals)}")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db = SessionLocal()
    inserted = skipped = executed = 0

    for r in returns:
        sig_type: str | None = None
        if r["return_pct"] >= THRESHOLD:
            sig_type = "sell"
        elif r["return_pct"] <= -THRESHOLD:
            sig_type = "buy"

        pcr_data: dict = {}
        if sig_type:
            pcr_data = fetch_pcr(r["ticker"]) or {}

        row = WeeklySignal(
            ticker      = r["ticker"],
            week_ending = r["week_ending"],
            return_pct  = r["return_pct"],
            signal_type = sig_type,
            last_price  = r["last_price"],
            pcr         = pcr_data.get("pcr"),
            pcr_label   = pcr_data.get("pcr_label"),
            put_volume  = pcr_data.get("put_volume"),
            call_volume = pcr_data.get("call_volume"),
            executed    = False,
            created_at  = now,
        )

        if sig_type and not DRY_RUN and r["last_price"] > 0:
            side = "SELL" if sig_type == "sell" else "BUY"
            qty  = round(TRADE_USD / r["last_price"], 4)
            if _place_order(r["ticker"], side, qty):
                row.executed   = True
                row.order_side = side
                row.order_qty  = qty
                executed += 1

        try:
            db.merge(row)
            inserted += 1
        except Exception as exc:
            logging.warning(f"DB merge failed for {r['ticker']}: {exc}")
            db.rollback()
            skipped += 1

    db.commit()
    db.close()
    logging.info(
        f"Done — {inserted} rows written, {skipped} skipped, "
        f"{executed} orders placed (dry_run={DRY_RUN})"
    )


if __name__ == "__main__":
    main()
