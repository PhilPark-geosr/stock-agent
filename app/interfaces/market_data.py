"""Market-data provider interface."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from app.schemas import MarketDataSnapshot


class MarketDataError(RuntimeError):
    """Raised when market data cannot be loaded or normalized."""


class ClosingDataNotReadyError(MarketDataError):
    """Raised when a requested session does not yet have a confirmed daily close."""


class MarketDataProvider(Protocol):
    """Interface for fetching market data, intentionally easy to fake in tests."""

    def fetch(self, symbol: str) -> MarketDataSnapshot:
        ...

    def fetch_close(self, symbol: str, trading_date: date) -> MarketDataSnapshot:
        """Fetch a snapshot whose final record is the requested session close."""
