"""Gather context for validated custom alert conditions."""

from __future__ import annotations

import logging
import os
from typing import Annotated, Any, Protocol, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

from app.alert_conditions import CustomAlertCondition
from app.custom_rule_tools.news import fetch_symbol_news
from app.custom_rule_tools.registry import get_custom_rule_tools
from app.market_data import MarketDataProvider, YFinanceMarketDataProvider
from app.schemas import model_to_dict

logger = logging.getLogger(__name__)


class CustomRuleAgentError(RuntimeError):
    """Raised when context for a validated custom rule cannot be gathered."""


class CustomRuleContext(BaseModel):
    condition_id: str
    user_rule: str
    gathered_facts: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""


class CustomRuleAgent(Protocol):
    def build_context(self, condition: CustomAlertCondition) -> CustomRuleContext:
        """Collect context using only the tools approved during rule validation."""


class CustomRuleAgentState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    condition: CustomAlertCondition
    custom_context: CustomRuleContext


class LangGraphCustomRuleAgent:
    """Use LLM tool-calling to gather custom-rule context at analysis time."""

    def __init__(
        self,
        *,
        llm: Any | None = None,
        tools: list[Any] | None = None,
        recursion_limit: int = 8,
    ) -> None:
        self.tools = tools or get_custom_rule_tools()
        self._llm = llm
        self._bound_llm: Any | None = None
        self.recursion_limit = recursion_limit
        self.graph = self._build_graph()

    def build_context(self, condition: CustomAlertCondition) -> CustomRuleContext:
        logger.info(
            "CustomRuleAgent graph start condition_id=%s symbol=%s rule_preview=%s",
            condition.id,
            condition.symbol,
            _preview(condition.user_rule),
        )
        result = self.graph.invoke(
            {
                "condition": condition,
                "messages": [
                    SystemMessage(
                        content=(
                            "You gather evidence for a user's stock alert rule. "
                            "Call only the provided tools, and only when external data is needed. "
                            "The final answer must briefly summarize the gathered evidence; "
                            "do not decide whether the alert should fire."
                        )
                    ),
                    HumanMessage(
                        content=(
                            f"target_symbol: {condition.symbol}\n"
                            f"condition_id: {condition.id}\n"
                            f"user_rule: {condition.user_rule}"
                        )
                    ),
                ],
            },
            config={"recursion_limit": self.recursion_limit},
        )
        context = result["custom_context"]
        logger.info(
            "CustomRuleAgent graph end condition_id=%s facts=%d tool_results=%d summary_chars=%d",
            context.condition_id,
            len(context.gathered_facts),
            len(context.evidence.get("tool_results", [])),
            len(context.summary or ""),
        )
        return context

    def _build_graph(self):
        graph = StateGraph(CustomRuleAgentState)
        graph.add_node("custom_rule_llm", self._call_llm)
        graph.add_node("tools", ToolNode(self.tools))
        graph.add_node("finalize_context", self._finalize_context)

        graph.set_entry_point("custom_rule_llm")
        graph.add_conditional_edges(
            "custom_rule_llm",
            self._route_after_llm,
            {
                "tools": "tools",
                "finalize": "finalize_context",
            },
        )
        graph.add_edge("tools", "custom_rule_llm")
        graph.add_edge("finalize_context", END)
        return graph.compile()

    def _call_llm(self, state: CustomRuleAgentState) -> dict:
        condition = state["condition"]
        logger.info(
            "CustomRuleAgent node=custom_rule_llm condition_id=%s messages=%d",
            condition.id,
            len(state.get("messages", [])),
        )
        response = self._get_bound_llm().invoke(state["messages"])
        tool_calls = getattr(response, "tool_calls", None) or []
        if tool_calls:
            logger.info(
                "CustomRuleAgent LLM requested tool_calls condition_id=%s tools=%s",
                condition.id,
                [_tool_call_name(tool_call) for tool_call in tool_calls],
            )
        else:
            logger.info(
                "CustomRuleAgent LLM returned final response condition_id=%s content_chars=%d",
                condition.id,
                len(str(getattr(response, "content", "") or "")),
            )
        return {"messages": [response]}

    def _get_bound_llm(self) -> Any:
        if self._bound_llm is None:
            logger.info(
                "CustomRuleAgent binding tools tools=%s",
                [_tool_name(tool) for tool in self.tools],
            )
            self._bound_llm = (self._llm or build_custom_rule_llm()).bind_tools(self.tools)
        return self._bound_llm

    @staticmethod
    def _route_after_llm(state: CustomRuleAgentState) -> str:
        last_message = state["messages"][-1]
        if getattr(last_message, "tool_calls", None):
            logger.info("CustomRuleAgent route=tools")
            return "tools"
        logger.info("CustomRuleAgent route=finalize")
        return "finalize"

    @staticmethod
    def _finalize_context(state: CustomRuleAgentState) -> dict:
        condition = state["condition"]
        final_message = state["messages"][-1]
        tool_messages = [
            message for message in state["messages"] if isinstance(message, ToolMessage)
        ]
        gathered_facts = [
            f"{message.name or 'tool'}: {message.content}" for message in tool_messages
        ]
        logger.info(
            "CustomRuleAgent node=finalize_context condition_id=%s tool_messages=%d",
            condition.id,
            len(tool_messages),
        )
        return {
            "custom_context": CustomRuleContext(
                condition_id=condition.id,
                user_rule=condition.user_rule,
                gathered_facts=gathered_facts,
                evidence={
                    "tool_results": [
                        {
                            "tool_name": message.name,
                            "tool_call_id": message.tool_call_id,
                            "content": message.content,
                        }
                        for message in tool_messages
                    ],
                    "messages": [
                        {
                            "type": message.type,
                            "content": getattr(message, "content", ""),
                        }
                        for message in state["messages"]
                        if getattr(message, "content", "")
                    ],
                },
                summary=str(getattr(final_message, "content", "")),
            )
        }


def build_custom_rule_llm() -> Any:
    """Build the LangChain Gemini chat model lazily so imports do not break startup."""

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError as exc:
        raise CustomRuleAgentError(
            "langchain-google-genai is required for LangGraphCustomRuleAgent"
        ) from exc

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise CustomRuleAgentError("GEMINI_API_KEY is required for LangGraphCustomRuleAgent")

    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    logger.info("CustomRuleAgent building Gemini chat model model=%s", model)
    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=api_key,
    )


class DefaultCustomRuleAgent:
    def __init__(self, *, market_data_provider: MarketDataProvider | None = None) -> None:
        self.market_data_provider = market_data_provider or YFinanceMarketDataProvider()

    def build_context(self, condition: CustomAlertCondition) -> CustomRuleContext:
        gathered_facts: list[str] = []
        evidence: dict[str, Any] = {}

        if "fetch_related_symbol_snapshot" in condition.required_tools:
            snapshots: dict[str, Any] = {}
            for symbol in condition.related_symbols:
                snapshot = self.market_data_provider.fetch(symbol)
                snapshots[symbol] = model_to_dict(snapshot)
                change_percent = snapshot.indicators.change_percent
                if change_percent is not None:
                    gathered_facts.append(f"{symbol} change_percent={change_percent:.2f}")
            evidence["related_symbol_snapshots"] = snapshots

        if "fetch_symbol_news" in condition.required_tools:
            news = {
                symbol: _fetch_symbol_news(symbol)
                for symbol in condition.news_symbols or [condition.symbol]
            }
            evidence["symbol_news"] = news
            gathered_facts.extend(
                f"{symbol} recent_news_count={len(items)}" for symbol, items in news.items()
            )

        return CustomRuleContext(
            condition_id=condition.id,
            user_rule=condition.user_rule,
            gathered_facts=gathered_facts,
            evidence=evidence,
        )


def _fetch_symbol_news(symbol: str) -> list[dict[str, Any]]:
    try:
        return fetch_symbol_news.invoke({"symbol": symbol})
    except Exception as exc:
        raise CustomRuleAgentError(f"failed to fetch news for {symbol}") from exc


def _preview(text: str, *, limit: int = 120) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def _tool_name(tool: Any) -> str:
    return str(getattr(tool, "name", None) or getattr(tool, "__name__", tool.__class__.__name__))


def _tool_call_name(tool_call: Any) -> str:
    if isinstance(tool_call, dict):
        return str(tool_call.get("name", "unknown"))
    return str(getattr(tool_call, "name", "unknown"))
