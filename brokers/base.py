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
    def disconnect(self):
        """Clean up any open connections."""
