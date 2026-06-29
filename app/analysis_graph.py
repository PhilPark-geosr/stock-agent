"""LangGraph orchestration for structured alert-condition analysis."""

from __future__ import annotations

import logging
from typing import Protocol, TypedDict

from langgraph.graph import END, StateGraph

from app.alert_conditions import AlertConditionUnion, CustomAlertCondition
from app.custom_rule_agent import CustomRuleAgent
from app.schemas import AnalysisResult, MarketDataSnapshot, model_to_dict

logger = logging.getLogger(__name__)


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

        conditions = alert_conditions or []
        logger.info(
            "MainAnalysisAgent graph start symbol=%s alert_conditions=%d",
            market_data.symbol,
            len(conditions),
        )
        result = self.graph.invoke(
            {
                "market_data": market_data,
                "alert_conditions": conditions,
            }
        )
        analysis_result = result["analysis_result"]
        logger.info(
            "MainAnalysisAgent graph end symbol=%s alert_triggered=%s matched=%s",
            analysis_result.symbol,
            analysis_result.alert_triggered,
            analysis_result.matched_alert_conditions,
        )
        return analysis_result

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
        logger.info(
            "MainAnalysisAgent node=split_conditions system=%d custom=%d",
            len(system_conditions),
            len(custom_conditions),
        )
        return {
            "system_conditions": system_conditions,
            "custom_conditions": custom_conditions,
        }

    @staticmethod
    def _should_run_custom_rule_agent(state: AnalysisGraphState) -> str:
        route = "custom" if state.get("custom_conditions") else "main"
        logger.info("MainAnalysisAgent route after split_conditions=%s", route)
        return route

    def _run_custom_rule_agent(self, state: AnalysisGraphState) -> dict:
        contexts = []
        custom_conditions = state.get("custom_conditions", [])
        logger.info(
            "MainAnalysisAgent node=custom_rule_agent conditions=%d",
            len(custom_conditions),
        )
        for condition in custom_conditions:
            logger.info(
                "MainAnalysisAgent calls CustomRuleAgent condition_id=%s symbol=%s",
                condition.id,
                condition.symbol,
            )
            context = self.custom_rule_agent.build_context(condition)
            contexts.append(model_to_dict(context))
            logger.info(
                "MainAnalysisAgent received CustomRuleContext condition_id=%s facts=%d summary_chars=%d",
                context.condition_id,
                len(context.gathered_facts),
                len(context.summary or ""),
            )
        return {"custom_contexts": contexts}

    def _run_main_analysis_agent(self, state: AnalysisGraphState) -> dict:
        alert_conditions = state.get("system_conditions", []) + state.get("custom_conditions", [])
        custom_contexts = state.get("custom_contexts", [])
        logger.info(
            "MainAnalysisAgent node=main_analysis_agent alert_conditions=%d custom_contexts=%d",
            len(alert_conditions),
            len(custom_contexts),
        )
        result = self.main_model.analyze(
            market_data=state["market_data"],
            alert_conditions=alert_conditions,
            custom_contexts=custom_contexts,
        )
        logger.info(
            "MainAnalysisAgent main model returned symbol=%s alert_triggered=%s matched=%s",
            result.symbol,
            result.alert_triggered,
            result.matched_alert_conditions,
        )
        return {"analysis_result": result}
