"""Application composition root."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from sqlalchemy.orm import Session

from app.application.analysis_graph import MainAnalysisAgent
from app.application.custom_rule_agent import CustomRuleAgent, LangGraphCustomRuleAgent
from app.core.scheduler_config import scheduler_settings
from app.core.trading_window import is_alert_window
from app.integrations.kakao_notify import get_default_alert_notifier
from app.integrations.llm.gemini_analysis_agent import GeminiAnalysisAgent
from app.integrations.yfinance_market_data_provider import YFinanceMarketDataProvider
from app.interfaces.analysis import AnalysisAgent
from app.interfaces.market_data import MarketDataProvider
from app.interfaces.notifications import AlertNotifier
from app.repositories import (
    AlertConditionRepository as SqlAlchemyAlertConditionRepository,
    AnalysisRepository as SqlAlchemyAnalysisRepository,
    WatchlistRepository as SqlAlchemyWatchlistRepository,
    BriefingRepository as SqlAlchemyBriefingRepository,
)
from app.services import AnalysisService, BriefingService


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
    alert_notifier: AlertNotifier | None = None,
    alert_window_checker: Callable[[datetime], bool] | None = None,
    now_provider: Callable[[], datetime] | None = None,
) -> AnalysisService:
    return AnalysisService(
        analysis_repository=SqlAlchemyAnalysisRepository(db),
        alert_condition_repository=SqlAlchemyAlertConditionRepository(db),
        watchlist_repository=SqlAlchemyWatchlistRepository(db),
        market_data_provider=market_data_provider or get_market_data_provider(),
        agent=agent or get_analysis_agent(),
        alert_notifier=alert_notifier or get_alert_notifier(),
        alert_window_checker=alert_window_checker or build_alert_window_checker(),
        now_provider=now_provider,
    )


def build_briefing_service(
    db: Session,
    *,
    analysis_service: AnalysisService | None = None,
) -> BriefingService:
    provider = analysis_service or build_analysis_service(db)
    analysis_repository = SqlAlchemyAnalysisRepository(db)
    watchlist_repository = SqlAlchemyWatchlistRepository(db)
    return BriefingService(
        briefing_repository=SqlAlchemyBriefingRepository(db),
        analysis_repository=analysis_repository,
        watchlist_repository=watchlist_repository,
        analysis_provider=provider,
        notifier=provider.alert_notifier,
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


def get_alert_notifier() -> AlertNotifier:
    return get_default_alert_notifier()
