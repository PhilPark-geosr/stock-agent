"""KST market hours and alert window helpers."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "Asia/Seoul"
DEFAULT_MARKET_START_HOUR = 8
DEFAULT_MARKET_END_HOUR = 16


def _to_local(now: datetime, tz_name: str) -> datetime:
    tz = ZoneInfo(tz_name)
    if now.tzinfo is None:
        return now.replace(tzinfo=tz)
    return now.astimezone(tz)


def is_within_hour_window(
    now: datetime,
    *,
    start_hour: int,
    end_hour: int,
    tz_name: str = DEFAULT_TIMEZONE,
) -> bool:
    """Return True when start_hour <= local hour < end_hour."""
    local = _to_local(now, tz_name)
    return start_hour <= local.hour < end_hour


def is_market_hours(
    now: datetime,
    *,
    start_hour: int = DEFAULT_MARKET_START_HOUR,
    end_hour: int = DEFAULT_MARKET_END_HOUR,
    tz_name: str = DEFAULT_TIMEZONE,
) -> bool:
    return is_within_hour_window(
        now,
        start_hour=start_hour,
        end_hour=end_hour,
        tz_name=tz_name,
    )


def is_alert_window(
    now: datetime,
    *,
    start_hour: int = DEFAULT_MARKET_START_HOUR,
    end_hour: int = DEFAULT_MARKET_END_HOUR,
    tz_name: str = DEFAULT_TIMEZONE,
) -> bool:
    return is_market_hours(
        now,
        start_hour=start_hour,
        end_hour=end_hour,
        tz_name=tz_name,
    )
