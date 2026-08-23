from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.core.trading_window import is_market_hours
from app.core.container import build_analysis_service
from app.repositories import AnalysisRepository, WatchlistRepository
from app.domain.auth import LoginIdentity, UserAccount
from app.domain.symbols import StockSymbol
from app.repositories.auth import SqlAlchemyUserAccountRepository
from app.services.scheduler import run_scheduled_batch
from tests.conftest import ALERT_WINDOW_UTC, FakeAnalysisAgent, FakeMarketDataProvider

KST = ZoneInfo("Asia/Seoul")


def test_scheduler_checks_due_work_before_first_sleep(monkeypatch):
    from app.core import scheduler_runtime

    calls = []
    stop_event = asyncio.Event()

    class FakeDb:
        def close(self):
            calls.append("close")

    class FakeSchedule:
        def run_due(self):
            calls.append("briefing")
            return SimpleNamespace(generated_ids=[])

    async def stop_on_sleep(seconds):
        calls.append("sleep")
        stop_event.set()

    monkeypatch.setattr(
        scheduler_runtime,
        "scheduler_settings",
        lambda: {
            "enabled": True,
            "interval_minutes": 60,
            "market_start_hour": 8,
            "market_end_hour": 16,
            "timezone": "Asia/Seoul",
        },
    )
    monkeypatch.setattr(scheduler_runtime, "build_analysis_service", lambda db: object())
    monkeypatch.setattr(
        scheduler_runtime,
        "run_scheduled_batch",
        lambda service: calls.append("analysis") or SimpleNamespace(
            ran=False, skipped_reason="not_due"
        ),
    )
    monkeypatch.setattr(
        scheduler_runtime, "build_briefing_schedule_service", lambda db: FakeSchedule()
    )

    asyncio.run(
        scheduler_runtime.scheduler_loop(
            lambda: FakeDb(), stop_event=stop_event, sleep=stop_on_sleep
        )
    )

    assert calls[:3] == ["analysis", "briefing", "close"]
    assert calls[-1] == "sleep"


def subscribe(db_session, symbol: str = "005930.KS"):
    account = SqlAlchemyUserAccountRepository(db_session).save_or_get_existing(
        UserAccount.register(LoginIdentity("kakao", "scheduler-user"))
    )
    return WatchlistRepository(db_session).add(account.id, StockSymbol.of(symbol))


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
    subscribe(db_session)
    service = build_analysis_service(
        db_session,
        market_data_provider=market_data,
        agent=agent,
        alert_notifier=alert_notifier,
        alert_window_checker=lambda now: True,
        now_provider=lambda: ALERT_WINDOW_UTC,
    )

    first = run_scheduled_batch(
        analysis_service=service,
        ignore_market_hours=True,
        now=ALERT_WINDOW_UTC,
    )
    second = run_scheduled_batch(
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
    subscribe(db_session)
    service = build_analysis_service(
        db_session,
        market_data_provider=market_data,
        agent=agent,
        alert_notifier=alert_notifier,
        alert_window_checker=lambda now: True,
    )
    outside = datetime(2026, 6, 2, 7, 0, tzinfo=KST)

    result = run_scheduled_batch(
        analysis_service=service,
        ignore_market_hours=False,
        now=outside,
    )

    assert result.ran is False
    assert result.skipped_reason == "outside_market_hours"
    assert agent.calls == []


def test_run_scheduled_batch_empty_watchlist(db_session, alert_notifier):
    service = build_analysis_service(
        db_session,
        alert_notifier=alert_notifier,
        alert_window_checker=lambda now: True,
    )
    result = run_scheduled_batch(service, ignore_market_hours=True, now=ALERT_WINDOW_UTC)

    assert result.ran is True
    assert result.symbols_analyzed == []
    assert result.skipped_reason == "empty_watchlist"


def test_scheduler_does_not_send_user_notifications(db_session, market_data, alert_notifier):
    subscribe(db_session)
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
        market_data_provider=market_data,
        agent=agent,
        alert_notifier=alert_notifier,
        alert_window_checker=lambda now: True,
        now_provider=lambda: ALERT_WINDOW_UTC,
    )

    run_scheduled_batch(
        analysis_service=service,
        ignore_market_hours=True,
        now=ALERT_WINDOW_UTC,
    )
    run_scheduled_batch(
        analysis_service=service,
        ignore_market_hours=True,
        now=ALERT_WINDOW_UTC,
    )

    assert alert_notifier.messages == []


def test_scheduler_run_endpoint(client, db_session, market_data, agent, alert_notifier):
    from unittest.mock import patch

    subscribe(db_session)
    service = build_analysis_service(
        db_session,
        market_data_provider=market_data,
        agent=agent,
        alert_notifier=alert_notifier,
        alert_window_checker=lambda now: True,
        now_provider=lambda: ALERT_WINDOW_UTC,
    )

    from app.api.deps import get_analysis_service

    client.app.dependency_overrides[get_analysis_service] = lambda: service
    with patch("app.api.routes.run_scheduled_batch", wraps=run_scheduled_batch):
        response = client.post("/scheduler/run?force=true")

    assert response.status_code == 200
    body = response.json()
    assert body["ran"] is True
    assert body["symbols_analyzed"] == ["005930.KS"]
    assert AnalysisRepository(db_session).count_by_symbol("005930.KS") == 1
