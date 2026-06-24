from __future__ import annotations

from datetime import datetime, timezone

from app.repositories import AnalysisRepository
from app.alert_conditions import RuleValidationResult
from app.schemas import AnalysisResult


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_watchlist_crud(client):
    create_response = client.post("/watchlist", json={"symbol": " msft "})

    assert create_response.status_code == 201
    assert create_response.json()["symbol"] == "MSFT"
    assert any(item["symbol"] == "MSFT" for item in client.get("/watchlist").json())

    delete_response = client.delete("/watchlist/MSFT")

    assert delete_response.status_code == 204
    assert not any(item["symbol"] == "MSFT" for item in client.get("/watchlist").json())


def test_custom_alert_condition_is_validated_and_saved(client, rule_validation_agent):
    response = client.post(
        "/alert-conditions",
        json={
            "symbol": "005930.KS",
            "user_rule": "Notify me when NVDA rises by 5 percent.",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["symbol"] == "005930.KS"
    assert body["required_tools"] == ["fetch_related_symbol_snapshot"]
    assert rule_validation_agent.calls == [
        ("Notify me when NVDA rises by 5 percent.", "005930.KS")
    ]

    listed = client.get("/alert-conditions")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [body["id"]]


def test_custom_alert_condition_rejection_returns_rewrite_guidance(client, rule_validation_agent):
    rule_validation_agent.result = RuleValidationResult(
        is_valid=False,
        validation_summary="The rule is too vague.",
        rewrite_guidance="Name a symbol and measurable trigger.",
    )

    response = client.post(
        "/alert-conditions",
        json={"symbol": "005930.KS", "user_rule": "Tell me when the mood is bad."},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["rewrite_guidance"] == "Name a symbol and measurable trigger."


def test_analysis_receives_enabled_custom_conditions(client, agent):
    client.post(
        "/alert-conditions",
        json={
            "symbol": "005930.KS",
            "user_rule": "Notify me when NVDA rises by 5 percent.",
        },
    )

    response = client.get("/stocks/005930.KS/analysis/latest")

    assert response.status_code == 200
    condition_ids = [condition.id for condition in agent.alert_conditions[0]]
    assert "custom.1" in condition_ids
    assert "price_move_abs_gte_3_percent" in condition_ids


def test_latest_analysis_returns_cached_result_without_external_calls(
    client, db_session, market_data, agent, alert_notifier
):
    AnalysisRepository(db_session).save(
        symbol="005930.KS",
        overall_judgment="neutral",
        summary="cached result",
        key_reasons=["cached reason"],
        risk_factors=[],
        support_levels={"latest_close": 72000},
        should_alert=False,
        triggered_alerts=[],
        alert_reason="No alert condition matched.",
        raw_result={"summary": "cached result"},
    )

    response = client.get("/stocks/005930.KS/analysis/latest")

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "005930.KS"
    assert body["summary"] == "cached result"
    assert body["raw_result"] == {"summary": "cached result"}
    assert market_data.calls == []
    assert agent.calls == []
    assert alert_notifier.messages == []


def test_latest_analysis_sends_pending_alert_for_cached_result(client, db_session, alert_notifier):
    AnalysisRepository(db_session).save(
        symbol="005930.KS",
        overall_judgment="상승",
        summary="cached alert",
        key_reasons=[],
        risk_factors=[],
        support_levels={},
        should_alert=True,
        triggered_alerts=["price_move_abs_gte_3_percent"],
        alert_reason="캐시된 알림 사유입니다.",
        raw_result={},
    )

    response = client.get("/stocks/005930.KS/analysis/latest")

    assert response.status_code == 200
    assert alert_notifier.messages == ["캐시된 알림 사유입니다."]
    stored = AnalysisRepository(db_session).get_latest("005930.KS")
    assert stored.alert_sent_at is not None

    client.get("/stocks/005930.KS/analysis/latest")
    assert alert_notifier.messages == ["캐시된 알림 사유입니다."]


def test_latest_analysis_sends_kakao_alert_reason_only_when_alert_triggered(
    client, agent, alert_notifier
):
    agent.result = AnalysisResult(
        symbol="005930.KS",
        analysis_time=datetime(2026, 5, 30, 1, tzinfo=timezone.utc),
        data_time=datetime(2026, 5, 30, tzinfo=timezone.utc),
        verdict="상승",
        summary="ignored for kakao",
        key_reasons=["ignored"],
        risk_factors=[],
        indicators={"latest_close": 72000},
        alert_triggered=True,
        matched_alert_conditions=["price_move_abs_gte_3_percent"],
        alert_reason="주가가 10% 이상 급등했습니다.",
    )

    response = client.get("/stocks/005930.KS/analysis/latest")

    assert response.status_code == 200
    assert alert_notifier.messages == ["주가가 10% 이상 급등했습니다."]


def test_latest_analysis_does_not_send_kakao_when_alert_not_triggered(client, alert_notifier):
    response = client.get("/stocks/005930.KS/analysis/latest")

    assert response.status_code == 200
    assert alert_notifier.messages == []


def test_latest_analysis_cache_miss_uses_fake_market_data_and_agent(
    client, db_session, market_data, agent, alert_notifier
):
    response = client.get("/stocks/005930.KS/analysis/latest")

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "005930.KS"
    assert body["overall_judgment"] == "neutral"
    assert body["summary"] == "steady"
    assert body["raw_result"]["summary"] == "steady"
    assert market_data.calls == ["005930.KS"]
    assert [call.symbol for call in agent.calls] == ["005930.KS"]
    assert AnalysisRepository(db_session).get_latest("005930.KS").summary == "steady"


def test_latest_analysis_market_data_empty_returns_error(client, market_data, market_data_empty_error):
    market_data.error = market_data_empty_error

    response = client.get("/stocks/005930.KS/analysis/latest")

    assert response.status_code == 502
    assert "no market data" in response.json()["detail"]


def test_latest_analysis_agent_failure_returns_error(client, agent, agent_failure_error):
    agent.error = agent_failure_error

    response = client.get("/stocks/005930.KS/analysis/latest")

    assert response.status_code == 502
    assert "Gemini analysis request failed" in response.json()["detail"]


def test_index_page_response(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'value="005930.KS"' in response.text
    assert "/stocks/" in response.text
