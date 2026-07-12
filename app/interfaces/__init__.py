"""Application interfaces implemented by adapters."""

from app.interfaces.analysis import AgentConfigurationError, AnalysisAgent, AnalysisAgentError
from app.interfaces.market_data import MarketDataError, MarketDataProvider
from app.interfaces.notifications import AlertNotifier, AlertNotifyError
from app.interfaces.repositories import (
    AlertConditionRepository,
    AnalysisRepository,
    WatchlistRepository,
)

__all__ = [
    "AgentConfigurationError",
    "AnalysisAgent",
    "AnalysisAgentError",
    "AlertConditionRepository",
    "AlertNotifier",
    "AlertNotifyError",
    "AnalysisRepository",
    "MarketDataError",
    "MarketDataProvider",
    "WatchlistRepository",
]
