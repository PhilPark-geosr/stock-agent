"""Scheduler configuration loaded from environment."""

from __future__ import annotations

import os

from app.settings import load_environment
from app.trading_window import (
    DEFAULT_MARKET_END_HOUR,
    DEFAULT_MARKET_START_HOUR,
    DEFAULT_TIMEZONE,
)


def scheduler_settings() -> dict[str, int | str | bool]:
    load_environment()
    return {
        "enabled": os.getenv("SCHEDULER_ENABLED", "true").lower() in {"1", "true", "yes", "on"},
        "interval_minutes": int(os.getenv("SCHEDULER_INTERVAL_MINUTES", "60")),
        "timezone": os.getenv("SCHEDULER_TIMEZONE", DEFAULT_TIMEZONE),
        "market_start_hour": int(os.getenv("SCHEDULER_MARKET_START_HOUR", str(DEFAULT_MARKET_START_HOUR))),
        "market_end_hour": int(os.getenv("SCHEDULER_MARKET_END_HOUR", str(DEFAULT_MARKET_END_HOUR))),
    }
