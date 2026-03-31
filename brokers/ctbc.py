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
import sys
import time
from io import StringIO
from pathlib import Path
from datetime import datetime, timedelta

# Support both `python brokers/ctbc.py` (direct) and `from brokers.ctbc import ...` (package)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from brokers.base import BrokerClient

logger = logging.getLogger(__name__)

_BASE_URL     = "https://www.win168.com.tw/NCTSWeb"
_LOGIN_URL    = f"{_BASE_URL}/"
_CAPTCHA_URL  = f"{_BASE_URL}/Login/GetImage/1"
_PROFILE_DIR  = Path(__file__).parent / ".ctbc_profile"  # persistent browser profile

# ── Nav-menu text to click for each route key ──────────────────────────────────
# Tried in order; first visible match wins.
_NAV_TEXTS = {
    "inventory":    ["庫存查詢", "庫存", "持股查詢", "庫存明細"],
    "today_orders": ["今日委託", "當日委託", "委託查詢", "委託明細"],
    "history":      ["歷史委託", "委託歷史", "歷史查詢"],
    "balance":      ["帳務查詢", "帳務", "資產查詢", "帳戶資訊"],
    "buy":          ["買進下單", "買進", "買入下單"],
    "sell":         ["賣出下單", "賣出", "賣出委託"],
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
        self._id        = os.getenv("CTBC_ID",       "")
        self._password  = os.getenv("CTBC_PASSWORD",  "")
        self._headless  = os.getenv("CTBC_HEADLESS",  "true").lower() != "false"
        self._dry_run   = os.getenv("CTBC_DRY_RUN",   "true").lower() != "false"
        self._pw        = None
        self._browser   = None
        self._page      = None
        self._logged_in = False
        self._routes: dict[str, str] = {}   # discovered post-login URLs

    # ──────────────────────────────────────────────────────────────────────────
    # Connection / login
    # ──────────────────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        if not self._id or not self._password:
            logger.error("CTBC: CTBC_ID or CTBC_PASSWORD not set in .env")
            return False
        try:
            from playwright.sync_api import sync_playwright
            self._pw = sync_playwright().start()

            # Persistent context = full browser profile saved to disk.
            # On second run the session is usually still live → no re-login needed.
            _PROFILE_DIR.mkdir(exist_ok=True)
            _ctx_kwargs = dict(
                headless=self._headless,
                locale="zh-TW",
                timezone_id="Asia/Taipei",
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            try:
                # Prefer system Chrome — closer fingerprint to a real browser
                ctx = self._pw.chromium.launch_persistent_context(
                    str(_PROFILE_DIR), channel="chrome", **_ctx_kwargs
                )
            except Exception:
                # Fall back to bundled Chromium if Chrome isn't installed
                ctx = self._pw.chromium.launch_persistent_context(
                    str(_PROFILE_DIR), **_ctx_kwargs
                )

            self._browser = None   # persistent context owns the browser lifecycle
            self._page    = ctx.new_page()

            # Stealth: patch navigator.webdriver + ~20 other automation tells
            try:
                from playwright_stealth import stealth
                stealth(self._page)
                logger.debug("CTBC: stealth patches applied")
            except ImportError:
                logger.debug("playwright-stealth not installed — run: pip install playwright-stealth")

            # Try navigating — persistent profile may still have a live session
            self._page.goto(_LOGIN_URL, wait_until="domcontentloaded", timeout=15000)
            if self._is_logged_in():
                logger.info("CTBC: session restored from persistent profile")
                self._logged_in = True
                self._discover_routes()
                return True

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
                time.sleep(1)   # let SPA routing settle

                # Handle intermediate pages in the login flow
                # (CertCheck, system notices, IP confirmations, etc.)
                self._click_through_login_flow()

                if self._is_logged_in():
                    # Persistent context auto-saves the session to _PROFILE_DIR
                    self._logged_in = True
                    logger.info("CTBC: login successful — landed on %s", page.url)
                    self._discover_routes()
                    return True

                # Wrong CAPTCHA or wrong credentials
                err_sel = ".alert, .error, #errMsg, [class*='error'], [class*='alert']"
                err = page.locator(err_sel).first
                try:
                    if err.is_visible(timeout=2000):
                        logger.warning("CTBC login error: %s", err.inner_text())
                except Exception:
                    pass
                time.sleep(1)

            except Exception as e:
                logger.warning("CTBC login attempt %d failed: %s", attempt + 1, e)

        logger.error("CTBC: login failed after 3 attempts")
        return False

    def _click_through_login_flow(self):
        """
        After the initial credential submit some NCTS deployments show
        intermediate pages (CertCheck, system notices, IP/device confirmation).
        Try to click them away; give up after 5 rounds.
        """
        page = self._page
        _CONFIRM_SELS = [
            "button:has-text('確認')",   "button:has-text('確定')",
            "button:has-text('繼續')",   "button:has-text('同意')",
            "button:has-text('下一步')", "button:has-text('登入')",
            "input[type='submit']",       "a.btn:has-text('確認')",
            "#btnConfirm", "#btnContinue", "#btnOk", "#btnNext",
        ]
        for round_ in range(5):
            url = page.url
            if "/Login/" not in url:
                return   # out of login flow — done
            logger.info("CTBC: intermediate page %d — %s", round_ + 1, url)
            # Log page title + first 400 chars of body text to help diagnose
            try:
                title = page.title()
                snippet = page.locator("body").inner_text()[:400].replace("\n", " ")
                logger.info("  title=%s  text=%s…", title, snippet)
            except Exception:
                pass

            clicked = False
            for sel in _CONFIRM_SELS:
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=500):
                        btn.click()
                        page.wait_for_load_state("domcontentloaded", timeout=10000)
                        time.sleep(0.5)
                        clicked = True
                        break
                except Exception:
                    continue

            if not clicked:
                # No button — wait briefly for auto-redirect
                time.sleep(2)

    def _is_logged_in(self) -> bool:
        """True if current page is the post-login dashboard (not any login step)."""
        try:
            url = self._page.url
            # Any /Login/ subpath = still in auth flow
            if "/Login/" in url:
                return False
            # Base NCTSWeb URL with no subpath (SPA may stay here with form gone)
            if url.rstrip("/") in (_LOGIN_URL.rstrip("/"), _BASE_URL.rstrip("/")):
                try:
                    return not self._page.locator("#loginBtn").is_visible(timeout=1500)
                except Exception:
                    return False
            # Any other /NCTSWeb/ path = logged in
            return "/NCTSWeb/" in url
        except Exception:
            return False

    def _discover_routes(self):
        """
        Scan nav links on the post-login page to build self._routes.
        Stores absolute URLs so _nav() can go directly without guessing.
        """
        self._routes = {}
        try:
            time.sleep(0.5)
            links = self._page.locator("a[href]").all()
            for link in links:
                try:
                    href = (link.get_attribute("href") or "").strip()
                    text = link.inner_text().strip()
                    if not href or href in ("#", "/") or href.startswith("javascript"):
                        continue
                    # Make absolute
                    if href.startswith("http"):
                        abs_url = href
                    elif href.startswith("/"):
                        abs_url = f"https://www.win168.com.tw{href}"
                    else:
                        abs_url = f"{_BASE_URL}/{href.lstrip('/')}"

                    for key, keywords in _NAV_TEXTS.items():
                        if key not in self._routes and any(kw in text for kw in keywords):
                            self._routes[key] = abs_url
                            break
                except Exception:
                    continue
            logger.info("CTBC: discovered routes: %s", self._routes)
        except Exception as e:
            logger.warning("CTBC: route discovery failed: %s", e)

    def _nav(self, route_key: str) -> bool:
        """
        Navigate to a named section.  Strategy (in order):
          1. Go to discovered URL directly (fast path)
          2. Click a nav-menu link matching known Chinese text labels
          3. Re-login once, then retry strategies 1 & 2
        """
        # ── Strategy 1: use previously discovered URL ──────────────────────────
        url = self._routes.get(route_key)
        if url:
            try:
                self._page.goto(url, wait_until="domcontentloaded", timeout=20000)
                time.sleep(0.5)
                if self._is_logged_in():
                    return True
            except Exception:
                pass

        # ── Strategy 2: click nav-menu text ────────────────────────────────────
        for text in _NAV_TEXTS.get(route_key, []):
            try:
                sel = (
                    f"a:has-text('{text}'), "
                    f"li:has-text('{text}'), "
                    f"[role='menuitem']:has-text('{text}'), "
                    f"span:has-text('{text}')"
                )
                el = self._page.locator(sel).first
                if el.is_visible(timeout=2000):
                    el.click()
                    self._page.wait_for_load_state("domcontentloaded", timeout=10000)
                    time.sleep(0.5)
                    if self._is_logged_in():
                        # Remember for next call
                        self._routes[route_key] = self._page.url
                        return True
            except Exception:
                continue

        # ── Strategy 3: session expired — re-login once ───────────────────────
        logger.warning("CTBC: cannot navigate to '%s' — re-logging in", route_key)
        if not self._do_login():
            return False
        # After re-login, try click-nav only (routes may have been refreshed)
        for text in _NAV_TEXTS.get(route_key, []):
            try:
                sel = (
                    f"a:has-text('{text}'), "
                    f"li:has-text('{text}'), "
                    f"[role='menuitem']:has-text('{text}')"
                )
                el = self._page.locator(sel).first
                if el.is_visible(timeout=2000):
                    el.click()
                    self._page.wait_for_load_state("domcontentloaded", timeout=10000)
                    time.sleep(0.5)
                    if self._is_logged_in():
                        self._routes[route_key] = self._page.url
                        return True
            except Exception:
                continue

        logger.error("CTBC: navigation to '%s' failed after re-login", route_key)
        return False

    def disconnect(self):
        try:
            if self._page:
                self._page.context.close()   # closes persistent context (flushes profile)
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
            # Wait for any table to appear
            page.wait_for_selector("table", timeout=10000)
            html = page.content()

            # Use pandas to parse all HTML tables; find the one with stock codes
            try:
                tables = pd.read_html(StringIO(html))
            except Exception:
                tables = []

            for tbl in tables:
                rows = _parse_inventory_table(tbl)
                if rows:
                    return pd.DataFrame(rows)

            # Fallback: Playwright row-by-row (non-standard tables)
            rows = []
            for tr in page.locator("table tbody tr, tr").all():
                cells = [td.inner_text().strip() for td in tr.locator("td").all()]
                if len(cells) < 4:
                    continue
                ticker = next((c for c in cells[:4] if c.isdigit() and len(c) == 4), None)
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
            if not rows:
                logger.debug("CTBC get_positions: no rows — page snippet:\n%s", html[:3000])
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
        if not self._nav("inventory"):
            return {}
        try:
            page = self._page
            page.wait_for_selector("body", timeout=8000)
            text = page.locator("body").inner_text()

            cash  = _extract_amount(text, ["可用餘額", "可動用資金", "現金餘額", "可用資金"])
            total = _extract_amount(text, ["總資產", "資產總值", "淨值", "總市值"])
            upnl  = _extract_amount(text, ["未實現損益", "未實現盈虧", "損益"])

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

        route = "today_orders" if days <= 1 else "history"
        if not self._nav(route):
            return pd.DataFrame()
        try:
            page = self._page
            page.wait_for_selector("table", timeout=10000)
            html = page.content()
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y/%m/%d")

            # Parse via pd.read_html first
            try:
                tables = pd.read_html(StringIO(html))
            except Exception:
                tables = []

            for tbl in tables:
                rows = _parse_orders_table(tbl, cutoff)
                if rows:
                    return pd.DataFrame(rows)

            # Fallback: Playwright row-by-row
            rows = []
            for tr in page.locator("table tbody tr, tr").all():
                cells = [td.inner_text().strip() for td in tr.locator("td").all()]
                if len(cells) < 5:
                    continue
                try:
                    date   = next((c for c in cells[:3] if "/" in c), "")
                    ticker = next((c for c in cells if c.isdigit() and len(c) == 4), "")
                    side   = "BUY" if any(k in " ".join(cells) for k in ["買", "Buy"]) else "SELL"
                    qty    = _num(next((c for c in cells if c.replace(",", "").isdigit() and int(c.replace(",", "")) > 100), "0"))
                    price  = _num(next((c for c in reversed(cells) if _is_price(c)), "0"))
                    status = cells[-1]
                    if date and date < cutoff:
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
            ticker_input = page.locator(
                "input[name*='stock'], input[placeholder*='代號'], input[id*='stock'], "
                "input[name*='Stock'], input[name*='code'], input[id*='code']"
            ).first
            if ticker_input.count():
                ticker_input.fill(ticker)
                ticker_input.press("Tab")
                time.sleep(0.5)

            # Fill quantity
            qty_input = page.locator(
                "input[name*='qty'], input[name*='Qty'], input[placeholder*='數量'], "
                "input[name*='quantity'], input[id*='qty']"
            ).first
            if qty_input.count():
                qty_input.fill(str(int(qty)))

            # Fill price
            if order_type.upper() == "LIMIT" and limit_price > 0:
                price_input = page.locator(
                    "input[name*='price'], input[name*='Price'], input[placeholder*='價格'], "
                    "input[id*='price']"
                ).first
                if price_input.count():
                    price_input.fill(str(limit_price))

            if self._dry_run:
                return {
                    "success":  True,
                    "order_id": "DRY-RUN",
                    "message":  (
                        f"DRY RUN — {side} {qty} x {ticker} @ {limit_price} "
                        "(not submitted). Set CTBC_DRY_RUN=false to submit."
                    ),
                }

            # Click submit button
            submit_btn = page.locator(
                "button[type='submit'], input[type='submit'], "
                "#orderBtn, [id*='submit'], [class*='submit'], "
                "button:has-text('確認'), button:has-text('下單')"
            ).first
            if not submit_btn.count():
                return {"success": False, "order_id": "", "message": "CTBC: submit button not found"}
            submit_btn.click()

            page.wait_for_load_state("domcontentloaded", timeout=10000)
            confirm_text = page.locator("body").inner_text()

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
    # Class helpers
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def is_configured() -> bool:
        return bool(os.getenv("CTBC_ID") and os.getenv("CTBC_PASSWORD"))


# ── Table parsers (used by get_positions / get_orders) ────────────────────────

def _parse_inventory_table(df: pd.DataFrame) -> list[dict]:
    """
    Try to extract inventory rows from a parsed HTML table DataFrame.
    Looks for columns containing 4-digit stock codes.
    """
    rows = []
    try:
        str_df = df.astype(str)
        # Find which column has 4-digit codes
        ticker_col = None
        for col in str_df.columns:
            if str_df[col].str.match(r"^\d{4}$").sum() >= 1:
                ticker_col = col
                break
        if ticker_col is None:
            return []

        cols = list(df.columns)
        t_idx = cols.index(ticker_col)

        for _, row in str_df.iterrows():
            ticker = row[ticker_col]
            if not (ticker.isdigit() and len(ticker) == 4):
                continue
            # Grab numeric columns after ticker
            numerics = []
            for c in cols[t_idx + 1:]:
                v = _num(row[c])
                numerics.append(v)
            if len(numerics) < 2:
                continue
            rows.append({
                "ticker":    ticker,
                "qty":       numerics[0] if len(numerics) > 0 else 0,
                "avg_cost":  numerics[1] if len(numerics) > 1 else 0,
                "mkt_value": numerics[3] if len(numerics) > 3 else 0,
                "pnl":       numerics[4] if len(numerics) > 4 else 0,
            })
    except Exception:
        pass
    return rows


def _parse_orders_table(df: pd.DataFrame, cutoff: str) -> list[dict]:
    """
    Try to extract order rows from a parsed HTML table DataFrame.
    Looks for date + 4-digit ticker columns.
    """
    rows = []
    try:
        str_df = df.astype(str)
        # Find ticker column
        ticker_col = None
        for col in str_df.columns:
            if str_df[col].str.match(r"^\d{4}$").sum() >= 1:
                ticker_col = col
                break
        if ticker_col is None:
            return []

        # Find date column
        date_col = None
        for col in str_df.columns:
            if str_df[col].str.contains(r"\d{4}/\d{2}/\d{2}|\d{3}/\d{2}/\d{2}").any():
                date_col = col
                break

        for _, row in str_df.iterrows():
            ticker = row[ticker_col]
            if not (ticker.isdigit() and len(ticker) == 4):
                continue
            date   = row[date_col] if date_col else ""
            cells  = row.tolist()
            side   = "BUY" if any("買" in str(c) or "Buy" in str(c) for c in cells) else "SELL"
            qty    = _num(next((c for c in cells if str(c).replace(",", "").isdigit()
                                and int(str(c).replace(",", "")) > 100), "0"))
            price  = _num(next((c for c in reversed(cells) if _is_price(str(c))), "0"))
            status = str(cells[-1])
            if date and date < cutoff:
                continue
            rows.append({
                "date": date, "ticker": ticker, "side": side,
                "qty": qty,   "price":  price,  "status": status,
            })
    except Exception:
        pass
    return rows


# ── Generic helpers ───────────────────────────────────────────────────────────

def _num(s: str) -> float:
    """Parse a number string that may contain commas, parentheses (negatives)."""
    s = str(s).replace(",", "").replace(" ", "").replace("+", "")
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def _is_price(s: str) -> bool:
    """Return True if the string looks like a stock price (1–5 digit float)."""
    try:
        v = float(str(s).replace(",", ""))
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
