from __future__ import annotations

import json

import httpx
import pytest

from app.application.custom_rule_agent import CustomRuleContext
from app.domain.alert_conditions import CustomAlertCondition
from app.domain.models import AnalysisResult
from app.integrations.llm.gemini_alert_evaluation_model import (
    AlertEvaluationModelError,
    GeminiAlertEvaluationModel,
)


class RecordingClient:
    def __init__(self, text: str) -> None:
        self.text = text
        self.requests = []

    def post(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"candidates": [{"content": {"parts": [{"text": self.text}]}}]},
        )


def _inputs():
    analysis = AnalysisResult(
        id=12,
        symbol="005930.KS",
        overall_judgment="상승",
        summary="6.2% 상승",
        key_reasons=["거래량 증가"],
        support_levels={"change_percent": 6.2},
        shared_safe=True,
    )
    condition = CustomAlertCondition(
        id="custom.4",
        symbol="005930.KS",
        name="5% rise",
        user_rule="5% 이상 상승하면 알려줘",
        normalized_rule="price change >= 5%",
        validation_summary="measurable",
    )
    context = CustomRuleContext(
        condition_id=condition.id,
        user_rule=condition.user_rule,
        summary="추가 자료 없음",
    )
    return analysis, condition, context


def test_gemini_evaluation_model_parses_decision_without_user_delivery_data(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    client = RecordingClient(
        json.dumps(
            {
                "outcome": "matched",
                "reason": "6.2%가 기준을 넘었습니다.",
                "notification_message": "5% 상승 조건 충족",
                "evidence": ["stock_analysis.indicators.change_percent=6.2"],
            },
            ensure_ascii=False,
        )
    )
    model = GeminiAlertEvaluationModel(client=client)

    decision = model.evaluate(
        analysis=_inputs()[0], condition=_inputs()[1], custom_context=_inputs()[2]
    )

    assert decision.outcome == "matched"
    request_text = client.requests[0][1]["json"]["contents"][0]["parts"][0]["text"]
    assert "005930.KS" in request_text
    assert "5% 이상 상승하면 알려줘" in request_text
    assert "owner_id" not in request_text
    assert "connection_id" not in request_text
    assert "access_token" not in request_text
    generation_config = client.requests[0][1]["json"]["generationConfig"]
    assert generation_config["responseMimeType"] == "application/json"
    assert generation_config["responseSchema"]["properties"]["outcome"]["enum"] == [
        "matched",
        "not_matched",
        "indeterminate",
    ]
    assert generation_config["responseSchema"]["properties"]["notification_message"] == {
        "type": "string",
        "nullable": True,
        "description": "A concise Korean message for matched; null otherwise.",
    }
    assert "additionalProperties" not in generation_config["responseSchema"]


def test_gemini_evaluation_model_rejects_malformed_output(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    model = GeminiAlertEvaluationModel(client=RecordingClient("not-json"))

    with pytest.raises(AlertEvaluationModelError, match="schema"):
        model.evaluate(
            analysis=_inputs()[0], condition=_inputs()[1], custom_context=_inputs()[2]
        )
