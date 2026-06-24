from __future__ import annotations

from datetime import datetime, timezone

from app.alert_conditions import CustomAlertCondition, DEFAULT_SYSTEM_ALERT_CONDITIONS
from app.analysis_graph import MainAnalysisAgent
from app.custom_rule_agent import CustomRuleContext
from app.schemas import AnalysisResult, MarketDataSnapshot


class RecordingMainModel:
    def __init__(self) -> None:
        self.conditions = []
        self.contexts = []

    def analyze(self, market_data, alert_conditions=None, custom_contexts=None) -> AnalysisResult:
        self.conditions = list(alert_conditions or [])
        self.contexts = list(custom_contexts or [])
        return AnalysisResult(
            symbol=market_data.symbol,
            analysis_time=datetime(2026, 6, 24, tzinfo=timezone.utc),
            data_time=market_data.data_time,
            verdict="neutral",
            summary="steady",
            key_reasons=[],
            risk_factors=[],
            indicators={},
            alert_triggered=False,
            matched_alert_conditions=[],
            alert_reason="",
        )


class RecordingCustomRuleAgent:
    def __init__(self) -> None:
        self.conditions = []

    def build_context(self, condition: CustomAlertCondition) -> CustomRuleContext:
        self.conditions.append(condition)
        return CustomRuleContext(
            condition_id=condition.id,
            user_rule=condition.user_rule,
            gathered_facts=["NVDA change_percent=5.00"],
        )


def test_main_analysis_graph_collects_custom_context_before_main_analysis(market_data: MarketDataSnapshot):
    main_model = RecordingMainModel()
    custom_rule_agent = RecordingCustomRuleAgent()
    agent = MainAnalysisAgent(main_model=main_model, custom_rule_agent=custom_rule_agent)
    custom_condition = CustomAlertCondition(
        id="custom.1",
        symbol="005930.KS",
        name="NVDA move",
        user_rule="Alert when NVDA rises by 5 percent.",
        validation_summary="valid",
        required_tools=["fetch_related_symbol_snapshot"],
        related_symbols=["NVDA"],
    )

    result = agent.analyze(
        market_data.snapshot,
        [*DEFAULT_SYSTEM_ALERT_CONDITIONS, custom_condition],
    )

    assert result.symbol == "005930.KS"
    assert custom_rule_agent.conditions == [custom_condition]
    assert [condition.id for condition in main_model.conditions] == [
        *[condition.id for condition in DEFAULT_SYSTEM_ALERT_CONDITIONS],
        "custom.1",
    ]
    assert main_model.contexts[0]["condition_id"] == "custom.1"
