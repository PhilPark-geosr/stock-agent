from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.application.auth_sessions import SessionService
from app.core.container import build_analysis_service, build_briefing_service
from app.api.deps import get_current_account, require_internal_operator
from app.main import app
from app.domain.briefings import compare_judgments, normalize_judgment
from app.domain.auth import LoginIdentity, UserAccount
from app.integrations.exchange_calendar import ExchangeCalendarsTradingCalendar
from app.interfaces.market_data import MarketDataError
from app.interfaces.trading_calendar import TradingSession
from app.repositories import BriefingRepository, WatchlistRepository
from app.repositories.auth import SqlAlchemyAuthSessionRepository, SqlAlchemyUserAccountRepository
from app.schemas import AnalysisResult
from app.services.briefing_scheduler import BriefingScheduleService


def test_judgment_normalization_and_comparison():
    assert normalize_judgment("강력 매수") == "STRONG_BUY"
    assert normalize_judgment("관망") == "HOLD"
    assert compare_judgments("BUY", "HOLD") == ("COMPARABLE", True, 1)
    assert compare_judgments("UNKNOWN", "BUY") == ("NOT_COMPARABLE", False, 0)


def test_x_user_id_cannot_replace_an_authenticated_session(client):
    override = app.dependency_overrides.pop(get_current_account)
    try:
        response = client.get("/users/me/briefings", headers={"X-User-Id": "alice"})
    finally:
        app.dependency_overrides[get_current_account] = override

    assert response.status_code == 401


def test_internal_briefing_run_requires_separate_operator_credential(
    client, monkeypatch
):
    override = app.dependency_overrides.pop(require_internal_operator)
    monkeypatch.setenv("INTERNAL_API_TOKEN", "operator-secret")
    request = {"type": "PRE_MARKET", "exchange": "KRX", "trading_date": "2026-07-27"}
    try:
        denied = client.post("/internal/briefings/run", json=request)
        allowed = client.post(
            "/internal/briefings/run",
            headers={"X-Internal-Token": "operator-secret"},
            json=request,
        )
    finally:
        app.dependency_overrides[require_internal_operator] = override

    assert denied.status_code == 403
    assert allowed.status_code == 200


def test_real_bearer_sessions_isolate_briefings(
    client, db_session, current_account, monkeypatch
):
    bob = SqlAlchemyUserAccountRepository(db_session).save_or_get_existing(
        UserAccount.register(LoginIdentity("kakao", "briefing-bob"))
    )
    sessions = SessionService(SqlAlchemyAuthSessionRepository(db_session))
    alice_token = sessions.issue(current_account).token
    bob_token = sessions.issue(bob).token
    account_override = app.dependency_overrides.pop(get_current_account)
    internal_override = app.dependency_overrides.pop(require_internal_operator)
    monkeypatch.setenv("INTERNAL_API_TOKEN", "operator-secret")
    try:
        created = client.post(
            "/internal/briefings/run",
            headers={
                "Authorization": f"Bearer {alice_token}",
                "X-Internal-Token": "operator-secret",
            },
            json={"type": "PRE_MARKET", "exchange": "KRX", "trading_date": "2026-07-27"},
        )
        assert created.status_code == 200
        briefing_id = created.json()["id"]

        alice_list = client.get(
            "/users/me/briefings",
            headers={"Authorization": f"Bearer {alice_token}"},
        )
        bob_detail = client.get(
            f"/users/me/briefings/{briefing_id}",
            headers={"Authorization": f"Bearer {bob_token}"},
        )
    finally:
        app.dependency_overrides[get_current_account] = account_override
        app.dependency_overrides[require_internal_operator] = internal_override

    assert [item["id"] for item in alice_list.json()] == [briefing_id]
    assert bob_detail.status_code == 404


def test_pre_and_post_market_briefings_are_idempotent_and_user_scoped(
    client, agent, alert_notifier, authenticate_as
):
    authenticate_as("alice", "005930.KS")

    pre = client.post(
        "/internal/briefings/run",
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
    assert pre_body["deliveries"] == []
    assert "005930.KS" in agent.calls[0].symbol
    assert alert_notifier.messages == []

    repeated = client.post(
        "/internal/briefings/run",
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
        json={"type": "POST_MARKET", "exchange": "KRX", "trading_date": "2026-07-27"},
    )
    assert post.status_code == 200
    item = post.json()["items"][0]
    assert item["previous_analysis_id"] == pre_body["items"][0]["current_analysis_id"]
    assert item["judgment_changed"] is True
    assert item["current_judgment"] == "BUY"
    assert item["previous_judgment"] == "HOLD"
    assert len(agent.calls) == 2

    authenticate_as("bob")
    assert client.get(f"/users/me/briefings/{pre_body['id']}").status_code == 404
    authenticate_as("alice")
    assert client.get("/users/me/briefings").json()[0]["type"] == "POST_MARKET"


def test_non_trading_day_does_not_create_briefing(client, authenticate_as):
    authenticate_as("alice", "005930.KS")

    response = client.post(
        "/internal/briefings/run",
        json={"type": "PRE_MARKET", "exchange": "KRX", "trading_date": "2026-07-26"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "SKIPPED_NON_TRADING_DAY"
    assert client.get("/users/me/briefings").json() == []


def test_watchlist_is_isolated_by_user(client, authenticate_as):
    authenticate_as("alice")
    assert client.post("/watchlist", json={"symbol": "MSFT"}).status_code == 201
    authenticate_as("bob")
    assert client.post("/watchlist", json={"symbol": "MSFT"}).status_code == 201

    authenticate_as("alice")
    assert [item["symbol"] for item in client.get("/watchlist").json()] == ["MSFT"]
    authenticate_as("bob")
    assert [item["symbol"] for item in client.get("/watchlist").json()] == ["MSFT"]


def test_accounts_share_the_same_market_analysis_for_the_same_briefing_run(
    client, authenticate_as, agent
):
    request = {"type": "PRE_MARKET", "exchange": "KRX", "trading_date": "2026-07-27"}
    authenticate_as("alice", "005930.KS")
    alice = client.post("/internal/briefings/run", json=request).json()

    authenticate_as("bob", "005930.KS")
    bob = client.post("/internal/briefings/run", json=request).json()

    assert alice["id"] != bob["id"]
    assert alice["items"][0]["current_analysis_id"] == bob["items"][0]["current_analysis_id"]
    assert len(agent.calls) == 1


def test_login_without_notification_connection_does_not_deliver_briefing(
    client, alert_notifier, monkeypatch, authenticate_as
):
    authenticate_as("alice", "005930.KS")

    def fail_delivery(message: str) -> None:
        raise RuntimeError("kakao unavailable")

    monkeypatch.setattr(alert_notifier, "send_alert", fail_delivery)
    response = client.post(
        "/internal/briefings/run",
        json={"type": "PRE_MARKET", "exchange": "KRX", "trading_date": "2026-07-27"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["items"]
    assert body["deliveries"] == []
    assert alert_notifier.messages == []


def test_force_regeneration_increments_version(client, agent, alert_notifier, authenticate_as):
    authenticate_as("alice", "005930.KS")
    request = {"type": "PRE_MARKET", "exchange": "KRX", "trading_date": "2026-07-27"}

    first = client.post("/internal/briefings/run", json=request)
    second = client.post(
        "/internal/briefings/run", json={**request, "force": True}
    )

    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["version"] == 2
    assert len(agent.calls) == 2
    assert alert_notifier.messages == []


def test_partial_briefing_records_retryable_symbol_failure(client, market_data, monkeypatch, authenticate_as):
    authenticate_as("alice", "005930.KS", "000660.KS")
    original_fetch = market_data.fetch

    def fetch(symbol: str):
        if symbol == "000660.KS":
            raise MarketDataError("temporary market data outage")
        return original_fetch(symbol)

    monkeypatch.setattr(market_data, "fetch", fetch)
    response = client.post(
        "/internal/briefings/run",
        json={"type": "PRE_MARKET", "exchange": "KRX", "trading_date": "2026-07-27"},
    )

    body = response.json()
    assert body["status"] == "PARTIAL"
    assert len(body["items"]) == 1
    assert body["failures"][0]["symbol"] == "000660.KS"
    assert body["failures"][0]["retryable"] is True

    monkeypatch.setattr(market_data, "fetch", original_fetch)
    recovered = client.post(
        "/internal/briefings/run",
        json={"type": "PRE_MARKET", "exchange": "KRX", "trading_date": "2026-07-27"},
    )

    assert recovered.status_code == 200
    assert recovered.json()["status"] == "COMPLETED"
    assert recovered.json()["version"] == 2
    assert len(recovered.json()["items"]) == 2
    assert recovered.json()["failures"] == []
    assert len(market_data.calls) == 2


def test_retryable_failure_attempt_count_increases_without_reanalyzing_success(
    client, market_data, monkeypatch, authenticate_as, agent
):
    authenticate_as("alice", "005930.KS", "000660.KS")
    original_fetch = market_data.fetch

    def fetch(symbol: str):
        if symbol == "000660.KS":
            raise MarketDataError("temporary market data outage")
        return original_fetch(symbol)

    monkeypatch.setattr(market_data, "fetch", fetch)
    request = {"type": "PRE_MARKET", "exchange": "KRX", "trading_date": "2026-07-27"}

    first = client.post("/internal/briefings/run", json=request)
    second = client.post("/internal/briefings/run", json=request)

    assert first.json()["failures"][0]["attempt_count"] == 1
    assert second.json()["failures"][0]["attempt_count"] == 2
    assert second.json()["version"] == 2
    assert len(agent.calls) == 1


def test_retry_skips_non_retryable_failures(
    client, market_data, monkeypatch, authenticate_as
):
    authenticate_as("alice", "005930.KS", "000660.KS", "035420.KS")
    original_fetch = market_data.fetch
    phase = ["first"]

    def fetch(symbol: str):
        if symbol == "000660.KS":
            if phase[0] == "second":
                raise AssertionError("non-retryable failure must not be attempted again")
            raise ValueError("invalid symbol configuration")
        if symbol == "035420.KS" and phase[0] == "first":
            raise MarketDataError("temporary market data outage")
        return original_fetch(symbol)

    monkeypatch.setattr(market_data, "fetch", fetch)
    request = {"type": "PRE_MARKET", "exchange": "KRX", "trading_date": "2026-07-27"}
    first = client.post("/internal/briefings/run", json=request)
    phase[0] = "second"
    second = client.post("/internal/briefings/run", json=request)

    assert first.json()["status"] == "PARTIAL"
    assert second.json()["status"] == "PARTIAL"
    assert second.json()["version"] == 2
    assert [failure["symbol"] for failure in second.json()["failures"]] == ["000660.KS"]
    assert second.json()["failures"][0]["attempt_count"] == 1
    assert len(second.json()["items"]) == 2


def test_post_market_uses_requested_session_close(client, market_data, authenticate_as):
    authenticate_as("alice", "005930.KS")
    response = client.post(
        "/internal/briefings/run",
        json={"type": "POST_MARKET", "exchange": "KRX", "trading_date": "2026-07-27"},
    )

    assert response.status_code == 200
    assert market_data.close_calls == [("005930.KS", date(2026, 7, 27))]


def test_failed_empty_briefing_is_not_exposed_as_user_briefing(
    client, market_data, authenticate_as
):
    authenticate_as("alice", "005930.KS")
    market_data.error = MarketDataError("market unavailable")

    failed = client.post(
        "/internal/briefings/run",
        json={"type": "PRE_MARKET", "exchange": "KRX", "trading_date": "2026-07-27"},
    )

    assert failed.status_code == 200
    assert failed.json()["status"] == "FAILED"
    assert failed.json()["items"] == []
    assert client.get("/users/me/briefings").json() == []
    assert client.get(f"/users/me/briefings/{failed.json()['id']}").status_code == 404


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
    db_session, market_data, agent, alert_notifier, authenticate_as
):
    authenticate_as("alice", "005930.KS")
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
        watchlist_repository=WatchlistRepository(db_session),
        trading_calendar=calendar,
        exchanges=("KRX",),
    )

    first = schedule.run_due(opens_at - timedelta(minutes=30))
    second = schedule.run_due(opens_at - timedelta(minutes=15))

    assert first.generated_ids == second.generated_ids
    assert len(first.generated_ids) == 1
    assert len(agent.calls) == 1
    assert alert_notifier.messages == []


def test_fresh_generation_lease_prevents_duplicate_work(db_session, authenticate_as):
    repository = BriefingRepository(db_session)
    account = authenticate_as("alice")
    first, acquired_first = repository.acquire_generation(
        user_account_id=account.id,
        exchange="KRX",
        briefing_type="PRE_MARKET",
        trading_date=date(2026, 7, 27),
    )
    second, acquired_second = repository.acquire_generation(
        user_account_id=account.id,
        exchange="KRX",
        briefing_type="PRE_MARKET",
        trading_date=date(2026, 7, 27),
    )

    assert first.id == second.id
    assert acquired_first is True
    assert acquired_second is False
