from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from app.domain.analysis_time import ChartBasis
from app.integrations.analysis_calendar import AnalysisSessionCalendar
from app.integrations.yfinance_market_data_provider import YFinanceMarketDataProvider
from app.services.analysis_time import AnalysisTimeResolver


def instant(value):
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def resolve(day, start, end, exchange="KSC", zone="Asia/Seoul", **kwargs):
    basis = ChartBasis(interval="1d", session_date=date.fromisoformat(day), source_timezone=zone)
    metadata = {"instrumentType": "EQUITY", "exchangeName": exchange, "exchangeTimezoneName": zone}
    metadata.update(kwargs.pop("metadata", {}))
    return AnalysisTimeResolver(kwargs.pop("calendar", AnalysisSessionCalendar())).resolve(basis, metadata, instant(start), instant(end))


@pytest.mark.parametrize("day,start,end,phase", [
    ("2026-11-06", "2026-11-06T15:00:00+09:00", "2026-11-06T15:00:02+09:00", "during_session"),
    ("2026-11-06", "2026-11-06T15:30:00+09:00", "2026-11-06T15:30:02+09:00", "after_session"),
    ("2026-11-06", "2026-11-06T15:29:59+09:00", "2026-11-06T15:30:00+09:00", "boundary"),
    ("2026-11-06", "2026-11-06T15:29:59+09:00", "2026-11-06T15:30:02+09:00", "boundary"),
    # Weekend collection of Friday's candle uses Friday's schedule.
    ("2026-11-06", "2026-11-08T12:00:00+09:00", "2026-11-08T12:00:02+09:00", "after_session"),
    # Korean special session must not be treated as closed at 15:30.
    ("2026-11-19", "2026-11-19T16:00:00+09:00", "2026-11-19T16:00:02+09:00", "during_session"),
    ("2025-11-13", "2025-11-13T16:30:00+09:00", "2025-11-13T16:30:02+09:00", "after_session"),
])
def test_kr_session_boundaries(day, start, end, phase):
    basis = resolve(day, start, end)
    assert basis.collection_phase == phase
    assert basis.finality == "unknown"  # A schedule is not provider-finality evidence.
    assert basis.calendar_source.startswith("exchange_calendars/")
    assert basis.collection_started_at == instant(start)
    assert basis.collected_at == instant(end)


@pytest.mark.parametrize("exchange", ["NMS", "NGM", "NCM", "NYQ", "ASE", "PCX"])
@pytest.mark.parametrize("day,close", [
    ("2026-03-06", "2026-03-06T21:00:00Z"),
    ("2026-03-09", "2026-03-09T20:00:00Z"),
    ("2026-11-27", "2026-11-27T18:00:00Z"),  # 13:00 EST early close
])
def test_us_dst_and_early_close_for_supported_exchanges(exchange, day, close):
    end = instant(close)
    basis = resolve(day, (end - timedelta(minutes=1)).isoformat(), close, exchange, "America/New_York")
    assert basis.session_close_at == end
    assert basis.collection_phase == "boundary"
    after = resolve(day, close, (end + timedelta(seconds=1)).isoformat(), exchange, "America/New_York")
    assert after.collection_phase == "after_session"


@pytest.mark.parametrize("day", ["2026-11-07", "2026-06-03", "2026-07-17"])
def test_kr_non_session_row_is_not_promoted_to_closed(day):
    basis = resolve(day, f"{day}T16:00:00+09:00", f"{day}T16:00:01+09:00")
    assert basis.collection_phase == "unknown"
    assert basis.phase_reason == "not_a_trading_session"


def test_us_holiday_is_not_promoted_to_closed():
    basis = resolve("2026-11-26", "2026-11-26T22:00:00Z", "2026-11-26T22:00:01Z", "NMS", "America/New_York")
    assert basis.phase_reason == "not_a_trading_session"


@pytest.mark.parametrize("metadata,reason", [
    ({"instrumentType": "CRYPTOCURRENCY"}, "unsupported_or_missing_market"),
    ({"exchangeName": "UNKNOWN"}, "unsupported_or_missing_market"),
    ({"exchangeName": {}}, "unsupported_or_missing_market"),
    ({"exchangeTimezoneName": "America/New_York"}, "market_timezone_mismatch"),
])
def test_unproven_market_is_not_guessed(metadata, reason):
    basis = resolve("2026-11-06", "2026-11-06T16:00:00+09:00", "2026-11-06T16:00:01+09:00", metadata=metadata)
    assert basis.collection_phase == "unknown"
    assert basis.phase_reason == reason


@pytest.mark.parametrize("day,start,end,reason", [
    ("2026-11-06", "2026-11-06T08:00:00+09:00", "2026-11-06T08:00:01+09:00", "before_session_open"),
    ("2026-11-06", "2026-11-06T16:00:00+09:00", "2026-11-06T15:59:59+09:00", "invalid_collection_window"),
    ("2027-11-05", "2027-11-05T16:00:00+09:00", "2027-11-05T16:00:01+09:00", "calendar_out_of_range"),
])
def test_invalid_or_uncovered_evidence_explains_unknown(day, start, end, reason):
    basis = resolve(day, start, end)
    assert basis.collection_phase == "unknown"
    assert basis.phase_reason == reason


def test_calendar_failure_does_not_discard_price_or_trade_date():
    class BrokenCalendar:
        def session(self, *_):
            raise RuntimeError("calendar offline")
    basis = resolve("2026-11-06", "2026-11-06T16:00:00+09:00", "2026-11-06T16:00:01+09:00", calendar=BrokenCalendar())
    assert basis.phase_reason == "calendar_unavailable"
    assert basis.session_date == date(2026, 11, 6)


def test_provider_uses_history_window_not_metadata_request_or_analysis_completion(monkeypatch):
    import yfinance
    times = iter([instant("2026-11-06T15:29:58+09:00"), instant("2026-11-06T15:29:59+09:00")])
    frame = pd.DataFrame({"Open": [100], "High": [110], "Low": [90], "Close": [105], "Volume": [1000]},
                         index=pd.date_range("2026-11-06", periods=1, tz="Asia/Seoul"))
    history_calls = []
    def history(**kwargs):
        history_calls.append(kwargs)
        return frame
    monkeypatch.setattr(yfinance, "Ticker", lambda _: SimpleNamespace(history=history,
        get_history_metadata=lambda: {"instrumentType": "EQUITY", "exchangeName": "KSC", "exchangeTimezoneName": "Asia/Seoul"}))
    snapshot = YFinanceMarketDataProvider(clock=lambda: next(times)).fetch("005930.KS")
    assert snapshot.chart_basis.collection_phase == "during_session"
    assert snapshot.chart_basis.collected_at == instant("2026-11-06T15:29:59+09:00")
    assert snapshot.indicators.latest_close == 105
    assert history_calls[0]["prepost"] is False


def test_first_kr_session_has_delayed_open():
    session = AnalysisSessionCalendar().session("XKRX", date(2026, 1, 2))
    assert session.opens_at == instant("2026-01-02T10:00:00+09:00")
