"""Application composition root."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Callable

from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.application.analysis_graph import MainAnalysisAgent
from app.application.custom_rule_agent import CustomRuleAgent, LangGraphCustomRuleAgent
from app.application.system_alerts import NoOpSystemAlertDispatcher, SystemAlertDispatcher
from app.application.user_alert_evaluator import LangGraphUserAlertEvaluator
from app.application.user_alerts import UserAlertDispatcher
from app.core.scheduler_config import scheduler_settings
from app.core.trading_window import is_alert_window
from app.integrations.llm.gemini_analysis_agent import GeminiAnalysisAgent
from app.integrations.yfinance_market_data_provider import YFinanceMarketDataProvider
from app.interfaces.analysis import AnalysisAgent
from app.interfaces.market_data import MarketDataProvider
from app.repositories import (
    AnalysisRepository as SqlAlchemyAnalysisRepository,
    WatchlistRepository as SqlAlchemyWatchlistRepository,
)
from app.services import AnalysisService
from app.integrations.kakao_auth import kakao_settings
from app.integrations.kakao_notify import KakaoNotificationSender
from app.repositories.notifications import (
    SqlAlchemyAlertEvaluationRepository,
    SqlAlchemyNotificationConnectionRepository,
    SqlAlchemyNotificationDeliveryRepository,
    SqlAlchemyUserAlertEvaluationTargetQuery,
)
from app.integrations.llm.gemini_alert_evaluation_model import GeminiAlertEvaluationModel


def build_alert_window_checker() -> Callable[[datetime], bool]:
    def checker(now: datetime) -> bool:
        settings = scheduler_settings()
        return is_alert_window(
            now,
            start_hour=int(settings["market_start_hour"]),
            end_hour=int(settings["market_end_hour"]),
            tz_name=str(settings["timezone"]),
        )

    return checker


def build_analysis_service(
    db: Session,
    *,
    market_data_provider: MarketDataProvider | None = None,
    agent: AnalysisAgent | None = None,
    alert_window_checker: Callable[[datetime], bool] | None = None,
    now_provider: Callable[[], datetime] | None = None,
    system_alert_dispatcher=None,
    user_alert_dispatcher=None,
) -> AnalysisService:
    dispatcher = system_alert_dispatcher or build_system_alert_dispatcher(db)
    custom_dispatcher = user_alert_dispatcher or build_user_alert_dispatcher(db)
    return AnalysisService(
        analysis_repository=SqlAlchemyAnalysisRepository(db),
        watchlist_repository=SqlAlchemyWatchlistRepository(db),
        market_data_provider=market_data_provider or get_market_data_provider(),
        agent=agent or get_analysis_agent(),
        system_alert_dispatcher=dispatcher,
        user_alert_dispatcher=custom_dispatcher,
        now_provider=now_provider,
    )


def build_system_alert_dispatcher(db: Session):
    key = os.getenv("NOTIFICATION_TOKEN_FERNET_KEY")
    settings = kakao_settings()
    if not key or not settings["rest_api_key"]:
        return NoOpSystemAlertDispatcher()
    try:
        cipher = Fernet(key.encode())
    except (ValueError, TypeError):
        return NoOpSystemAlertDispatcher()

    connections = SqlAlchemyNotificationConnectionRepository(db, cipher)
    return SystemAlertDispatcher(
        watchlist_repository=SqlAlchemyWatchlistRepository(db),
        connection_repository=connections,
        delivery_repository=SqlAlchemyNotificationDeliveryRepository(db),
        sender=KakaoNotificationSender(
            connections,
            rest_api_key=str(settings["rest_api_key"]),
            client_secret=settings["client_secret"],
        ),
    )


def build_user_alert_dispatcher(db: Session):
    key = os.getenv("NOTIFICATION_TOKEN_FERNET_KEY")
    cipher = None
    if key:
        try:
            cipher = Fernet(key.encode())
        except (ValueError, TypeError):
            cipher = None
    connections = SqlAlchemyNotificationConnectionRepository(db, cipher)
    settings = kakao_settings()
    sender = None
    if cipher is not None and settings["rest_api_key"]:
        sender = KakaoNotificationSender(
            connections,
            rest_api_key=str(settings["rest_api_key"]),
            client_secret=settings["client_secret"],
        )
    return UserAlertDispatcher(
        target_query=SqlAlchemyUserAlertEvaluationTargetQuery(db),
        evaluation_repository=SqlAlchemyAlertEvaluationRepository(db),
        evaluator=LangGraphUserAlertEvaluator(
            custom_rule_agent=get_default_custom_rule_agent(),
            evaluation_model=GeminiAlertEvaluationModel(),
        ),
        connection_repository=connections,
        delivery_repository=SqlAlchemyNotificationDeliveryRepository(db),
        sender=sender,
    )


def get_market_data_provider() -> MarketDataProvider:
    return YFinanceMarketDataProvider()


def get_default_custom_rule_agent() -> CustomRuleAgent:
    return LangGraphCustomRuleAgent()


def get_analysis_agent() -> AnalysisAgent:
    return MainAnalysisAgent(
        main_model=GeminiAnalysisAgent(),
        custom_rule_agent=get_default_custom_rule_agent(),
    )

__all__ = [
    "build_analysis_service",
    "build_system_alert_dispatcher",
    "build_user_alert_dispatcher",
    "get_analysis_agent",
    "get_market_data_provider",
]
