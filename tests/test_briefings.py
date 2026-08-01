from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.core.container import build_analysis_service, build_briefing_delivery_service, build_briefing_service
from app.domain.briefings import compare_judgments, normalize_judgment
from app.integrations.exchange_calendar import ExchangeCalendarsTradingCalendar
from app.interfaces.market_data import MarketDataError
from app.interfaces.trading_calendar import TradingSession
from app.repositories import BriefingRepository, WatchlistRepository
from app.schemas import AnalysisResult
from app.services.briefing_scheduler import BriefingScheduleService


def test_judgment_normalization_and_comparison():
    assert normalize_judgment("강력 매수") == "STRONG_BUY"
    assert normalize_judgment("관망") == "HOLD"
    assert compare_judgments("BUY", "HOLD") == ("COMPARABLE", True, 1)
    assert compare_judgments("UNKNOWN", "BUY") == ("NOT_COMPARABLE", False, 0)


def test_pre_and_post_market_briefings_are_idempotent_and_user_scoped(
    client, agent, alert_notifier
):
    headers = {"X-User-Id": "alice"}
    assert client.post("/watchlist", headers=headers, json={"symbol": "005930.KS"}).status_code == 201

    pre = client.post(
        "/internal/briefings/run",
        headers=headers,
        json={"type": "PRE_MARKET", "exchange": "KRX", "trading_date": "2026-07-27"},
    )
    assert pre.status_code == 200
    pre_body = pre.json()
    assert pre_body["type"] == "PRE_MARKET"
    assert pre_body["status"] == "COMPLETED"
    assert pre_body["resolved_symbols"] == ["005930.KS"]
    assert pre_body["scopes"][0]["source_type"] == "WATCHLIST"
    assert pre_body["scopes"][0]["resolved_symbols"] == ["005930.KS"]
    assert pre_body["items"][0]["comparison_status"] == "NOT_COMPARABLE"
    assert pre_body["deliveries"][0]["status"] == "SENT"
    assert pre_body["deliveries"][0]["attempt_count"] == 1
    assert "005930.KS" in agent.calls[0].symbol
    assert "005930.KS" in alert_notifier.messages[0]
    assert "현재 판단" in alert_notifier.messages[0]

    repeated = client.post(
        "/internal/briefings/run",
        headers=headers,
        json={"type": "PRE_MARKET", "exchange": "KRX", "trading_date": "2026-07-27"},
    )
    assert repeated.status_code == 200
    assert repeated.json()["id"] == pre_body["id"]
    assert len(agent.calls) == 1

    agent.result = AnalysisResult(
        symbol="005930.KS",
        analysis_time=datetime(2026, 7, 27, 7, tzinfo=timezone.utc),
        data_time=datetime(2026, 7, 27, 6, tzinfo=timezone.utc),
        verdict="상승",
        summary="매수 관점으로 변경",
        key_reasons=["거래량 증가"],
        risk_factors=[],
        indicators={"latest_close": 73000},
        alert_triggered=False,
        matched_alert_conditions=[],
        alert_reason="",
    )
    post = client.post(
        "/internal/briefings/run",
        headers=headers,
        json={"type": "POST_MARKET", "exchange": "KRX", "trading_date": "2026-07-27"},
    )
    assert post.status_code == 200
    item = post.json()["items"][0]
    assert item["previous_analysis_id"] == pre_body["items"][0]["current_analysis_id"]
    assert item["judgment_changed"] is True
    assert item["current_judgment"] == "BUY"
    assert item["previous_judgment"] == "HOLD"
    assert len(agent.calls) == 2

    assert client.get(
        f"/users/me/briefings/{pre_body['id']}", headers={"X-User-Id": "bob"}
    ).status_code == 404
    assert client.get("/users/me/briefings", headers=headers).json()[0]["type"] == "POST_MARKET"


def test_non_trading_day_does_not_create_briefing(client):
    headers = {"X-User-Id": "alice"}
    client.post("/watchlist", headers=headers, json={"symbol": "005930.KS"})

    response = client.post(
        "/internal/briefings/run",
        headers=headers,
        json={"type": "PRE_MARKET", "exchange": "KRX", "trading_date": "2026-07-26"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "SKIPPED_NON_TRADING_DAY"
    assert client.get("/users/me/briefings", headers=headers).json() == []


def test_watchlist_is_isolated_by_user(client):
    assert client.post(
        "/watchlist", headers={"X-User-Id": "alice"}, json={"symbol": "MSFT"}
    ).status_code == 201
    assert client.post(
        "/watchlist", headers={"X-User-Id": "bob"}, json={"symbol": "MSFT"}
    ).status_code == 201

    assert len(client.get("/watchlist", headers={"X-User-Id": "alice"}).json()) == 1
    assert len(client.get("/watchlist", headers={"X-User-Id": "bob"}).json()) == 1


def test_delivery_failure_does_not_discard_completed_briefing(
    client, alert_notifier, monkeypatch
):
    headers = {"X-User-Id": "alice"}
    client.post("/watchlist", headers=headers, json={"symbol": "005930.KS"})

    def fail_delivery(message: str) -> None:
        raise RuntimeError("kakao unavailable")

    monkeypatch.setattr(alert_notifier, "send_alert", fail_delivery)
    response = client.post(
        "/internal/briefings/run",
        headers=headers,
        json={"type": "PRE_MARKET", "exchange": "KRX", "trading_date": "2026-07-27"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["items"]
    assert body["deliveries"][0]["status"] == "FAILED"
    assert body["deliveries"][0]["last_error"] == "kakao unavailable"

    monkeypatch.setattr(
        alert_notifier, "send_alert", lambda message: alert_notifier.messages.append(message)
    )
    retried = client.post(
        "/internal/briefings/run",
        headers=headers,
        json={"type": "PRE_MARKET", "exchange": "KRX", "trading_date": "2026-07-27"},
    ).json()
    assert retried["deliveries"][0]["status"] == "SENT"
    assert retried["deliveries"][0]["attempt_count"] == 2


def test_force_regeneration_increments_version(client, agent, alert_notifier):
    headers = {"X-User-Id": "alice"}
    client.post("/watchlist", headers=headers, json={"symbol": "005930.KS"})
    request = {"type": "PRE_MARKET", "exchange": "KRX", "trading_date": "2026-07-27"}

    first = client.post("/internal/briefings/run", headers=headers, json=request)
    second = client.post(
        "/internal/briefings/run", headers=headers, json={**request, "force": True}
    )

    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["version"] == 2
    assert len(agent.calls) == 2
    assert len(alert_notifier.messages) == 2


def test_partial_briefing_records_retryable_symbol_failure(client, market_data, monkeypatch):
    headers = {"X-User-Id": "alice"}
    client.post("/watchlist", headers=headers, json={"symbol": "005930.KS"})
    client.post("/watchlist", headers=headers, json={"symbol": "000660.KS"})
    original_fetch = market_data.fetch

    def fetch(symbol: str):
        if symbol == "000660.KS":
            raise MarketDataError("temporary market data outage")
        return original_fetch(symbol)

    monkeypatch.setattr(market_data, "fetch", fetch)
    response = client.post(
        "/internal/briefings/run",
        headers=headers,
        json={"type": "PRE_MARKET", "exchange": "KRX", "trading_date": "2026-07-27"},
    )

    body = response.json()
    assert body["status"] == "PARTIAL"
    assert len(body["items"]) == 1
    assert body["failures"][0]["symbol"] == "000660.KS"
    assert body["failures"][0]["retryable"] is True


def test_post_market_uses_requested_session_close(client, market_data):
    headers = {"X-User-Id": "alice"}
    client.post("/watchlist", headers=headers, json={"symbol": "005930.KS"})
    response = client.post(
        "/internal/briefings/run",
        headers=headers,
        json={"type": "POST_MARKET", "exchange": "KRX", "trading_date": "2026-07-27"},
    )

    assert response.status_code == 200
    assert market_data.close_calls == [("005930.KS", date(2026, 7, 27))]


def test_exchange_calendar_handles_holiday_early_close_and_dst():
    calendar = ExchangeCalendarsTradingCalendar()

    assert calendar.session_on("KRX", date(2026, 1, 1)) is None
    early_close = calendar.session_on("NYSE", date(2026, 11, 27))
    before_dst = calendar.session_on("NYSE", date(2026, 3, 6))
    after_dst = calendar.session_on("NYSE", date(2026, 3, 9))

    assert early_close is not None and early_close.closes_at.hour == 18
    assert before_dst is not None and before_dst.opens_at.hour == 14
    assert after_dst is not None and after_dst.opens_at.hour == 13


class FixedTradingCalendar:
    def __init__(self, session: TradingSession) -> None:
        self.session = session

    def local_date(self, exchange: str, instant: datetime):
        return self.session.trading_date

    def session_on(self, exchange: str, trading_date: date):
        if exchange == self.session.exchange and trading_date == self.session.trading_date:
            return self.session
        return None


def test_schedule_service_generates_due_briefing_once(
    db_session, market_data, agent, alert_notifier
):
    user_id = "alice"
    WatchlistRepository(db_session).add("005930.KS", user_id)
    opens_at = datetime(2026, 7, 27, 0, tzinfo=timezone.utc)
    session = TradingSession("KRX", date(2026, 7, 27), opens_at, opens_at + timedelta(hours=6, minutes=30))
    calendar = FixedTradingCalendar(session)
    analysis_service = build_analysis_service(
        db_session,
        market_data_provider=market_data,
        agent=agent,
        alert_notifier=alert_notifier,
        alert_window_checker=lambda now: True,
    )
    briefing_service = build_briefing_service(
        db_session,
        analysis_service=analysis_service,
        trading_calendar=calendar,
    )
    schedule = BriefingScheduleService(
        briefing_service=briefing_service,
        delivery_service=build_briefing_delivery_service(
            db_session, notifier=alert_notifier
        ),
        watchlist_repository=WatchlistRepository(db_session),
        trading_calendar=calendar,
        exchanges=("KRX",),
    )

    first = schedule.run_due(opens_at - timedelta(minutes=30))
    second = schedule.run_due(opens_at - timedelta(minutes=15))

    assert first.generated_ids == second.generated_ids
    assert len(first.generated_ids) == 1
    assert len(agent.calls) == 1
    assert len(alert_notifier.messages) == 1


def test_fresh_generation_lease_prevents_duplicate_work(db_session):
    repository = BriefingRepository(db_session)
    first, acquired_first = repository.acquire_generation(
        user_id="alice",
        exchange="KRX",
        briefing_type="PRE_MARKET",
        trading_date=date(2026, 7, 27),
    )
    second, acquired_second = repository.acquire_generation(
        user_id="alice",
        exchange="KRX",
        briefing_type="PRE_MARKET",
        trading_date=date(2026, 7, 27),
    )

    assert first.id == second.id
    assert acquired_first is True
    assert acquired_second is False
