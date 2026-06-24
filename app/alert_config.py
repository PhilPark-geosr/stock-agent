"""Kakao alert window configuration."""

from __future__ import annotations

import os

from app.settings import load_environment
from app.trading_window import DEFAULT_MARKET_END_HOUR, DEFAULT_MARKET_START_HOUR, DEFAULT_TIMEZONE


def alert_window_settings() -> dict[str, int | str]:
    load_environment()
    return {
        "timezone": os.getenv("ALERT_TIMEZONE", DEFAULT_TIMEZONE),
        "market_start_hour": int(os.getenv("ALERT_START_HOUR", str(DEFAULT_MARKET_START_HOUR))),
        "market_end_hour": int(os.getenv("ALERT_END_HOUR", str(DEFAULT_MARKET_END_HOUR))),
    }
