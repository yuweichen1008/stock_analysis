"""
Strategy execution layer.

Strategies read signal data produced by the scanner pipelines and can optionally
fire orders through BrokerManager.  Designed to be called from the Streamlit
dashboard on-demand (not as a background daemon).

Available strategies:
  MeanReversionExecutor  — auto-executes all signals above a score threshold
  ManualOrderExecutor    — single-order wrapper for the UI Trading page
"""

from __future__ import annotations

import logging
import os
import pandas as pd
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class OrderIntent:
    """Records a planned or executed order with its result."""
    ticker:      str
    side:        str            # "BUY" or "SELL"
    qty:         float
    order_type:  str            # "MARKET" | "LIMIT" | "STOP"
    limit_price: float
    algo:        str            # "DMA" | "VWAP" | "TWAP" | "ADAPTIVE"
    broker:      str
    strategy:    str
    result:      Optional[dict] = field(default=None)

    @property
    def success(self) -> bool:
        return bool(self.result and self.result.get("success"))

    @property
    def order_id(self) -> str:
        return (self.result or {}).get("order_id", "")

    @property
    def message(self) -> str:
        return (self.result or {}).get("message", "dry-run" if self.result is None else "")


class MeanReversionExecutor:
    """
    Reads the signal CSV produced by taiwan_trending / us_trending and places
    BUY orders for all signal stocks that pass a minimum score threshold.

    Parameters
    ----------
    manager        : BrokerManager instance (already connected)
    broker_name    : which connected broker to route orders to
    min_score      : minimum signal score (0–10) to auto-trade; default 5.0
    qty_per_trade  : fixed shares per order
    order_type     : "MARKET" or "LIMIT" (limit uses current price)
    algo           : execution algorithm string ("DMA" / "VWAP" / "TWAP" / "ADAPTIVE")
    dry_run        : if True, compute intents but do NOT send to broker
    """

    def __init__(
        self,
        manager,
        broker_name:   str,
        min_score:     float = 5.0,
        qty_per_trade: float = 100.0,
        order_type:    str   = "MARKET",
        algo:          str   = "DMA",
        dry_run:       bool  = True,
    ):
        self.manager       = manager
        self.broker_name   = broker_name
        self.min_score     = min_score
        self.qty_per_trade = qty_per_trade
        self.order_type    = order_type
        self.algo          = algo
        self.dry_run       = dry_run

    def run(self, signal_csv_path: str) -> List[OrderIntent]:
        """
        Load signal CSV, filter by min_score, fire orders.

        Returns list of OrderIntent objects:
          - result=None          when dry_run=True
          - result=broker dict   when dry_run=False
        """
        if not os.path.exists(signal_csv_path):
            logger.warning("MeanReversionExecutor: signal file not found: %s", signal_csv_path)
            return []

        df = pd.read_csv(signal_csv_path, dtype={"ticker": str})
        df["score"] = pd.to_numeric(df.get("score", 0), errors="coerce").fillna(0)
        df = df[df["score"] >= self.min_score].sort_values("score", ascending=False)

        logger.info(
            "MeanReversionExecutor: %d signal(s) above score %.1f (dry_run=%s)",
            len(df), self.min_score, self.dry_run,
        )

        intents: List[OrderIntent] = []
        for _, row in df.iterrows():
            intent = OrderIntent(
                ticker      = str(row["ticker"]),
                side        = "BUY",
                qty         = self.qty_per_trade,
                order_type  = self.order_type,
                limit_price = float(row.get("price", 0.0)),
                algo        = self.algo,
                broker      = self.broker_name,
                strategy    = "MeanReversion",
                result      = None,
            )
            if not self.dry_run:
                intent.result = self.manager.place_order(
                    broker_name = self.broker_name,
                    ticker      = intent.ticker,
                    side        = intent.side,
                    qty         = intent.qty,
                    order_type  = intent.order_type,
                    limit_price = intent.limit_price,
                    algo        = intent.algo,
                )
                logger.info("Order %s %s: %s", intent.side, intent.ticker, intent.message)
            intents.append(intent)

        return intents

    def preview(self, signal_csv_path: str) -> pd.DataFrame:
        """
        Return a DataFrame preview of what would be ordered without executing.
        Useful for showing the user a confirm-before-execute table in the UI.
        """
        intents = self.run.__wrapped__(self, signal_csv_path) if hasattr(self.run, "__wrapped__") \
                  else MeanReversionExecutor(
                      self.manager, self.broker_name, self.min_score,
                      self.qty_per_trade, self.order_type, self.algo, dry_run=True,
                  ).run(signal_csv_path)
        rows = [
            {
                "ticker":     i.ticker,
                "side":       i.side,
                "qty":        i.qty,
                "order_type": i.order_type,
                "limit_price": i.limit_price,
                "algo":       i.algo,
                "broker":     i.broker,
            }
            for i in intents
        ]
        return pd.DataFrame(rows)


class ManualOrderExecutor:
    """
    Thin wrapper used by the Trading page to place a single manual order.
    Keeping this separate means the UI imports from strategies, not manager.
    """

    def __init__(self, manager):
        self.manager = manager

    def place(
        self,
        broker_name:  str,
        ticker:       str,
        side:         str,
        qty:          float,
        order_type:   str   = "MARKET",
        limit_price:  float = 0.0,
        algo:         str   = "DMA",
    ) -> OrderIntent:
        """Place a single order and return an OrderIntent with the result populated."""
        result = self.manager.place_order(
            broker_name = broker_name,
            ticker      = ticker,
            side        = side,
            qty         = qty,
            order_type  = order_type,
            limit_price = limit_price,
            algo        = algo,
        )
        return OrderIntent(
            ticker      = ticker,
            side        = side,
            qty         = qty,
            order_type  = order_type,
            limit_price = limit_price,
            algo        = algo,
            broker      = broker_name,
            strategy    = "Manual",
            result      = result,
        )
