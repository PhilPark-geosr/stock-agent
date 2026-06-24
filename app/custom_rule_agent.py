"""Gather context for validated custom alert conditions."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.alert_conditions import CustomAlertCondition
from app.market_data import MarketDataProvider, YFinanceMarketDataProvider
from app.schemas import model_to_dict


class CustomRuleAgentError(RuntimeError):
    """Raised when context for a validated custom rule cannot be gathered."""


class CustomRuleContext(BaseModel):
    condition_id: str
    user_rule: str
    gathered_facts: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)


class CustomRuleAgent(Protocol):
    def build_context(self, condition: CustomAlertCondition) -> CustomRuleContext:
        """Collect context using only the tools approved during rule validation."""


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
        import yfinance as yf
    except ImportError as exc:
        raise CustomRuleAgentError("yfinance is required to fetch symbol news") from exc

    try:
        raw_items = yf.Ticker(symbol).news or []
    except Exception as exc:
        raise CustomRuleAgentError(f"failed to fetch news for {symbol}") from exc

    return [
        {
            "title": item.get("title"),
            "publisher": item.get("publisher"),
            "link": item.get("link"),
            "published_at": item.get("providerPublishTime"),
        }
        for item in raw_items[:10]
    ]
