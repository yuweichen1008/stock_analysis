"""
Robinhood broker integration via robin_stocks.

robin_stocks uses an unofficial REST API; it does not require a local daemon.
Credentials are authenticated on first use and the session token is cached
automatically at ~/.tokens/robinhood.pickle.

Env vars:
  ROBINHOOD_USERNAME   Robinhood account email
  ROBINHOOD_PASSWORD   Robinhood account password

Note: If MFA is enabled on the account, robin_stocks will prompt interactively
on the first login. After the first successful login the token is cached and
subsequent calls use the stored session (no MFA re-prompt).
"""

import os
import logging
import pandas as pd
from datetime import datetime, timedelta

from brokers.base import BrokerClient

logger = logging.getLogger(__name__)


class RobinhoodClient(BrokerClient):
    """Read-only Robinhood account client using robin_stocks."""

    @property
    def name(self) -> str:
        return "Robinhood"

    def __init__(self):
        self._username = os.getenv("ROBINHOOD_USERNAME", "")
        self._password = os.getenv("ROBINHOOD_PASSWORD", "")
        self._rh       = None
        self._logged_in = False

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        if not self._username or not self._password:
            logger.warning("Robinhood: ROBINHOOD_USERNAME / ROBINHOOD_PASSWORD not set")
            return False
        try:
            import robin_stocks.robinhood as rh
            rh.login(
                username=self._username,
                password=self._password,
                expiresIn=86400,    # 24 h session
                store_session=True,
            )
            self._rh = rh
            self._logged_in = True
            logger.info("Robinhood logged in as %s", self._username)
            return True
        except Exception as e:
            logger.warning("Robinhood connect failed: %s", e)
            self._rh = None
            self._logged_in = False
            return False

    def disconnect(self):
        if self._rh and self._logged_in:
            try:
                self._rh.logout()
            except Exception:
                pass
        self._rh = None
        self._logged_in = False

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    def get_positions(self) -> pd.DataFrame:
        if not self._rh:
            return pd.DataFrame()
        try:
            holdings = self._rh.build_holdings()   # dict keyed by ticker symbol
            rows = []
            for ticker, info in holdings.items():
                qty       = float(info.get("quantity",       0))
                avg_cost  = float(info.get("average_buy_price", 0))
                mkt_value = float(info.get("equity",         0))
                pnl       = float(info.get("equity_change",  0))
                rows.append({
                    "ticker":    ticker,
                    "qty":       qty,
                    "avg_cost":  avg_cost,
                    "mkt_value": mkt_value,
                    "pnl":       pnl,
                })
            return pd.DataFrame(rows) if rows else pd.DataFrame()
        except Exception as e:
            logger.warning("Robinhood get_positions error: %s", e)
            return pd.DataFrame()

    # ------------------------------------------------------------------
    # Balance
    # ------------------------------------------------------------------

    def get_balance(self) -> dict:
        if not self._rh:
            return {}
        try:
            profile = self._rh.load_portfolio_profile()
            if not profile:
                return {}
            total   = float(profile.get("equity",               0))
            cash    = float(profile.get("withdrawable_amount",  0))
            upnl    = float(profile.get("extended_hours_equity", total) or total) - total
            return {"cash": cash, "total_value": total, "unrealized_pnl": upnl, "currency": "USD"}
        except Exception as e:
            logger.warning("Robinhood get_balance error: %s", e)
            return {}

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def get_orders(self, days: int = 7) -> pd.DataFrame:
        if not self._rh:
            return pd.DataFrame()
        try:
            cutoff = datetime.now() - timedelta(days=days)
            all_orders = self._rh.get_all_stock_orders()
            rows = []
            for o in all_orders:
                created = o.get("created_at", "")
                try:
                    order_dt = datetime.fromisoformat(created.replace("Z", "+00:00")).replace(tzinfo=None)
                    if order_dt < cutoff:
                        continue
                except Exception:
                    pass
                executions = o.get("executions", [])
                avg_price  = (
                    float(executions[0]["price"]) if executions
                    else float(o.get("price") or o.get("average_price") or 0)
                )
                rows.append({
                    "date":   created[:10],
                    "ticker": o.get("instrument_symbol") or o.get("symbol", ""),
                    "side":   o.get("side", "").upper(),
                    "qty":    float(o.get("quantity", 0)),
                    "price":  avg_price,
                    "status": o.get("state", "").upper(),
                })
            return pd.DataFrame(rows) if rows else pd.DataFrame()
        except Exception as e:
            logger.warning("Robinhood get_orders error: %s", e)
            return pd.DataFrame()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def is_configured() -> bool:
        """Return True if both username and password env vars are set."""
        return bool(os.getenv("ROBINHOOD_USERNAME") and os.getenv("ROBINHOOD_PASSWORD"))
