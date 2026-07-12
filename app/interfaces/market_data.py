"""Market-data provider interface."""

from __future__ import annotations

from typing import Protocol

from app.schemas import MarketDataSnapshot


class MarketDataError(RuntimeError):
    """Raised when market data cannot be loaded or normalized."""


class MarketDataProvider(Protocol):
    """Interface for fetching market data, intentionally easy to fake in tests."""

    def fetch(self, symbol: str) -> MarketDataSnapshot:
        ...
