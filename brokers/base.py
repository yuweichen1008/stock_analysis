from abc import ABC, abstractmethod
import pandas as pd


class BrokerClient(ABC):
    """
    Abstract base class for all broker integrations.

    Each concrete implementation must provide the same 4 read-only methods so
    BrokerManager can aggregate data across brokers without knowing the details.

    Positions DataFrame schema:
        ticker      str   — exchange symbol (e.g. "AAPL", "2330.TW")
        qty         float — number of shares / units held
        avg_cost    float — average cost per share (in account currency)
        mkt_value   float — current market value
        pnl         float — unrealized P&L

    Orders DataFrame schema:
        date        str   — order date (YYYY-MM-DD)
        ticker      str
        side        str   — "BUY" or "SELL"
        qty         float
        price       float — filled price (or limit price if unfilled)
        status      str   — "FILLED" / "PENDING" / "CANCELLED"
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable broker name shown in Telegram reports."""

    @abstractmethod
    def connect(self) -> bool:
        """
        Attempt to connect to the broker.
        Returns True on success, False on failure (never raises).
        """

    @abstractmethod
    def get_positions(self) -> pd.DataFrame:
        """Return current open positions. Empty DataFrame if none or on error."""

    @abstractmethod
    def get_balance(self) -> dict:
        """
        Return account balance summary.
        Keys: cash (float), total_value (float), unrealized_pnl (float), currency (str).
        Return empty dict on error.
        """

    @abstractmethod
    def get_orders(self, days: int = 7) -> pd.DataFrame:
        """Return orders from the last `days` trading days. Empty DataFrame on error."""

    @abstractmethod
    def place_order(
        self,
        ticker: str,
        side: str,
        qty: float,
        order_type: str = "MARKET",
        limit_price: float = 0.0,
        algo: str = "DMA",
    ) -> dict:
        """
        Place a buy or sell order.

        Parameters
        ----------
        ticker      : exchange symbol (e.g. "AAPL", "2330")
        side        : "BUY" or "SELL"
        qty         : number of shares / units
        order_type  : "MARKET" | "LIMIT" | "STOP"
        limit_price : required for LIMIT and STOP orders
        algo        : execution algorithm — "DMA" | "VWAP" | "TWAP" | "ADAPTIVE"
                      (broker-dependent; unsupported algos fall back to DMA)

        Returns a result dict:
          { "success": bool, "order_id": str, "message": str }
        Never raises — all errors are captured in "message".
        """

    @abstractmethod
    def disconnect(self):
        """Clean up any open connections."""
