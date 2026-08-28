from __future__ import annotations

import pytest

from app.application.custom_rule_agent import CustomRuleContext
from app.application.user_alert_evaluator import (
    AlertEvaluationDecision,
    AlertEvaluationOutputError,
    LangGraphUserAlertEvaluator,
    UserAlertEvaluationError,
)
from app.domain.alert_conditions import CustomAlertCondition
from app.domain.models import AnalysisResult


def _analysis() -> AnalysisResult:
    return AnalysisResult(
        id=7,
        symbol="005930.KS",
        overall_judgment="상승",
        summary="6.2% 상승",
        support_levels={"change_percent": 6.2},
        shared_safe=True,
    )


def _condition() -> CustomAlertCondition:
    return CustomAlertCondition(
        id="custom.9",
        symbol="005930.KS",
        name="5% rise",
        user_rule="5% 이상 상승하면 알려줘",
        normalized_rule="price change >= 5%",
        validation_summary="measurable",
    )


class RecordingContextAgent:
    def __init__(self) -> None:
        self.conditions = []

    def build_context(self, condition):
        self.conditions.append(condition)
        return CustomRuleContext(
            condition_id=condition.id,
            user_rule=condition.user_rule,
            gathered_facts=["related market was stable"],
            summary="supplemental evidence",
        )


class SequenceEvaluationModel:
    def __init__(self, *decisions) -> None:
        self.decisions = list(decisions)
        self.calls = []

    def evaluate(self, *, analysis, condition, custom_context, validation_errors=None):
        self.calls.append((analysis, condition, custom_context, list(validation_errors or [])))
        return self.decisions.pop(0)


class MalformedThenValidModel(SequenceEvaluationModel):
    def evaluate(self, *, analysis, condition, custom_context, validation_errors=None):
        self.calls.append((analysis, condition, custom_context, list(validation_errors or [])))
        if len(self.calls) == 1:
            raise AlertEvaluationOutputError("decision JSON did not match schema")
        return self.decisions.pop(0)


def test_evaluator_always_gathers_custom_context_before_deciding():
    context_agent = RecordingContextAgent()
    model = SequenceEvaluationModel(
        AlertEvaluationDecision(
            outcome="not_matched",
            reason="상승률이 기준보다 낮습니다.",
            evidence=["analysis.change_percent=2.1"],
        )
    )
    evaluator = LangGraphUserAlertEvaluator(
        custom_rule_agent=context_agent,
        evaluation_model=model,
    )

    decision = evaluator.evaluate(analysis=_analysis(), condition=_condition())

    assert decision.outcome == "not_matched"
    assert context_agent.conditions == [_condition()]
    assert model.calls[0][0] is not None
    assert model.calls[0][2].summary == "supplemental evidence"


def test_evaluator_retries_one_invalid_decision_with_validation_feedback():
    model = SequenceEvaluationModel(
        AlertEvaluationDecision(outcome="matched", reason="", notification_message=None),
        AlertEvaluationDecision(
            outcome="matched",
            reason="6.2%가 5%를 넘었습니다.",
            notification_message="5% 상승 조건을 충족했습니다.",
        ),
    )
    evaluator = LangGraphUserAlertEvaluator(
        custom_rule_agent=RecordingContextAgent(),
        evaluation_model=model,
    )

    decision = evaluator.evaluate(analysis=_analysis(), condition=_condition())

    assert decision.notification_message == "5% 상승 조건을 충족했습니다."
    assert len(model.calls) == 2
    assert model.calls[1][3] == [
        "evaluation requires a reason",
        "matched evaluation requires a notification message",
    ]


def test_evaluator_fails_after_second_invalid_decision():
    invalid = AlertEvaluationDecision(
        outcome="not_matched",
        reason="",
        notification_message="발송하면 안 되는 메시지",
    )
    evaluator = LangGraphUserAlertEvaluator(
        custom_rule_agent=RecordingContextAgent(),
        evaluation_model=SequenceEvaluationModel(invalid, invalid),
    )

    with pytest.raises(UserAlertEvaluationError, match="evaluation requires a reason"):
        evaluator.evaluate(analysis=_analysis(), condition=_condition())


def test_evaluator_retries_one_malformed_model_output():
    model = MalformedThenValidModel(
        AlertEvaluationDecision(outcome="not_matched", reason="기준 미달")
    )
    evaluator = LangGraphUserAlertEvaluator(
        custom_rule_agent=RecordingContextAgent(), evaluation_model=model
    )

    decision = evaluator.evaluate(analysis=_analysis(), condition=_condition())

    assert decision.outcome == "not_matched"
    assert model.calls[1][3] == ["decision JSON did not match schema"]


def test_evaluator_does_not_retry_transport_errors():
    class TransportFailureModel(SequenceEvaluationModel):
        def evaluate(self, **kwargs):
            self.calls.append(kwargs)
            raise RuntimeError("transport unavailable")

    model = TransportFailureModel()
    evaluator = LangGraphUserAlertEvaluator(
        custom_rule_agent=RecordingContextAgent(), evaluation_model=model
    )

    with pytest.raises(RuntimeError, match="transport unavailable"):
        evaluator.evaluate(analysis=_analysis(), condition=_condition())
    assert len(model.calls) == 1
