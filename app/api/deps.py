"""FastAPI dependency providers."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.container import (
    build_analysis_service,
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
from app.services import AnalysisProvider
from app.application.auth_sessions import LoginAttemptService, SessionService
from app.application.login import LoginService
from app.integrations.kakao_auth import KakaoAuthError, KakaoExternalLogin, build_authorize_url, kakao_settings
from app.repositories.auth import SqlAlchemyAuthSessionRepository, SqlAlchemyLoginAttemptRepository
from app.repositories.auth import SqlAlchemyUserAccountRepository


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


def get_watchlist_repository(db: Session = Depends(get_db)) -> WatchlistRepositoryInterface:
    return WatchlistRepository(db)


def get_alert_condition_repository(db: Session = Depends(get_db)) -> AlertConditionRepositoryInterface:
    return AlertConditionRepository(db)


def get_session_service(db: Session = Depends(get_db)) -> SessionService:
    return SessionService(SqlAlchemyAuthSessionRepository(db))


def get_login_attempt_service(
    db: Session = Depends(get_db),
    sessions: SessionService = Depends(get_session_service),
) -> LoginAttemptService:
    return LoginAttemptService(SqlAlchemyLoginAttemptRepository(db), sessions)


def get_authorization_url():
    return lambda state: build_authorize_url(state=state)


def get_login_service(db: Session = Depends(get_db)) -> LoginService:
    settings = kakao_settings()
    rest_api_key = settings["rest_api_key"]
    if not rest_api_key:
        raise KakaoAuthError("KAKAO_REST_API_KEY is required")
    external_login = KakaoExternalLogin(
        rest_api_key=rest_api_key,
        redirect_uri=settings["redirect_uri"],
        client_secret=settings["client_secret"],
    )
    return LoginService(external_login, SqlAlchemyUserAccountRepository(db))
