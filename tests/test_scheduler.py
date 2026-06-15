from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.repositories import AnalysisRepository, WatchlistRepository
from app.scheduler import run_scheduled_batch
from app.services import build_analysis_service
from app.trading_window import is_market_hours
from tests.conftest import ALERT_WINDOW_UTC, FakeAnalysisAgent, FakeMarketDataProvider

KST = ZoneInfo("Asia/Seoul")


@pytest.mark.parametrize(
    ("local_hour", "expected"),
    [
        (7, False),
        (8, True),
        (12, True),
        (15, True),
        (16, False),
    ],
)
def test_is_market_hours_boundaries(local_hour: int, expected: bool):
    now = datetime(2026, 6, 2, local_hour, 30, tzinfo=KST)
    assert is_market_hours(now) is expected


def test_run_scheduled_batch_accumulates_results(db_session, market_data, agent, alert_notifier):
    WatchlistRepository(db_session).add("005930.KS")
    service = build_analysis_service(
        db_session,
        market_data_provider=market_data,
        agent=agent,
        alert_notifier=alert_notifier,
        now_provider=lambda: ALERT_WINDOW_UTC,
    )

    first = run_scheduled_batch(
        db_session,
        analysis_service=service,
        ignore_market_hours=True,
        now=ALERT_WINDOW_UTC,
    )
    second = run_scheduled_batch(
        db_session,
        analysis_service=service,
        ignore_market_hours=True,
        now=ALERT_WINDOW_UTC,
    )

    assert first.ran is True
    assert first.symbols_analyzed == ["005930.KS"]
    assert second.symbols_analyzed == ["005930.KS"]
    assert AnalysisRepository(db_session).count_by_symbol("005930.KS") == 2
    assert len(agent.calls) == 2


def test_run_scheduled_batch_skips_outside_market_hours(db_session, market_data, agent, alert_notifier):
    WatchlistRepository(db_session).add("005930.KS")
    service = build_analysis_service(
        db_session,
        market_data_provider=market_data,
        agent=agent,
        alert_notifier=alert_notifier,
    )
    outside = datetime(2026, 6, 2, 7, 0, tzinfo=KST)

    result = run_scheduled_batch(
        db_session,
        analysis_service=service,
        ignore_market_hours=False,
        now=outside,
    )

    assert result.ran is False
    assert result.skipped_reason == "outside_market_hours"
    assert agent.calls == []


def test_run_scheduled_batch_empty_watchlist(db_session):
    result = run_scheduled_batch(db_session, ignore_market_hours=True, now=ALERT_WINDOW_UTC)

    assert result.ran is True
    assert result.symbols_analyzed == []
    assert result.skipped_reason == "empty_watchlist"


def test_alert_sent_only_once_for_same_conditions(db_session, alert_notifier):
    WatchlistRepository(db_session).add("005930.KS")
    from app.schemas import AnalysisResult

    agent = FakeAnalysisAgent(
        result=AnalysisResult(
            symbol="005930.KS",
            analysis_time=datetime(2026, 6, 1, 3, tzinfo=timezone.utc),
            data_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
            verdict="상승",
            summary="alert batch",
            key_reasons=[],
            risk_factors=[],
            indicators={"latest_close": 72000},
            alert_triggered=True,
            matched_alert_conditions=["price_move_abs_gte_3_percent"],
            alert_reason="급등 알림",
        )
    )
    service = build_analysis_service(
        db_session,
        agent=agent,
        alert_notifier=alert_notifier,
        now_provider=lambda: ALERT_WINDOW_UTC,
    )

    run_scheduled_batch(
        db_session,
        analysis_service=service,
        ignore_market_hours=True,
        now=ALERT_WINDOW_UTC,
    )
    run_scheduled_batch(
        db_session,
        analysis_service=service,
        ignore_market_hours=True,
        now=ALERT_WINDOW_UTC,
    )

    assert alert_notifier.messages == ["급등 알림"]


def test_scheduler_run_endpoint(client, db_session, market_data, agent, alert_notifier):
    from unittest.mock import patch

    WatchlistRepository(db_session).add("005930.KS")
    service = build_analysis_service(
        db_session,
        market_data_provider=market_data,
        agent=agent,
        alert_notifier=alert_notifier,
        now_provider=lambda: ALERT_WINDOW_UTC,
    )

    with patch("app.scheduler.build_analysis_service", return_value=service):
        response = client.post("/scheduler/run?force=true")

    assert response.status_code == 200
    body = response.json()
    assert body["ran"] is True
    assert body["symbols_analyzed"] == ["005930.KS"]
    assert AnalysisRepository(db_session).count_by_symbol("005930.KS") == 1
