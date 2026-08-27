"""Application interfaces implemented by adapters."""

from app.interfaces.analysis import AgentConfigurationError, AnalysisAgent, AnalysisAgentError
from app.interfaces.market_data import MarketDataError, MarketDataProvider
from app.interfaces.notifications import NotificationSender, AlertNotifyError
from app.interfaces.repositories import (
    AlertConditionRepository,
    AnalysisRepository,
    WatchlistRepository,
    NotificationConnectionRepository,
    NotificationDeliveryRepository,
)
from app.interfaces.rule_validation import RuleValidationAgent, RuleValidationError

__all__ = [
    "AgentConfigurationError",
    "AnalysisAgent",
    "AnalysisAgentError",
    "AlertConditionRepository",
    "NotificationSender",
    "AlertNotifyError",
    "AnalysisRepository",
    "MarketDataError",
    "MarketDataProvider",
    "RuleValidationAgent",
    "RuleValidationError",
    "WatchlistRepository",
    "NotificationConnectionRepository",
    "NotificationDeliveryRepository",
]
