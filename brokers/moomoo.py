"""
Moomoo (Futu) broker integration via moomoo-api.

Requirements:
  - OpenD (Futu OpenD daemon) must be running on the host machine
  - Download from: https://www.futunn.com/download/OpenAPI

Env vars:
  MOOMOO_HOST         default 127.0.0.1
  MOOMOO_PORT         default 11111
  MOOMOO_TRADE_ENV    SIMULATE or REAL  (default SIMULATE)
  MOOMOO_UNLOCK_PWD   trading password (required for order queries in REAL mode)
  MOOMOO_MARKET       HK or US         (default US — covers TWS signals via ADR/US-listed)
"""

import os
import logging
import pandas as pd
from datetime import datetime, timedelta

from brokers.base import BrokerClient

logger = logging.getLogger(__name__)


class MoomooClient(BrokerClient):
    """Read-only Moomoo account client using moomoo-api."""

    @property
    def name(self) -> str:
        return "Moomoo"

    def __init__(self):
        self._host       = os.getenv("MOOMOO_HOST",       "127.0.0.1")
        self._port       = int(os.getenv("MOOMOO_PORT",   "11111"))
        self._env_str    = os.getenv("MOOMOO_TRADE_ENV",  "SIMULATE").upper()
        self._unlock_pwd = os.getenv("MOOMOO_UNLOCK_PWD", "")
        self._market     = os.getenv("MOOMOO_MARKET",     "US").upper()
        self._trade_ctx  = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        try:
            import moomoo as ft
            env = ft.TrdEnv.REAL if self._env_str == "REAL" else ft.TrdEnv.SIMULATE

            if self._market == "HK":
                ctx = ft.OpenHKTradeContext(host=self._host, port=self._port)
            else:
                ctx = ft.OpenUSTradeContext(host=self._host, port=self._port)

            # Unlock trade password (required for REAL env order queries)
            if env == ft.TrdEnv.REAL and self._unlock_pwd:
                ret, data = ctx.unlock_trade(self._unlock_pwd)
                if ret != ft.RET_OK:
                    logger.warning("Moomoo unlock_trade failed: %s", data)

            self._trade_ctx = ctx
            self._env       = env
            logger.info("Moomoo connected (%s, %s market)", self._env_str, self._market)
            return True
        except Exception as e:
            logger.warning("Moomoo connect failed: %s", e)
            self._trade_ctx = None
            return False

    def disconnect(self):
        if self._trade_ctx:
            self._trade_ctx.close()
            self._trade_ctx = None

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    def get_positions(self) -> pd.DataFrame:
        if not self._trade_ctx:
            return pd.DataFrame()
        try:
            import moomoo as ft
            ret, data = self._trade_ctx.position_list_query(trd_env=self._env)
            if ret != ft.RET_OK or data is None or data.empty:
                return pd.DataFrame()

            # Moomoo columns: code, stock_name, qty, can_sell_qty, cost_price,
            #                 market_val, pl_val (unrealized P&L)
            df = data.rename(columns={
                "code":       "ticker",
                "qty":        "qty",
                "cost_price": "avg_cost",
                "market_val": "mkt_value",
                "pl_val":     "pnl",
            })
            for col in ["qty", "avg_cost", "mkt_value", "pnl"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
            return df[["ticker", "qty", "avg_cost", "mkt_value", "pnl"]].copy()
        except Exception as e:
            logger.warning("Moomoo get_positions error: %s", e)
            return pd.DataFrame()

    # ------------------------------------------------------------------
    # Balance
    # ------------------------------------------------------------------

    def get_balance(self) -> dict:
        if not self._trade_ctx:
            return {}
        try:
            import moomoo as ft
            ret, data = self._trade_ctx.accinfo_query(trd_env=self._env)
            if ret != ft.RET_OK or data is None or data.empty:
                return {}
            row = data.iloc[0]
            # Moomoo columns: cash, total_assets, market_val, pl_val
            cash  = float(row.get("cash",         0))
            total = float(row.get("total_assets", 0))
            upnl  = float(row.get("pl_val",       0))
            currency = "HKD" if self._market == "HK" else "USD"
            return {"cash": cash, "total_value": total, "unrealized_pnl": upnl, "currency": currency}
        except Exception as e:
            logger.warning("Moomoo get_balance error: %s", e)
            return {}

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def get_orders(self, days: int = 7) -> pd.DataFrame:
        if not self._trade_ctx:
            return pd.DataFrame()
        try:
            import moomoo as ft
            ret, data = self._trade_ctx.order_list_query(trd_env=self._env)
            if ret != ft.RET_OK or data is None or data.empty:
                return pd.DataFrame()

            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            # Moomoo columns: code, trd_side, order_type, order_status,
            #                 qty, dealt_qty, price, create_time
            df = data.copy()
            df = df[df.get("create_time", pd.Series(dtype=str)) >= cutoff] if "create_time" in df else df

            rows = []
            for _, r in df.iterrows():
                side   = str(r.get("trd_side",    "")).upper()
                status = str(r.get("order_status", "")).upper()
                rows.append({
                    "date":   str(r.get("create_time", ""))[:10],
                    "ticker": str(r.get("code",   "")),
                    "side":   "BUY" if "BUY" in side else "SELL",
                    "qty":    float(r.get("dealt_qty", r.get("qty", 0))),
                    "price":  float(r.get("price", 0)),
                    "status": "FILLED" if "FILLED" in status else status,
                })
            return pd.DataFrame(rows) if rows else pd.DataFrame()
        except Exception as e:
            logger.warning("Moomoo get_orders error: %s", e)
            return pd.DataFrame()

    # ------------------------------------------------------------------
    # Order execution
    # ------------------------------------------------------------------

    def place_order(self, ticker: str, side: str, qty: float,
                    order_type: str = "MARKET", limit_price: float = 0.0,
                    algo: str = "DMA") -> dict:
        """
        Place an order via Moomoo OpenD.
        Note: Moomoo does not expose VWAP/TWAP/ADAPTIVE algos via the open API;
        the `algo` parameter is accepted but ignored.
        """
        if not self._trade_ctx:
            return {"success": False, "order_id": "", "message": "Moomoo not connected"}
        try:
            import moomoo as ft

            trd_side = ft.TrdSide.BUY if side.upper() == "BUY" else ft.TrdSide.SELL
            ot_map = {
                "MARKET": ft.OrderType.MARKET,
                "LIMIT":  ft.OrderType.NORMAL,   # NORMAL = limit in Moomoo
                "STOP":   ft.OrderType.STOP,
            }
            ft_order_type = ot_map.get(order_type.upper(), ft.OrderType.MARKET)
            price = limit_price if order_type.upper() in ("LIMIT", "STOP") else 0.0

            if algo not in ("DMA", ""):
                logger.debug("Moomoo: algo '%s' not supported, using default routing", algo)

            ret, data = self._trade_ctx.place_order(
                price=price,
                qty=qty,
                code=ticker,
                trd_side=trd_side,
                order_type=ft_order_type,
                trd_env=self._env,
            )
            if ret != ft.RET_OK:
                return {"success": False, "order_id": "", "message": str(data)}
            order_id = str(data["order_id"].iloc[0]) if not data.empty else ""
            return {"success": True, "order_id": order_id, "message": "Moomoo order placed"}
        except Exception as e:
            logger.warning("Moomoo place_order error: %s", e)
            return {"success": False, "order_id": "", "message": str(e)}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def is_configured() -> bool:
        """Return True if MOOMOO_PORT is set in env (even SIMULATE works)."""
        return bool(os.getenv("MOOMOO_PORT"))
