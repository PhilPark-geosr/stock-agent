from __future__ import annotations

from datetime import datetime, timezone

from app.domain.briefings import compare_judgments, normalize_judgment
from app.schemas import AnalysisResult


def test_judgment_normalization_and_comparison():
    assert normalize_judgment("강력 매수") == "STRONG_BUY"
    assert normalize_judgment("관망") == "HOLD"
    assert compare_judgments("BUY", "HOLD") == ("COMPARABLE", True, 1)
    assert compare_judgments("UNKNOWN", "BUY") == ("NOT_COMPARABLE", False, 0)


def test_pre_and_post_market_briefings_are_idempotent_and_user_scoped(client, agent):
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
    assert pre_body["items"][0]["comparison_status"] == "NOT_COMPARABLE"
    assert pre_body["deliveries"][0]["status"] == "SENT"
    assert pre_body["deliveries"][0]["attempt_count"] == 1

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
    client.post("/watchlist", headers={"X-User-Id": "alice"}, json={"symbol": "MSFT"})

    assert len(client.get("/watchlist", headers={"X-User-Id": "alice"}).json()) == 1
    assert client.get("/watchlist", headers={"X-User-Id": "bob"}).json() == []


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
