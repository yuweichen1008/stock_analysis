"""
Options Snipe — monitors US stock prices and auto-places Moomoo options orders
when a ticker moves more than SNIPE_THRESHOLD% within SNIPE_WINDOW_MIN minutes.

Env vars:
  SNIPE_TICKERS      comma-separated tickers to watch (e.g. "AAPL,TSLA,NVDA")
  SNIPE_THRESHOLD    % move threshold, default 5.0
  SNIPE_WINDOW_MIN   rolling window in minutes, default 5
  SNIPE_QTY          contracts per order, default 1
  SNIPE_MAX_PREMIUM  max ask price willing to pay per contract, default 500
  SNIPE_DRY_RUN      true = log only, false = place real orders (default true)
  TELEGRAM_BOT_TOKEN bot token for alerts
  INTERNAL_API_SECRET guards Oracle API broker endpoint
  ORACLE_API_BASE    Oracle API base URL (default http://localhost:8000)
  MOOMOO_PORT        Moomoo OpenD port (default 11111)
  MOOMOO_TRADE_ENV   SIMULATE or REAL (default SIMULATE)

Usage:
  SNIPE_DRY_RUN=true python options_snipe.py
  SNIPE_DRY_RUN=false SNIPE_TICKERS=AAPL,NVDA python options_snipe.py
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from collections import deque
from datetime import datetime, timedelta, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

TICKERS       = [t.strip().upper() for t in os.getenv("SNIPE_TICKERS", "AAPL,TSLA,NVDA,MSFT,SPY").split(",") if t.strip()]
THRESHOLD_PCT = float(os.getenv("SNIPE_THRESHOLD",  "5.0"))
WINDOW_MIN    = int(os.getenv("SNIPE_WINDOW_MIN",   "5"))
SNIPE_QTY     = int(os.getenv("SNIPE_QTY",          "1"))
MAX_PREMIUM   = float(os.getenv("SNIPE_MAX_PREMIUM", "500"))
DRY_RUN       = os.getenv("SNIPE_DRY_RUN", "true").lower() != "false"
POLL_SECONDS  = 60   # price refresh cadence

TG_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN",   "")
INTERNAL_KEY = os.getenv("INTERNAL_API_SECRET",  "")
API_BASE     = os.getenv("ORACLE_API_BASE", "http://localhost:8000")

# cooldown: skip a ticker for N minutes after firing to avoid repeat orders
COOLDOWN_MIN = 30


def _is_market_hours() -> bool:
    """Return True if current UTC time is within US regular session (13:30–20:00 UTC)."""
    now = datetime.now(timezone.utc)
    if now.weekday() >= 5:
        return False
    t = (now.hour, now.minute)
    return (13, 30) <= t < (20, 0)


# ── Price fetching ────────────────────────────────────────────────────────────

def _fetch_prices(tickers: list[str]) -> dict[str, float]:
    """Fetch latest prices via yfinance. Returns {ticker: price}."""
    try:
        import yfinance as yf
        if not tickers:
            return {}
        data = yf.download(
            " ".join(tickers),
            period="1d",
            interval="1m",
            progress=False,
            auto_adjust=True,
        )
        prices: dict[str, float] = {}
        if len(tickers) == 1:
            close = data["Close"]
            if not close.empty:
                prices[tickers[0]] = float(close.iloc[-1])
        else:
            for t in tickers:
                try:
                    col = data["Close"][t]
                    if not col.empty:
                        prices[t] = float(col.dropna().iloc[-1])
                except (KeyError, IndexError):
                    pass
        return prices
    except Exception as exc:
        logger.warning("Price fetch error: %s", exc)
        return {}


# ── Options chain ─────────────────────────────────────────────────────────────

def _get_nearest_otm_contract(ticker: str, direction: str) -> dict | None:
    """
    Pick nearest OTM contract for the given direction ('up'=CALL, 'down'=PUT).
    Uses yfinance options to avoid Moomoo dependency for selection.
    """
    try:
        import yfinance as yf
        opt_type = "calls" if direction == "up" else "puts"
        yfobj = yf.Ticker(ticker)
        exps = yfobj.options
        if not exps:
            return None

        # Pick nearest expiry at least 5 days out (avoid gamma risk on same-day)
        today = datetime.now(timezone.utc).date()
        target_exp = None
        for exp in exps:
            exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
            if (exp_date - today).days >= 5:
                target_exp = exp
                break

        if not target_exp:
            return None

        chain = yfobj.option_chain(target_exp)
        df = getattr(chain, opt_type)
        if df is None or df.empty:
            return None

        price = _fetch_prices([ticker]).get(ticker)
        if not price:
            return None

        # Nearest OTM: first strike above spot (calls) or below spot (puts)
        if direction == "up":
            otm = df[df["strike"] > price].sort_values("strike").head(1)
        else:
            otm = df[df["strike"] < price].sort_values("strike", ascending=False).head(1)

        if otm.empty:
            return None

        row = otm.iloc[0]
        return {
            "ticker":     ticker,
            "type":       "CALL" if direction == "up" else "PUT",
            "strike":     float(row["strike"]),
            "expiry":     target_exp,
            "ask":        float(row["ask"]) if row["ask"] > 0 else float(row["lastPrice"]),
            "iv":         float(row.get("impliedVolatility", 0)),
            # Moomoo options code: US.TICKER{YYMMDD}{C|P}{8-digit-strike*1000}
            "moomoo_code": _build_moomoo_code(ticker, target_exp, direction, float(row["strike"])),
        }
    except Exception as exc:
        logger.warning("Options chain error for %s: %s", ticker, exc)
        return None


def _build_moomoo_code(ticker: str, expiry: str, direction: str, strike: float) -> str:
    """Build Moomoo options code e.g. US.AAPL250117C00150000"""
    date_part  = expiry[2:4] + expiry[5:7] + expiry[8:10]  # YYMMDD
    side_char  = "C" if direction == "up" else "P"
    strike_int = int(round(strike * 1000))
    return f"US.{ticker.upper()}{date_part}{side_char}{strike_int:08d}"


# ── Order placement ───────────────────────────────────────────────────────────

def _place_order_via_api(contract: dict, qty: int, price: float) -> bool:
    """POST to Oracle broker API to place the options order."""
    if DRY_RUN:
        logger.info("[DRY RUN] would place %d × %s @ %.2f", qty, contract["moomoo_code"], price)
        return True
    try:
        payload = json.dumps({
            "ticker":        contract["moomoo_code"],
            "side":          "buy",
            "qty":           qty,
            "limit_price":   round(price * 1.02, 2),  # 2% above ask for fill probability
            "market":        "US",
            "signal_source": "options_snipe",
        }).encode()
        req = urllib.request.Request(
            f"{API_BASE}/api/broker/order",
            data=payload,
            headers={
                "Content-Type":      "application/json",
                "X-Internal-Secret": INTERNAL_KEY,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            logger.info("Order placed: %s", result.get("message"))
            return True
    except Exception as exc:
        logger.error("Order placement failed: %s", exc)
        return False


# ── Telegram alert ────────────────────────────────────────────────────────────

def _send_telegram(msg: str) -> None:
    if not TG_TOKEN:
        return
    try:
        from api.db import Subscriber, SessionLocal as SL
        sub_db = SL()
        subs = sub_db.query(Subscriber).filter(Subscriber.active == True).all()  # noqa: E712
        sub_db.close()
        for sub in subs:
            try:
                payload = json.dumps({"chat_id": sub.telegram_id, "text": msg, "parse_mode": "Markdown"}).encode()
                req = urllib.request.Request(
                    f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                urllib.request.urlopen(req, timeout=10)
            except Exception as exc:
                logger.warning("Telegram send failed for %s: %s", sub.telegram_id, exc)
    except Exception as exc:
        logger.warning("Telegram dispatch error: %s", exc)


def _alert_and_snipe(ticker: str, direction: str, move_pct: float, current_price: float) -> None:
    arrow    = "📈" if direction == "up" else "📉"
    side_str = "CALL" if direction == "up" else "PUT"

    contract = _get_nearest_otm_contract(ticker, direction)
    if not contract:
        logger.warning("No suitable options contract found for %s %s", ticker, side_str)
        msg = (
            f"{arrow} *[Snipe Alert — No Contract]* ${ticker}\n"
            f"Moved {move_pct:+.2f}% → ${current_price:.2f}\n"
            f"No suitable {side_str} contract found."
        )
        _send_telegram(msg)
        return

    if contract["ask"] > MAX_PREMIUM:
        logger.info("Premium %.2f > MAX_PREMIUM %.2f — skipping order", contract["ask"], MAX_PREMIUM)
        msg = (
            f"{arrow} *[Snipe Alert — Premium Too High]* ${ticker}\n"
            f"Moved {move_pct:+.2f}% → ${current_price:.2f}\n"
            f"{side_str} {contract['strike']} exp {contract['expiry']} ask=${contract['ask']:.2f} > max ${MAX_PREMIUM:.0f}"
        )
        _send_telegram(msg)
        return

    placed = _place_order_via_api(contract, SNIPE_QTY, contract["ask"])

    msg = (
        f"{arrow} *[Option Snipe {'🟢 PLACED' if placed else '🔴 FAILED'}]* ${ticker}\n"
        f"Triggered: {move_pct:+.2f}% in {WINDOW_MIN}min → ${current_price:.2f}\n"
        f"Order: {SNIPE_QTY}× {side_str} strike=${contract['strike']} exp={contract['expiry']}\n"
        f"Ask=${contract['ask']:.2f}  IV={contract['iv']*100:.0f}%\n"
        f"Code: `{contract['moomoo_code']}`\n"
        f"{'⚠️ DRY RUN — no real order placed' if DRY_RUN else ''}"
    )
    _send_telegram(msg)
    logger.info("Snipe processed for %s: %s", ticker, msg.replace("*", "").replace("`", ""))


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    logger.info(
        "Option Snipe starting — tickers=%s threshold=%.1f%% window=%dmin qty=%d dry_run=%s",
        TICKERS, THRESHOLD_PCT, WINDOW_MIN, SNIPE_QTY, DRY_RUN,
    )
    if DRY_RUN:
        logger.info("DRY RUN mode — orders will be logged but NOT placed")

    # price_history[ticker] = deque of (timestamp, price)
    price_history: dict[str, deque] = {t: deque() for t in TICKERS}
    # cooldown[ticker] = datetime until which we suppress re-firing
    cooldown: dict[str, datetime] = {}

    while True:
        now = datetime.now(timezone.utc)

        if not _is_market_hours():
            logger.info("Outside market hours — sleeping 5 min")
            time.sleep(300)
            continue

        prices = _fetch_prices(TICKERS)

        for ticker in TICKERS:
            price = prices.get(ticker)
            if price is None:
                continue

            # Append to history and trim old entries
            price_history[ticker].append((now, price))
            cutoff = now - timedelta(minutes=WINDOW_MIN)
            while price_history[ticker] and price_history[ticker][0][0] < cutoff:
                price_history[ticker].popleft()

            # Need at least 2 data points
            if len(price_history[ticker]) < 2:
                continue

            # Check cooldown
            if cooldown.get(ticker) and now < cooldown[ticker]:
                continue

            baseline_price = price_history[ticker][0][1]
            if baseline_price <= 0:
                continue

            move_pct = ((price - baseline_price) / baseline_price) * 100

            if abs(move_pct) >= THRESHOLD_PCT:
                direction = "up" if move_pct > 0 else "down"
                logger.info(
                    "SNIPE TRIGGER: %s moved %+.2f%% (%.2f → %.2f) in %dmin",
                    ticker, move_pct, baseline_price, price, WINDOW_MIN,
                )
                _alert_and_snipe(ticker, direction, move_pct, price)
                # Set cooldown to avoid repeated triggers
                cooldown[ticker] = now + timedelta(minutes=COOLDOWN_MIN)

        logger.debug("Poll complete — sleeping %ds", POLL_SECONDS)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
