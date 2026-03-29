"""
BrokerManager — aggregates data across all configured broker accounts.

Only brokers with credentials present in the environment are loaded.
Each broker is connected lazily when a report method is first called.
"""

import logging
import pandas as pd
from typing import List

from brokers.base import BrokerClient

logger = logging.getLogger(__name__)

# Max holdings to show per broker before truncating
_MAX_POSITIONS = 20
_MAX_ORDERS    = 15


class BrokerManager:
    """
    Discovers which brokers are configured (env vars set), connects them,
    and provides Telegram-ready Markdown reports for positions, balance, and orders.
    """

    def __init__(self):
        self._clients: List[BrokerClient] = []
        self._connected = False

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _load_clients(self) -> List[BrokerClient]:
        """Instantiate client objects for every broker that has credentials."""
        clients = []
        try:
            from brokers.ibkr import IBKRClient
            if IBKRClient.is_configured():
                clients.append(IBKRClient())
                logger.info("BrokerManager: IBKR enabled")
        except ImportError:
            logger.debug("ib_insync not installed — IBKR skipped")

        try:
            from brokers.moomoo import MoomooClient
            if MoomooClient.is_configured():
                clients.append(MoomooClient())
                logger.info("BrokerManager: Moomoo enabled")
        except ImportError:
            logger.debug("moomoo-api not installed — Moomoo skipped")

        try:
            from brokers.robinhood import RobinhoodClient
            if RobinhoodClient.is_configured():
                clients.append(RobinhoodClient())
                logger.info("BrokerManager: Robinhood enabled")
        except ImportError:
            logger.debug("robin_stocks not installed — Robinhood skipped")

        return clients

    def connect_all(self):
        """Connect to all configured brokers. Failures are logged and skipped."""
        if self._connected:
            return
        self._clients = self._load_clients()
        active = []
        for c in self._clients:
            if c.connect():
                active.append(c)
            else:
                logger.warning("%s: connection failed — skipping", c.name)
        self._clients  = active
        self._connected = True

    def disconnect_all(self):
        for c in self._clients:
            try:
                c.disconnect()
            except Exception:
                pass
        self._clients  = []
        self._connected = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_connected(self):
        if not self._connected:
            self.connect_all()

    def _no_brokers_msg(self) -> str:
        return (
            "⚠️ *No brokers connected*\n\n"
            "Configure at least one broker in `.env`:\n"
            "• IBKR: set `IBKR_PORT`\n"
            "• Moomoo: set `MOOMOO_PORT`\n"
            "• Robinhood: set `ROBINHOOD_USERNAME` + `ROBINHOOD_PASSWORD`"
        )

    # ------------------------------------------------------------------
    # Aggregated data access
    # ------------------------------------------------------------------

    def get_all_positions(self) -> pd.DataFrame:
        """
        Return merged positions DataFrame across all connected brokers.
        Adds a 'broker' column. Columns: broker, ticker, qty, avg_cost, mkt_value, pnl.
        """
        self._ensure_connected()
        frames = []
        for c in self._clients:
            df = c.get_positions()
            if not df.empty:
                df = df.copy()
                df.insert(0, "broker", c.name)
                frames.append(df)
        if not frames:
            return pd.DataFrame(columns=["broker", "ticker", "qty", "avg_cost", "mkt_value", "pnl"])
        return pd.concat(frames, ignore_index=True)

    def get_all_balances(self) -> list:
        """Return list of {broker_name, **balance_dict} for each connected broker."""
        self._ensure_connected()
        results = []
        for c in self._clients:
            b = c.get_balance()
            if b:
                results.append({"broker": c.name, **b})
        return results

    def connected_broker_names(self) -> list:
        """Return list of broker names that are currently connected."""
        self._ensure_connected()
        return [c.name for c in self._clients]

    def place_order(
        self,
        broker_name: str,
        ticker: str,
        side: str,
        qty: float,
        order_type: str = "MARKET",
        limit_price: float = 0.0,
        algo: str = "DMA",
    ) -> dict:
        """
        Route an order to the named broker.
        Returns the broker's place_order() result dict.
        """
        self._ensure_connected()
        for c in self._clients:
            if c.name == broker_name:
                return c.place_order(ticker, side, qty, order_type, limit_price, algo)
        return {
            "success":  False,
            "order_id": "",
            "message":  f"Broker '{broker_name}' not connected or not configured",
        }

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------

    def balance_report(self) -> str:
        """Return a Markdown string showing account cash + net value per broker."""
        self._ensure_connected()
        if not self._clients:
            return self._no_brokers_msg()

        lines = ["💰 *Account Balance*", ""]
        for c in self._clients:
            b = c.get_balance()
            if not b:
                lines.append(f"*{c.name}*: ⚠️ could not fetch balance")
                continue
            cur   = b.get("currency", "")
            cash  = b.get("cash",          0)
            total = b.get("total_value",   0)
            upnl  = b.get("unrealized_pnl", 0)
            pnl_sign = "+" if upnl >= 0 else ""
            lines += [
                f"*{c.name}* ({cur})",
                f"  Net Value : {cur} {total:,.2f}",
                f"  Cash      : {cur} {cash:,.2f}",
                f"  Unrealized: {pnl_sign}{upnl:,.2f}",
                "",
            ]
        return "\n".join(lines).strip()

    def positions_report(self) -> str:
        """Return a Markdown string listing all open positions across brokers."""
        self._ensure_connected()
        if not self._clients:
            return self._no_brokers_msg()

        lines = ["📋 *Open Positions*", ""]
        any_positions = False
        for c in self._clients:
            df = c.get_positions()
            if df.empty:
                lines.append(f"*{c.name}*: no open positions")
                lines.append("")
                continue
            any_positions = True
            df = df.head(_MAX_POSITIONS)
            lines.append(f"*{c.name}* — {len(df)} holding(s)")
            for _, r in df.iterrows():
                pnl      = float(r.get("pnl", 0))
                pnl_sign = "+" if pnl >= 0 else ""
                lines.append(
                    f"  {r['ticker']:>6}  qty {r['qty']:.0f}  "
                    f"avg {r['avg_cost']:.2f}  "
                    f"val {r['mkt_value']:.0f}  "
                    f"PnL {pnl_sign}{pnl:.0f}"
                )
            if len(c.get_positions()) > _MAX_POSITIONS:
                lines.append(f"  …and {len(c.get_positions()) - _MAX_POSITIONS} more")
            lines.append("")

        if not any_positions:
            lines.append("_No open positions across all connected brokers._")
        return "\n".join(lines).strip()

    def orders_report(self, days: int = 7) -> str:
        """Return a Markdown string of recent orders across brokers."""
        self._ensure_connected()
        if not self._clients:
            return self._no_brokers_msg()

        lines = [f"📝 *Orders — last {days} days*", ""]
        any_orders = False
        for c in self._clients:
            df = c.get_orders(days=days)
            if df.empty:
                lines.append(f"*{c.name}*: no recent orders")
                lines.append("")
                continue
            any_orders = True
            df = df.sort_values("date", ascending=False).head(_MAX_ORDERS)
            lines.append(f"*{c.name}*")
            for _, r in df.iterrows():
                side_icon = "🟢" if str(r.get("side", "")).upper() == "BUY" else "🔴"
                lines.append(
                    f"  {side_icon} {r['date']}  {r['ticker']:>6}  "
                    f"{r['side']}  {r['qty']:.0f} @ {r['price']:.2f}  "
                    f"[{r['status']}]"
                )
            lines.append("")

        if not any_orders:
            lines.append("_No orders found in the selected period._")
        return "\n".join(lines).strip()
