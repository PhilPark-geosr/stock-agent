from __future__ import annotations

from typing import Literal, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app.application.custom_rule_agent import CustomRuleAgent, CustomRuleContext
from app.domain.alert_conditions import CustomAlertCondition
from app.domain.models import AnalysisResult


class AlertEvaluationDecision(BaseModel):
    outcome: Literal["matched", "not_matched", "indeterminate"]
    reason: str
    notification_message: str | None = None
    evidence: list[str] = Field(default_factory=list)


class UserAlertEvaluationError(RuntimeError):
    pass


class AlertEvaluationOutputError(RuntimeError):
    """Raised when a model responded but its decision output cannot be parsed."""


class AlertEvaluationModel(Protocol):
    def evaluate(
        self,
        *,
        analysis: AnalysisResult,
        condition: CustomAlertCondition,
        custom_context: CustomRuleContext,
        validation_errors: list[str] | None = None,
    ) -> AlertEvaluationDecision:
        ...


class UserAlertEvaluator(Protocol):
    def evaluate(
        self, *, analysis: AnalysisResult, condition: CustomAlertCondition
    ) -> AlertEvaluationDecision:
        ...


class UserAlertEvaluationState(TypedDict, total=False):
    analysis: AnalysisResult
    condition: CustomAlertCondition
    custom_context: CustomRuleContext
    decision: AlertEvaluationDecision
    validation_errors: list[str]
    attempts: int
    failure_reason: str
    decision_error: str | None


class LangGraphUserAlertEvaluator:
    def __init__(self, *, custom_rule_agent: CustomRuleAgent, evaluation_model: AlertEvaluationModel) -> None:
        self.custom_rule_agent = custom_rule_agent
        self.evaluation_model = evaluation_model
        self.graph = self._build_graph()

    def evaluate(
        self, *, analysis: AnalysisResult, condition: CustomAlertCondition
    ) -> AlertEvaluationDecision:
        result = self.graph.invoke(
            {"analysis": analysis, "condition": condition, "attempts": 0, "validation_errors": []}
        )
        if result.get("failure_reason"):
            raise UserAlertEvaluationError(result["failure_reason"])
        return result["decision"]

    def _build_graph(self):
        graph = StateGraph(UserAlertEvaluationState)
        graph.add_node("custom_rule_agent", self._run_custom_rule_agent)
        graph.add_node("evaluate_condition", self._evaluate_condition)
        graph.add_node("validate_decision", self._validate_decision)
        graph.add_node("evaluation_failed", self._evaluation_failed)
        graph.add_edge(START, "custom_rule_agent")
        graph.add_edge("custom_rule_agent", "evaluate_condition")
        graph.add_edge("evaluate_condition", "validate_decision")
        graph.add_conditional_edges(
            "validate_decision",
            self._route_after_validation,
            {"valid": END, "retry": "evaluate_condition", "failed": "evaluation_failed"},
        )
        graph.add_edge("evaluation_failed", END)
        return graph.compile()

    def _run_custom_rule_agent(self, state: UserAlertEvaluationState) -> dict:
        return {"custom_context": self.custom_rule_agent.build_context(state["condition"])}

    def _evaluate_condition(self, state: UserAlertEvaluationState) -> dict:
        try:
            decision = self.evaluation_model.evaluate(
                analysis=state["analysis"],
                condition=state["condition"],
                custom_context=state["custom_context"],
                validation_errors=state.get("validation_errors") or None,
            )
        except AlertEvaluationOutputError as exc:
            return {
                "decision_error": str(exc),
                "attempts": state.get("attempts", 0) + 1,
            }
        return {
            "decision": decision,
            "decision_error": None,
            "attempts": state.get("attempts", 0) + 1,
        }

    @staticmethod
    def _validate_decision(state: UserAlertEvaluationState) -> dict:
        if state.get("decision_error"):
            return {"validation_errors": [state["decision_error"]]}
        decision = state["decision"]
        errors: list[str] = []
        if not decision.reason.strip():
            errors.append("evaluation requires a reason")
        if decision.outcome == "matched":
            if not (decision.notification_message or "").strip():
                errors.append("matched evaluation requires a notification message")
        elif decision.notification_message:
            errors.append("only matched evaluation can have a notification message")
        return {"validation_errors": errors}

    @staticmethod
    def _route_after_validation(state: UserAlertEvaluationState) -> str:
        if not state.get("validation_errors"):
            return "valid"
        if state.get("attempts", 0) < 2:
            return "retry"
        return "failed"

    @staticmethod
    def _evaluation_failed(state: UserAlertEvaluationState) -> dict:
        return {"failure_reason": "; ".join(state.get("validation_errors", []))}
