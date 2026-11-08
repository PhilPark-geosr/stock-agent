"""Versioned regular-session schedules for analysis input collection.

This is a schedule, not a live trading-status or quote-finality feed.
Reviewed local exceptions and their sources are in analysis_time_basis_design.md.
"""

from datetime import date, datetime, time, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

import exchange_calendars as xcals

from app.domain.analysis_time import CalendarUnavailable, TradingSession


@lru_cache(maxsize=8)
def _calendar(exchange: str):
    return xcals.get_calendar(exchange)


class AnalysisSessionCalendar:
    """Resolve the selected candle's session, never today's session instead."""

    def session(self, exchange: str, day: date) -> TradingSession | None:
        # Bound calendar assumptions; new years need a release/review, not a
        # silent weekday-only guess. Existing snapshots are never recalculated.
        final_year = 2026 if exchange == "XKRX" else 2028
        if not 2025 <= day.year <= final_year:
            raise CalendarUnavailable("calendar_out_of_range")
        source = f"exchange_calendars/{xcals.__version__};analysis-overrides/2026-11-08"
        if exchange == "XKRX":
            # Explicit reviewed exceptions cover gaps in the locked calendar.
            if day in (date(2026, 6, 3), date(2026, 7, 17)):
                return None
            if day in (date(2025, 11, 13), date(2026, 11, 19)):
                zone = ZoneInfo("Asia/Seoul")
                return TradingSession(
                    datetime.combine(day, time(10), zone).astimezone(timezone.utc),
                    datetime.combine(day, time(16, 30), zone).astimezone(timezone.utc),
                    source,
                )
        cal = _calendar(exchange)
        if not cal.is_session(day):
            return None
        return TradingSession(
            cal.session_open(day).to_pydatetime(),
            cal.session_close(day).to_pydatetime(),
            source,
        )
