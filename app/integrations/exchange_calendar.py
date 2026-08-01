from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import exchange_calendars as exchange_calendars
import pandas as pd

from app.interfaces.trading_calendar import TradingCalendar, TradingSession


CALENDAR_CODES = {
    "KRX": "XKRX",
    "US": "XNYS",
    "NYSE": "XNYS",
    "NASDAQ": "XNAS",
}

EXCHANGE_TIMEZONES = {
    "KRX": ZoneInfo("Asia/Seoul"),
    "US": ZoneInfo("America/New_York"),
    "NYSE": ZoneInfo("America/New_York"),
    "NASDAQ": ZoneInfo("America/New_York"),
}


class ExchangeCalendarsTradingCalendar(TradingCalendar):
    def local_date(self, exchange: str, instant: datetime) -> date:
        normalized = exchange.strip().upper()
        timezone_info = EXCHANGE_TIMEZONES.get(normalized)
        if timezone_info is None:
            raise ValueError(f"unsupported exchange: {exchange}")
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=timezone.utc)
        return instant.astimezone(timezone_info).date()

    def session_on(self, exchange: str, trading_date: date) -> TradingSession | None:
        normalized = exchange.strip().upper()
        calendar_code = CALENDAR_CODES.get(normalized)
        if calendar_code is None:
            raise ValueError(f"unsupported exchange: {exchange}")

        calendar = exchange_calendars.get_calendar(calendar_code)
        session_label = pd.Timestamp(trading_date)
        if not calendar.is_session(session_label):
            return None

        opens_at = calendar.session_open(session_label).to_pydatetime().astimezone(timezone.utc)
        closes_at = calendar.session_close(session_label).to_pydatetime().astimezone(timezone.utc)
        return TradingSession(
            exchange=normalized,
            trading_date=trading_date,
            opens_at=opens_at,
            closes_at=closes_at,
        )
