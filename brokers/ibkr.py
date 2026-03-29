"""
Interactive Brokers integration via ib_insync.

Requirements:
  - TWS or IB Gateway must be running on the host machine
  - API connections must be enabled in TWS (File → Global Configuration → API)
  - Set IBKR_PORT=7497 for paper-trading TWS
  - Set IBKR_PORT=7496 for live TWS
  - Set IBKR_PORT=4002 for live IB Gateway

Env vars:
  IBKR_HOST       default 127.0.0.1
  IBKR_PORT       default 7497  (paper)
  IBKR_CLIENT_ID  default 1
"""

import os
import logging
import pandas as pd
from datetime import datetime, timedelta

from brokers.base import BrokerClient

logger = logging.getLogger(__name__)


class IBKRClient(BrokerClient):
    """Read-only IBKR account client using ib_insync."""

    @property
    def name(self) -> str:
        return "IBKR"

    def __init__(self):
        self._host      = os.getenv("IBKR_HOST", "127.0.0.1")
        self._port      = int(os.getenv("IBKR_PORT", "7497"))
        self._client_id = int(os.getenv("IBKR_CLIENT_ID", "1"))
        self._ib        = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        try:
            from ib_insync import IB
            self._ib = IB()
            self._ib.connect(self._host, self._port, clientId=self._client_id, timeout=10)
            logger.info("IBKR connected on %s:%s", self._host, self._port)
            return True
        except Exception as e:
            logger.warning("IBKR connect failed: %s", e)
            self._ib = None
            return False

    def disconnect(self):
        if self._ib and self._ib.isConnected():
            self._ib.disconnect()
            self._ib = None

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    def get_positions(self) -> pd.DataFrame:
        if not self._ib:
            return pd.DataFrame()
        try:
            rows = []
            for item in self._ib.portfolio():
                rows.append({
                    "ticker":     item.contract.symbol,
                    "qty":        float(item.position),
                    "avg_cost":   float(item.averageCost),
                    "mkt_value":  float(item.marketValue),
                    "pnl":        float(item.unrealizedPNL),
                })
            return pd.DataFrame(rows) if rows else pd.DataFrame()
        except Exception as e:
            logger.warning("IBKR get_positions error: %s", e)
            return pd.DataFrame()

    # ------------------------------------------------------------------
    # Balance
    # ------------------------------------------------------------------

    def get_balance(self) -> dict:
        if not self._ib:
            return {}
        try:
            vals  = {v.tag: v.value for v in self._ib.accountValues() if v.currency in ("BASE", "USD", "")}
            cash  = float(vals.get("TotalCashValue", 0))
            total = float(vals.get("NetLiquidation", 0))
            upnl  = float(vals.get("UnrealizedPnL",  0))
            return {"cash": cash, "total_value": total, "unrealized_pnl": upnl, "currency": "USD"}
        except Exception as e:
            logger.warning("IBKR get_balance error: %s", e)
            return {}

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def get_orders(self, days: int = 7) -> pd.DataFrame:
        if not self._ib:
            return pd.DataFrame()
        try:
            cutoff = datetime.now() - timedelta(days=days)
            rows = []
            for trade in self._ib.trades():
                try:
                    filled_time = trade.log[-1].time if trade.log else None
                    if filled_time and filled_time.replace(tzinfo=None) < cutoff:
                        continue
                    fill = trade.orderStatus
                    avg_px = fill.avgFillPrice or trade.order.lmtPrice or 0
                    rows.append({
                        "date":   filled_time.strftime("%Y-%m-%d") if filled_time else "",
                        "ticker": trade.contract.symbol,
                        "side":   trade.order.action,       # "BUY" / "SELL"
                        "qty":    float(fill.filled or trade.order.totalQuantity),
                        "price":  float(avg_px),
                        "status": fill.status,
                    })
                except Exception:
                    continue
            return pd.DataFrame(rows) if rows else pd.DataFrame()
        except Exception as e:
            logger.warning("IBKR get_orders error: %s", e)
            return pd.DataFrame()

    # ------------------------------------------------------------------
    # Order execution
    # ------------------------------------------------------------------

    def place_order(self, ticker: str, side: str, qty: float,
                    order_type: str = "MARKET", limit_price: float = 0.0,
                    algo: str = "DMA") -> dict:
        if not self._ib:
            return {"success": False, "order_id": "", "message": "IBKR not connected"}
        try:
            from ib_insync import Stock, MarketOrder, LimitOrder, Order, TagValue

            contract = Stock(ticker, "SMART", "USD")
            self._ib.qualifyContracts(contract)

            if order_type == "LIMIT":
                order = LimitOrder(side, qty, limit_price)
            elif order_type == "STOP":
                order = Order()
                order.action        = side
                order.orderType     = "STP"
                order.auxPrice      = limit_price
                order.totalQuantity = qty
            else:
                order = MarketOrder(side, qty)

            # Execution algorithm overlay (IBKR Adaptive Algos)
            if algo == "VWAP":
                order.algoStrategy = "Vwap"
                order.algoParams   = []
            elif algo == "TWAP":
                order.algoStrategy = "Twap"
                order.algoParams   = []
            elif algo == "ADAPTIVE":
                order.algoStrategy = "Adaptive"
                order.algoParams   = [TagValue("adaptivePriority", "Normal")]

            trade = self._ib.placeOrder(contract, order)
            self._ib.sleep(1)   # allow status to populate
            return {
                "success":  True,
                "order_id": str(trade.order.orderId),
                "message":  f"IBKR order placed — status: {trade.orderStatus.status}",
            }
        except Exception as e:
            logger.warning("IBKR place_order error: %s", e)
            return {"success": False, "order_id": "", "message": str(e)}

    # ------------------------------------------------------------------
    # Class-level helpers
    # ------------------------------------------------------------------

    @staticmethod
    def is_configured() -> bool:
        """Return True if at least IBKR_PORT is set (non-empty) in env."""
        return bool(os.getenv("IBKR_PORT"))
