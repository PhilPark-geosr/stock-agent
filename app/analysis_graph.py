"""LangGraph orchestration for structured alert-condition analysis."""

from __future__ import annotations

from typing import Protocol, TypedDict

from langgraph.graph import END, StateGraph

from app.alert_conditions import AlertConditionUnion, CustomAlertCondition
from app.custom_rule_agent import CustomRuleAgent
from app.schemas import AnalysisResult, MarketDataSnapshot, model_to_dict


class MainAnalysisModel(Protocol):
    def analyze(
        self,
        market_data: MarketDataSnapshot,
        alert_conditions: list[AlertConditionUnion] | None = None,
        custom_contexts: list[dict] | None = None,
    ) -> AnalysisResult:
        ...


class AnalysisGraphState(TypedDict, total=False):
    market_data: MarketDataSnapshot
    alert_conditions: list[AlertConditionUnion]
    system_conditions: list[AlertConditionUnion]
    custom_conditions: list[CustomAlertCondition]
    custom_contexts: list[dict]
    analysis_result: AnalysisResult


class MainAnalysisAgent:
    """Run validated custom-rule context gathering before final LLM analysis."""

    def __init__(self, *, main_model: MainAnalysisModel, custom_rule_agent: CustomRuleAgent) -> None:
        self.main_model = main_model
        self.custom_rule_agent = custom_rule_agent
        self.graph = self._build_graph()

    def analyze(
        self,
        market_data: MarketDataSnapshot,
        alert_conditions: list[AlertConditionUnion] | None = None,
        custom_contexts: list[dict] | None = None,
    ) -> AnalysisResult:
        if custom_contexts:
            raise ValueError("MainAnalysisAgent builds custom contexts internally")

        result = self.graph.invoke(
            {
                "market_data": market_data,
                "alert_conditions": alert_conditions or [],
            }
        )
        return result["analysis_result"]

    def _build_graph(self):
        graph = StateGraph(AnalysisGraphState)
        graph.add_node("split_conditions", self._split_conditions)
        graph.add_node("custom_rule_agent", self._run_custom_rule_agent)
        graph.add_node("main_analysis_agent", self._run_main_analysis_agent)

        graph.set_entry_point("split_conditions")
        graph.add_conditional_edges(
            "split_conditions",
            self._should_run_custom_rule_agent,
            {
                "custom": "custom_rule_agent",
                "main": "main_analysis_agent",
            },
        )
        graph.add_edge("custom_rule_agent", "main_analysis_agent")
        graph.add_edge("main_analysis_agent", END)
        return graph.compile()

    @staticmethod
    def _split_conditions(state: AnalysisGraphState) -> dict:
        system_conditions = [
            condition for condition in state["alert_conditions"] if condition.kind == "system"
        ]
        custom_conditions = [
            condition for condition in state["alert_conditions"] if condition.kind == "custom"
        ]
        return {
            "system_conditions": system_conditions,
            "custom_conditions": custom_conditions,
        }

    @staticmethod
    def _should_run_custom_rule_agent(state: AnalysisGraphState) -> str:
        return "custom" if state.get("custom_conditions") else "main"

    def _run_custom_rule_agent(self, state: AnalysisGraphState) -> dict:
        contexts = [
            model_to_dict(self.custom_rule_agent.build_context(condition))
            for condition in state.get("custom_conditions", [])
        ]
        return {"custom_contexts": contexts}

    def _run_main_analysis_agent(self, state: AnalysisGraphState) -> dict:
        result = self.main_model.analyze(
            market_data=state["market_data"],
            alert_conditions=state.get("system_conditions", []) + state.get("custom_conditions", []),
            custom_contexts=state.get("custom_contexts", []),
        )
        return {"analysis_result": result}
