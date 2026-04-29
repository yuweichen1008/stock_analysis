"""
Options screener pipeline — runs weekdays at 09:45 ET and 15:30 ET.

Scans ~200 pre-filtered US stocks for unusual options activity, RSI extremes,
and PCR sentiment. Scores each signal 0-10 and pushes top results to iOS
subscribers + Telegram when OPTIONS_DRY_RUN=false.

Usage:
    OPTIONS_DRY_RUN=true  python options_screener_pipeline.py   # safe (default)
    OPTIONS_DRY_RUN=false python options_screener_pipeline.py   # live notifications
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from options.universe import get_options_universe
from options.fetcher  import fetch_options_metrics
from options.signals  import classify_signal
from api.db import SessionLocal, OptionsSignal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

DRY_RUN      = os.getenv("OPTIONS_DRY_RUN", "true").lower() != "false"
INTERNAL_KEY = os.getenv("INTERNAL_API_SECRET", "")
API_BASE     = os.getenv("ORACLE_API_BASE", "http://localhost:8000")
TG_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN", "")


def _rounded_snapshot_at() -> datetime:
    """Round current UTC time to nearest 15-minute bucket for idempotent merges."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    bucket = (now.minute // 15) * 15
    return now.replace(minute=bucket, second=0, microsecond=0)


def _notify_push(db) -> None:
    """POST to internal broadcast endpoint to trigger iOS push notifications."""
    import urllib.request
    import json
    try:
        payload = json.dumps({"type": "options_signals"}).encode()
        req = urllib.request.Request(
            f"{API_BASE}/api/notify/broadcast",
            data=payload,
            headers={
                "Content-Type":     "application/json",
                "X-Internal-Secret": INTERNAL_KEY,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            logging.info("Push broadcast result: %s", result)
    except Exception as exc:
        logging.warning("Push broadcast failed: %s", exc)


def _notify_telegram(top_signals: list[dict]) -> None:
    """Send top options signals to all Telegram subscribers via Bot API."""
    if not TG_TOKEN or not top_signals:
        return
    try:
        import urllib.request, json
        from api.db import Subscriber, SessionLocal as SL
        sub_db = SL()
        subs = sub_db.query(Subscriber).filter(Subscriber.active == True).all()
        sub_db.close()

        if not subs:
            return

        lines = ["📊 *Oracle Options Signals*\n"]
        for s in top_signals[:5]:
            emoji = "🟢" if s["signal_type"] == "buy_signal" else ("🔴" if s["signal_type"] == "sell_signal" else "⚡")
            label = s["signal_type"].replace("_", " ").title()
            rsi   = f"{s['rsi_14']:.1f}" if s.get("rsi_14") is not None else "n/a"
            pcr   = f"{s['pcr']:.2f}" if s.get("pcr") is not None else "n/a"
            ivr   = f"{s['iv_rank']:.0f}" if s.get("iv_rank") is not None else "—"
            lines.append(
                f"{emoji} *{s['ticker']}* — {label} (score {s['signal_score']:.1f})\n"
                f"RSI: {rsi}  PCR: {pcr}({s.get('pcr_label','')})  IV Rank: {ivr}"
            )
        text = "\n\n".join(lines)

        for sub in subs:
            try:
                payload = json.dumps({
                    "chat_id":    sub.telegram_id,
                    "text":       text,
                    "parse_mode": "Markdown",
                }).encode()
                req = urllib.request.Request(
                    f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                urllib.request.urlopen(req, timeout=10)
                time.sleep(0.05)
            except Exception as exc:
                logging.debug("Telegram send failed for %s: %s", sub.telegram_id, exc)

        logging.info("Telegram broadcast sent to %d subscribers", len(subs))
    except Exception as exc:
        logging.warning("Telegram broadcast error: %s", exc)


def main() -> None:
    logging.info("Options screener pipeline starting (dry_run=%s)", DRY_RUN)

    db = SessionLocal()
    snapshot_at = _rounded_snapshot_at()
    logging.info("Snapshot bucket: %s", snapshot_at.isoformat())

    tickers = get_options_universe(db)
    logging.info("Universe: %d tickers", len(tickers))

    inserted = skipped = signalled = 0
    fetch_errors: list[str] = []
    written_signals: list[dict] = []

    for i, ticker in enumerate(tickers):
        try:
            metrics = fetch_options_metrics(ticker, db, snapshot_at)
        except Exception as exc:
            logging.warning("Fetch failed for %s: %s", ticker, exc)
            fetch_errors.append(ticker)
            skipped += 1
            time.sleep(0.3)
            continue

        if metrics is None:
            skipped += 1
            if i % 20 == 0:
                logging.info("Progress: %d/%d (skipped=%d)", i, len(tickers), skipped)
            time.sleep(0.3)
            continue

        signal_type, score, reason = classify_signal(metrics)

        # Only write rows that have a signal (keeps the table lean)
        if signal_type is None:
            time.sleep(0.3)
            continue

        row = OptionsSignal(
            ticker          = ticker,
            snapshot_at     = snapshot_at,
            price           = metrics["price"],
            price_change_1d = metrics["price_change_1d"],
            rsi_14          = metrics["rsi_14"],
            pcr             = metrics["pcr"],
            pcr_label       = metrics["pcr_label"],
            put_volume      = metrics["put_volume"],
            call_volume     = metrics["call_volume"],
            avg_iv          = metrics["avg_iv"],
            iv_rank         = metrics["iv_rank"],
            total_oi        = metrics["total_oi"],
            volume_oi_ratio = metrics["volume_oi_ratio"],
            signal_type     = signal_type,
            signal_score    = score,
            signal_reason   = reason,
            executed        = False,
            created_at      = datetime.now(timezone.utc).replace(tzinfo=None),
        )

        try:
            db.merge(row)
            inserted += 1
            signalled += 1
            written_signals.append({
                "ticker":       ticker,
                "signal_type":  signal_type,
                "signal_score": score,
                "rsi_14":       metrics["rsi_14"],
                "pcr":          metrics["pcr"],
                "pcr_label":    metrics["pcr_label"],
                "iv_rank":      metrics["iv_rank"],
            })
        except Exception as exc:
            logging.warning("DB merge failed for %s: %s", ticker, exc)
            db.rollback()
            skipped += 1

        if i % 20 == 0:
            logging.info("Progress: %d/%d (signals=%d)", i, len(tickers), signalled)
        time.sleep(0.3)

    db.commit()
    db.close()

    if fetch_errors:
        logging.info("Fetch errors for %d tickers: %s", len(fetch_errors), fetch_errors)

    logging.info(
        "Done — %d signals written, %d tickers skipped (dry_run=%s)",
        inserted, skipped, DRY_RUN,
    )

    # Emit a structured error that Cloud Logging → Cloud Monitoring can alert on.
    # Filter: severity=ERROR AND jsonPayload.message="options_screener_zero_signals"
    if signalled == 0 and not DRY_RUN:
        logging.error(json.dumps({
            "severity":      "ERROR",
            "message":       "options_screener_zero_signals",
            "ticker_count":  len(tickers),
            "fetch_errors":  len(fetch_errors),
        }))

    if not DRY_RUN and written_signals:
        top = sorted(written_signals, key=lambda x: x["signal_score"], reverse=True)
        _notify_push(db)
        _notify_telegram(top)


if __name__ == "__main__":
    main()
