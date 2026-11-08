from datetime import date, datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from app.domain.analysis_time import ChartBasis
from app.integrations.yfinance_market_data_provider import YFinanceMarketDataProvider
from app.repositories import AnalysisRepository


@pytest.mark.parametrize("zone, day", [
    ("Asia/Seoul", "2026-11-06"),
    ("America/New_York", "2026-03-06"),
    ("America/New_York", "2026-03-09"),
])
def test_daily_basis_uses_last_valid_local_row_before_utc_conversion(monkeypatch, zone, day):
    import yfinance

    index = pd.date_range(day, periods=2, tz=zone)
    frame = pd.DataFrame({
        "Open": [100, None], "High": [110, None], "Low": [90, None],
        "Close": [105, None], "Volume": [1000, 0],
    }, index=index)
    monkeypatch.setattr(yfinance, "Ticker", lambda _: SimpleNamespace(history=lambda **_: frame))
    snapshot = YFinanceMarketDataProvider().fetch("TEST")

    assert snapshot.chart_basis.session_date == date.fromisoformat(day)
    assert snapshot.chart_basis.source_timezone == zone
    assert snapshot.chart_basis.finality == "unknown"
    assert snapshot.records[-1].close == snapshot.indicators.latest_close == 105
    assert snapshot.data_time == index[0].to_pydatetime().astimezone(timezone.utc)
    if zone == "Asia/Seoul":
        assert snapshot.data_time.date() != snapshot.chart_basis.session_date


@pytest.mark.parametrize("zone, interval", [(None, "1d"), ("Asia/Seoul", "1m")])
def test_unproven_daily_date_is_not_inferred(monkeypatch, zone, interval):
    import yfinance

    frame = pd.DataFrame({
        "Open": [100], "High": [110], "Low": [90], "Close": [105], "Volume": [1000],
    }, index=pd.date_range("2026-11-06", periods=1, tz=zone))
    monkeypatch.setattr(yfinance, "Ticker", lambda _: SimpleNamespace(history=lambda **_: frame))
    snapshot = YFinanceMarketDataProvider(interval=interval).fetch("TEST")
    assert snapshot.chart_basis.session_date is None


def test_recorded_basis_survives_new_analysis_and_all_read_endpoints(client, market_data, agent, db_session):
    market_data.snapshot = market_data.snapshot.model_copy(update={
        "chart_basis": ChartBasis(interval="1d", session_date=date(2026, 11, 6), source_timezone="Asia/Seoul"),
    })
    # A model-generated price/time must not override the actual input basis.
    agent.result = agent.analyze(market_data.snapshot).model_copy(update={
        "data_time": datetime(2099, 1, 1, tzinfo=timezone.utc),
        "indicators": {"latest_close": 999999},
    })
    created = client.post("/stocks/005930.KS/analysis")
    assert created.status_code == 201
    first = created.json()
    assert first["chart_basis"]["session_date"] == "2026-11-06"
    assert first["support_levels"]["latest_close"] == 72000
    assert first["data_timestamp"].startswith("2026-05-30")  # fixture input, not agent time
    assert first["analyzed_at"].endswith("Z")
    assert first["analyzed_at"] != first["raw_result"]["analysis_time"]

    market_data.snapshot = market_data.snapshot.model_copy(update={
        "chart_basis": ChartBasis(interval="1d", session_date=date(2026, 11, 9), source_timezone="Asia/Seoul"),
    })
    second = client.post("/stocks/005930.KS/analysis").json()
    db_session.expire_all()
    detail = client.get(f"/stocks/005930.KS/analysis/{first['id']}").json()
    assert detail == first
    latest = client.get("/stocks/005930.KS/analysis/latest").json()
    assert latest["id"] == second["id"]
    history = client.get("/stocks/005930.KS/analysis").json()
    assert [row["chart_basis"]["session_date"] for row in history] == ["2026-11-09", "2026-11-06"]
    assert history[1]["analyzed_at"] == first["analyzed_at"]
    assert len(market_data.calls) == 2  # historical reads do not fetch new prices


@pytest.mark.parametrize("raw", [None, {}, {"_chart_basis_v1": {"session_date": "invalid"}}])
def test_legacy_or_malformed_basis_keeps_history_readable(client, db_session, raw):
    saved = AnalysisRepository(db_session).save(
        symbol="005930.KS", overall_judgment="neutral", summary="old",
        data_timestamp=datetime(2026, 11, 5, 15, tzinfo=timezone.utc), raw_result=raw,
    )
    detail = client.get(f"/stocks/005930.KS/analysis/{saved.id}").json()
    assert detail["chart_basis"] is None
    assert detail["data_timestamp"] == "2026-11-05T15:00:00Z"
    assert client.get("/stocks/005930.KS/analysis").json()[0]["chart_basis"] is None
    assert saved.raw_result == raw
