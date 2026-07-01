from __future__ import annotations

from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from app.alert_conditions import CustomAlertCondition
from app.custom_rule_agent import (
    CustomRuleAgentError,
    LangGraphCustomRuleAgent,
    build_custom_rule_llm,
)


@tool
def fake_fetch_related_symbol_snapshot(symbol: str) -> dict:
    """Fetch fake market data for a stock symbol."""

    return {"symbol": symbol, "indicators": {"change_percent": 5.25}}


class ToolCallingFakeLlm:
    def __init__(self) -> None:
        self.bound_tools = []
        self.calls = []

    def bind_tools(self, tools):
        self.bound_tools = list(tools)
        return self

    def invoke(self, messages):
        self.calls.append(list(messages))
        if not any(message.type == "tool" for message in messages):
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "fake_fetch_related_symbol_snapshot",
                        "args": {"symbol": "NVDA"},
                        "id": "call_1",
                    }
                ],
            )
        return AIMessage(content="NVDA is up 5.25 percent.")


class NoToolFakeLlm:
    def bind_tools(self, tools):
        self.bound_tools = list(tools)
        return self

    def invoke(self, messages):
        return AIMessage(content="No extra data is needed.")


def test_langgraph_custom_rule_agent_runs_llm_requested_tool():
    llm = ToolCallingFakeLlm()
    agent = LangGraphCustomRuleAgent(
        llm=llm,
        tools=[fake_fetch_related_symbol_snapshot],
    )
    condition = CustomAlertCondition(
        id="custom.1",
        symbol="005930.KS",
        name="NVDA move",
        user_rule="Alert when NVDA rises by 5 percent.",
        validation_summary="valid",
    )

    context = agent.build_context(condition)

    assert llm.bound_tools == [fake_fetch_related_symbol_snapshot]
    assert len(llm.calls) == 2
    assert context.condition_id == "custom.1"
    assert context.summary == "NVDA is up 5.25 percent."
    assert context.gathered_facts
    assert context.evidence["tool_results"][0]["tool_name"] == "fake_fetch_related_symbol_snapshot"
    assert "5.25" in context.evidence["tool_results"][0]["content"]


def test_langgraph_custom_rule_agent_can_finalize_without_tools():
    agent = LangGraphCustomRuleAgent(
        llm=NoToolFakeLlm(),
        tools=[fake_fetch_related_symbol_snapshot],
    )
    condition = CustomAlertCondition(
        id="custom.2",
        symbol="005930.KS",
        name="Simple rule",
        user_rule="Alert when Samsung moves sharply.",
        validation_summary="valid",
    )

    context = agent.build_context(condition)

    assert context.summary == "No extra data is needed."
    assert context.gathered_facts == []
    assert context.evidence["tool_results"] == []


def test_build_custom_rule_llm_reports_missing_optional_dependency(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    try:
        build_custom_rule_llm()
    except CustomRuleAgentError as exc:
        assert "LangGraphCustomRuleAgent" in str(exc)
    else:
        raise AssertionError("build_custom_rule_llm should require Gemini configuration")
