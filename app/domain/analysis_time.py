"""Time meaning captured with a particular analysis input."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict


class CalendarUnavailable(ValueError):
    pass


@dataclass(frozen=True)
class TradingSession:
    opens_at: datetime
    closes_at: datetime
    source: str


class SessionCalendar(Protocol):
    def session(self, exchange: str, day: date) -> TradingSession | None: ...


class ChartBasis(BaseModel):
    """A daily session date is a calendar label, not a closing instant."""

    model_config = ConfigDict(frozen=True)

    interval: str
    session_date: date | None = None
    source_timezone: str | None = None
    finality: Literal["unknown"] = "unknown"
    collection_started_at: AwareDatetime | None = None
    collected_at: AwareDatetime | None = None
    exchange: str | None = None
    session_open_at: AwareDatetime | None = None
    session_close_at: AwareDatetime | None = None
    calendar_source: str | None = None
    collection_phase: Literal["during_session", "after_session", "boundary", "unknown"] = "unknown"
    phase_reason: str | None = None
