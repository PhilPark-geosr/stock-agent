"""Exchange trading-session contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


@dataclass(frozen=True)
class TradingSession:
    exchange: str
    trading_date: date
    opens_at: datetime
    closes_at: datetime


class TradingCalendar(Protocol):
    def local_date(self, exchange: str, instant: datetime) -> date:
        """Return the exchange-local calendar date for an instant."""

    def session_on(self, exchange: str, trading_date: date) -> TradingSession | None:
        """Return the regular session, or None for a non-trading date."""
