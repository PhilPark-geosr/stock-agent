"""Analysis agent interface."""

from __future__ import annotations

from typing import Any, Iterable, Protocol

from app.domain.alert_conditions import AlertConditionUnion
from app.schemas import AnalysisResult, MarketDataSnapshot


class AgentConfigurationError(RuntimeError):
    """Raised when an analysis agent adapter is not configured."""


class AnalysisAgentError(RuntimeError):
    """Raised when analysis generation fails."""


class AnalysisAgent(Protocol):
    """Interface for structured stock analysis."""

    def analyze(
        self,
        market_data: MarketDataSnapshot,
        alert_conditions: Iterable[AlertConditionUnion] | None = None,
        custom_contexts: Iterable[dict[str, Any]] | None = None,
    ) -> AnalysisResult:
        ...
