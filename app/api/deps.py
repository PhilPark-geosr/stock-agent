"""FastAPI dependency providers."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.container import (
    build_analysis_service,
    build_briefing_delivery_service,
    build_briefing_service,
    get_alert_notifier,
    get_analysis_agent,
    get_market_data_provider,
)
from app.core.database import get_db
from app.integrations.llm.gemini_rule_validation_agent import GeminiRuleValidationAgent
from app.interfaces.analysis import AnalysisAgent
from app.interfaces.market_data import MarketDataProvider
from app.interfaces.notifications import AlertNotifier
from app.interfaces.repositories import (
    AlertConditionRepository as AlertConditionRepositoryInterface,
    WatchlistRepository as WatchlistRepositoryInterface,
)
from app.interfaces.rule_validation import RuleValidationAgent
from app.repositories import AlertConditionRepository, WatchlistRepository
from app.services import AnalysisProvider, BriefingService
from app.services.briefing_delivery import BriefingDeliveryService


def get_rule_validation_agent() -> RuleValidationAgent:
    return GeminiRuleValidationAgent()


def get_analysis_service(
    db: Session = Depends(get_db),
    market_data_provider: MarketDataProvider = Depends(get_market_data_provider),
    agent: AnalysisAgent = Depends(get_analysis_agent),
    alert_notifier: AlertNotifier = Depends(get_alert_notifier),
) -> AnalysisProvider:
    return build_analysis_service(
        db,
        market_data_provider=market_data_provider,
        agent=agent,
        alert_notifier=alert_notifier,
    )


def get_current_user_id(
    user_id: str = Header(default="default", alias="X-User-Id"),
) -> str:
    normalized = user_id.strip()
    if not normalized or len(normalized) > 64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid X-User-Id header",
        )
    return normalized


def get_briefing_service(
    db: Session = Depends(get_db),
    analysis_service: AnalysisProvider = Depends(get_analysis_service),
) -> BriefingService:
    return build_briefing_service(db, analysis_service=analysis_service)


def get_briefing_delivery_service(
    db: Session = Depends(get_db),
    alert_notifier: AlertNotifier = Depends(get_alert_notifier),
) -> BriefingDeliveryService:
    return build_briefing_delivery_service(db, notifier=alert_notifier)


def get_watchlist_repository(db: Session = Depends(get_db)) -> WatchlistRepositoryInterface:
    return WatchlistRepository(db)


def get_alert_condition_repository(db: Session = Depends(get_db)) -> AlertConditionRepositoryInterface:
    return AlertConditionRepository(db)
