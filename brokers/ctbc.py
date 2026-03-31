"""
CTBC Win168 broker integration via Playwright browser automation.

Automates https://www.win168.com.tw/NCTSWeb/ to:
  - Login (CAPTCHA solved automatically via ddddocr)
  - Fetch inventory / positions
  - Fetch account balance
  - Fetch order history
  - Submit buy / sell orders

Requirements (already in requirements.txt):
  playwright + chromium   →  pip install playwright && playwright install chromium
  ddddocr                 →  pip install ddddocr   (CAPTCHA OCR, no Tesseract needed)

Env vars (.env):
  CTBC_ID          身分證字號 / 使用者帳號
  CTBC_PASSWORD    登入密碼
  CTBC_HEADLESS    true (default) | false  — set false to watch the browser
  CTBC_DRY_RUN     true (default) | false  — set false to actually submit orders
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd

from brokers.base import BrokerClient

logger = logging.getLogger(__name__)

_BASE_URL    = "https://www.win168.com.tw/NCTSWeb"
_LOGIN_URL   = f"{_BASE_URL}/"
_CAPTCHA_URL = f"{_BASE_URL}/Login/GetImage/1"
_COOKIE_FILE = Path(__file__).parent / ".ctbc_session.json"

# ── Known page routes (discovered from NCTS platform) ────────────────────────
# These may need adjustment if CTBC customises the standard NCTS paths.
_ROUTES = {
    "inventory":    f"{_BASE_URL}/Inventory/",         # 庫存查詢
    "today_orders": f"{_BASE_URL}/Order/OrderList/",   # 今日委託
    "history":      f"{_BASE_URL}/Order/HistoryList/", # 歷史委託
    "balance":      f"{_BASE_URL}/Account/",           # 帳務查詢
    "buy":          f"{_BASE_URL}/Trade/Buy/",         # 買進下單
    "sell":         f"{_BASE_URL}/Trade/Sell/",        # 賣出下單
}


def _solve_captcha(image_bytes: bytes) -> str:
    """Use ddddocr to read the 4-digit image CAPTCHA."""
    try:
        import ddddocr
        ocr = ddddocr.DdddOcr(show_ad=False)
        return ocr.classification(image_bytes).strip()
    except Exception as e:
        logger.warning("CAPTCHA OCR failed (%s) — falling back to manual input", e)
        Path("/tmp/ctbc_captcha.png").write_bytes(image_bytes)
        code = input("CAPTCHA saved to /tmp/ctbc_captcha.png — enter code: ").strip()
        return code


class CTBCClient(BrokerClient):
    """
    CTBC Win168 broker client (Playwright-based).

    Usage:
        client = CTBCClient()
        if client.connect():
            positions = client.get_positions()
            balance   = client.get_balance()
            orders    = client.get_orders(days=7)
    """

    @property
    def name(self) -> str:
        return "CTBC"

    def __init__(self):
        self._id       = os.getenv("CTBC_ID",       "")
        self._password = os.getenv("CTBC_PASSWORD",  "")
        self._headless = os.getenv("CTBC_HEADLESS",  "true").lower() != "false"
        self._dry_run  = os.getenv("CTBC_DRY_RUN",   "true").lower() != "false"
        self._pw       = None
        self._browser  = None
        self._page     = None
        self._logged_in = False

    # ──────────────────────────────────────────────────────────────────────────
    # Connection / login
    # ──────────────────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        if not self._id or not self._password:
            logger.error("CTBC: CTBC_ID or CTBC_PASSWORD not set in .env")
            return False
        try:
            from playwright.sync_api import sync_playwright
            self._pw      = sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=self._headless)
            ctx           = self._browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
            self._page = ctx.new_page()

            # Try loading saved session cookies first
            if _COOKIE_FILE.exists():
                try:
                    cookies = json.loads(_COOKIE_FILE.read_text())
                    ctx.add_cookies(cookies)
                    self._page.goto(_ROUTES["inventory"], wait_until="domcontentloaded", timeout=15000)
                    if self._is_logged_in():
                        logger.info("CTBC: session restored from cookie cache")
                        self._logged_in = True
                        return True
                except Exception:
                    pass

            return self._do_login()
        except Exception as e:
            logger.error("CTBC connect failed: %s", e)
            return False

    def _do_login(self) -> bool:
        """Navigate to login page, fill credentials, solve CAPTCHA, submit."""
        page = self._page
        for attempt in range(3):
            try:
                page.goto(_LOGIN_URL, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_selector("#uid", timeout=10000)

                # Fill credentials
                page.fill("#uid",   self._id)
                page.fill("#uauth", self._password)

                # Solve CAPTCHA
                captcha_bytes = page.request.get(_CAPTCHA_URL).body()
                code = _solve_captcha(captcha_bytes)
                logger.info("CTBC login attempt %d — CAPTCHA: %s", attempt + 1, code)
                page.fill("#vcode", code)

                # Click login (JS-driven button)
                page.click("#loginBtn")
                page.wait_for_load_state("domcontentloaded", timeout=15000)

                if self._is_logged_in():
                    # Persist session cookies
                    cookies = page.context.cookies()
                    _COOKIE_FILE.write_text(json.dumps(cookies, ensure_ascii=False))
                    self._logged_in = True
                    logger.info("CTBC: login successful")
                    return True

                # Wrong CAPTCHA or credentials — check for error message
                err = page.locator(".alert, .error, #errMsg, [class*='error']").first
                if err.is_visible():
                    logger.warning("CTBC login error: %s", err.inner_text())
                time.sleep(1)

            except Exception as e:
                logger.warning("CTBC login attempt %d failed: %s", attempt + 1, e)

        logger.error("CTBC: login failed after 3 attempts")
        return False

    def _is_logged_in(self) -> bool:
        """Return True if the current page looks like a post-login dashboard."""
        url = self._page.url
        # Login page always contains the login form; post-login pages don't
        return "/NCTSWeb/" in url and "#uid" not in url and not self._page.locator("#loginBtn").is_visible()

    def _nav(self, route_key: str) -> bool:
        """Navigate to a route; return False if redirected to login."""
        try:
            self._page.goto(_ROUTES[route_key], wait_until="domcontentloaded", timeout=20000)
            if not self._is_logged_in():
                logger.warning("CTBC: session expired, re-logging in")
                return self._do_login()
            return True
        except Exception as e:
            logger.warning("CTBC nav to %s failed: %s", route_key, e)
            return False

    def disconnect(self):
        try:
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._logged_in = False

    # ──────────────────────────────────────────────────────────────────────────
    # Positions / inventory
    # ──────────────────────────────────────────────────────────────────────────

    def get_positions(self) -> pd.DataFrame:
        if not self._logged_in:
            return pd.DataFrame()
        if not self._nav("inventory"):
            return pd.DataFrame()
        try:
            page = self._page
            page.wait_for_selector("table, .list-table, [class*='grid']", timeout=10000)
            # NCTS inventory table: ticker | name | qty | avg_cost | market_price | mkt_value | pnl
            rows = []
            for tr in page.locator("table tbody tr").all():
                cells = [td.inner_text().strip() for td in tr.locator("td").all()]
                if len(cells) < 5:
                    continue
                try:
                    # Column order varies; find ticker (4-digit number) in first few cells
                    ticker = next((c for c in cells[:3] if c.isdigit() and len(c) == 4), None)
                    if not ticker:
                        continue
                    i = cells.index(ticker)
                    rows.append({
                        "ticker":    ticker,
                        "qty":       _num(cells[i + 2] if i + 2 < len(cells) else "0"),
                        "avg_cost":  _num(cells[i + 3] if i + 3 < len(cells) else "0"),
                        "mkt_value": _num(cells[i + 5] if i + 5 < len(cells) else "0"),
                        "pnl":       _num(cells[i + 6] if i + 6 < len(cells) else "0"),
                    })
                except Exception:
                    continue

            if not rows:
                # Fallback: try to parse any visible numeric data
                logger.info("CTBC: no rows parsed from standard selectors — page HTML logged")
                logger.debug(page.content()[:2000])

            return pd.DataFrame(rows) if rows else pd.DataFrame(
                columns=["ticker", "qty", "avg_cost", "mkt_value", "pnl"]
            )
        except Exception as e:
            logger.warning("CTBC get_positions error: %s", e)
            return pd.DataFrame()

    # ──────────────────────────────────────────────────────────────────────────
    # Balance
    # ──────────────────────────────────────────────────────────────────────────

    def get_balance(self) -> dict:
        if not self._logged_in:
            return {}
        # Balance is often shown in the inventory page header / account summary
        if not self._nav("inventory"):
            return {}
        try:
            page = self._page
            page.wait_for_selector("body", timeout=8000)
            text = page.locator("body").inner_text()

            # NCTS typically shows: 可用餘額, 股票市值, 總資產
            cash  = _extract_amount(text, ["可用餘額", "可動用資金", "現金餘額"])
            total = _extract_amount(text, ["總資產", "資產總值", "淨值"])
            upnl  = _extract_amount(text, ["未實現損益", "未實現盈虧"])

            return {
                "cash":           cash,
                "total_value":    total or cash,
                "unrealized_pnl": upnl,
                "currency":       "TWD",
                "broker":         "CTBC",
            }
        except Exception as e:
            logger.warning("CTBC get_balance error: %s", e)
            return {}

    # ──────────────────────────────────────────────────────────────────────────
    # Orders
    # ──────────────────────────────────────────────────────────────────────────

    def get_orders(self, days: int = 7) -> pd.DataFrame:
        if not self._logged_in:
            return pd.DataFrame()

        # Try today's orders first, then history
        route = "today_orders" if days <= 1 else "history"
        if not self._nav(route):
            return pd.DataFrame()
        try:
            page = self._page
            page.wait_for_selector("table, .list-table", timeout=10000)
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y/%m/%d")
            rows   = []
            for tr in page.locator("table tbody tr").all():
                cells = [td.inner_text().strip() for td in tr.locator("td").all()]
                if len(cells) < 5:
                    continue
                try:
                    # Typical NCTS order columns: date | ticker | name | side | qty | price | status
                    date   = cells[0] if "/" in cells[0] else ""
                    ticker = next((c for c in cells[1:4] if c.isdigit() and len(c) == 4), "")
                    side   = "BUY" if any(k in " ".join(cells) for k in ["買", "Buy"]) else "SELL"
                    qty    = _num(next((c for c in cells if c.replace(",", "").isdigit() and int(c.replace(",", "")) > 0), "0"))
                    price  = _num(next((c for c in reversed(cells) if _is_price(c)), "0"))
                    status = cells[-1]
                    if date < cutoff:
                        continue
                    rows.append({
                        "date": date, "ticker": ticker, "side": side,
                        "qty": qty,   "price":  price,  "status": status,
                    })
                except Exception:
                    continue
            return pd.DataFrame(rows) if rows else pd.DataFrame(
                columns=["date", "ticker", "side", "qty", "price", "status"]
            )
        except Exception as e:
            logger.warning("CTBC get_orders error: %s", e)
            return pd.DataFrame()

    # ──────────────────────────────────────────────────────────────────────────
    # Order placement
    # ──────────────────────────────────────────────────────────────────────────

    def place_order(self, ticker: str, side: str, qty: float,
                    order_type: str = "LIMIT", limit_price: float = 0.0,
                    algo: str = "DMA") -> dict:
        """
        Place a buy or sell order on Win168.

        dry_run=True (default via CTBC_DRY_RUN env) fills and previews the
        form but does NOT click the final confirm button.
        """
        if not self._logged_in:
            return {"success": False, "order_id": "", "message": "CTBC not logged in"}

        route = "buy" if side.upper() == "BUY" else "sell"
        if not self._nav(route):
            return {"success": False, "order_id": "", "message": "CTBC: navigation failed"}

        try:
            page = self._page
            page.wait_for_selector("input, [class*='order'], form", timeout=10000)

            # Fill ticker (NCTS uses a stock code input field)
            ticker_input = page.locator("input[name*='stock'], input[placeholder*='代號'], input[id*='stock']").first
            if ticker_input.count():
                ticker_input.fill(ticker)
                ticker_input.press("Tab")
                time.sleep(0.5)

            # Fill quantity (usually in lots of 1000 shares)
            qty_input = page.locator("input[name*='qty'], input[name*='Qty'], input[placeholder*='數量']").first
            if qty_input.count():
                qty_input.fill(str(int(qty)))

            # Fill price
            if order_type.upper() == "LIMIT" and limit_price > 0:
                price_input = page.locator("input[name*='price'], input[name*='Price'], input[placeholder*='價格']").first
                if price_input.count():
                    price_input.fill(str(limit_price))

            if self._dry_run:
                return {
                    "success":  True,
                    "order_id": "DRY-RUN",
                    "message":  f"DRY RUN — {side} {qty} x {ticker} @ {limit_price} (not submitted). Set CTBC_DRY_RUN=false to submit.",
                }

            # Click submit button
            submit_btn = page.locator("button[type='submit'], input[type='submit'], #orderBtn, [id*='submit'], [class*='submit']").first
            if not submit_btn.count():
                return {"success": False, "order_id": "", "message": "CTBC: submit button not found"}
            submit_btn.click()

            # Wait for confirmation
            page.wait_for_load_state("domcontentloaded", timeout=10000)
            confirm_text = page.locator("body").inner_text()

            # Look for order ID in confirmation
            import re
            order_id_match = re.search(r"委託序號[：:]\s*(\w+)", confirm_text)
            order_id = order_id_match.group(1) if order_id_match else ""

            return {
                "success":  True,
                "order_id": order_id,
                "message":  f"CTBC order submitted: {side} {qty} x {ticker}",
            }
        except Exception as e:
            logger.warning("CTBC place_order error: %s", e)
            return {"success": False, "order_id": "", "message": str(e)}

    # ──────────────────────────────────────────────────────────────────────────
    # Standalone runner — for quick CLI testing
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def is_configured() -> bool:
        return bool(os.getenv("CTBC_ID") and os.getenv("CTBC_PASSWORD"))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _num(s: str) -> float:
    """Parse a number string that may contain commas, parentheses (negatives)."""
    s = s.replace(",", "").replace(" ", "").replace("+", "")
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def _is_price(s: str) -> bool:
    """Return True if the string looks like a stock price (2–5 digit float)."""
    try:
        v = float(s.replace(",", ""))
        return 1.0 < v < 5000.0
    except (ValueError, TypeError):
        return False


def _extract_amount(text: str, keywords: list[str]) -> float:
    """Find a dollar amount following any of the given keywords in text."""
    import re
    for kw in keywords:
        m = re.search(rf"{kw}[：:\s]*([0-9,]+(?:\.[0-9]+)?)", text)
        if m:
            return _num(m.group(1))
    return 0.0


# ── CLI quick test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    client = CTBCClient()

    print("Connecting to CTBC Win168…")
    if not client.connect():
        print("Login failed. Check CTBC_ID / CTBC_PASSWORD in .env")
        sys.exit(1)

    print("\n── Balance ──────────────────")
    balance = client.get_balance()
    for k, v in balance.items():
        print(f"  {k}: {v}")

    print("\n── Positions ────────────────")
    pos = client.get_positions()
    print(pos.to_string() if not pos.empty else "  (no open positions)")

    print("\n── Orders (last 7 days) ─────")
    orders = client.get_orders(days=7)
    print(orders.to_string() if not orders.empty else "  (no recent orders)")

    client.disconnect()
