"""FastAPI dependency providers."""

from __future__ import annotations

import os

from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.container import (
    build_analysis_service,
    get_analysis_agent,
    get_market_data_provider,
)
from app.core.database import get_db
from app.integrations.llm.gemini_rule_validation_agent import GeminiRuleValidationAgent
from app.interfaces.analysis import AnalysisAgent
from app.interfaces.market_data import MarketDataProvider
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
from app.application.auth_sessions import AttemptUnauthorized
from app.domain.auth import UserAccount
from app.repositories.notifications import SqlAlchemyNotificationConnectionRepository
from app.application.notification_connections import KakaoNotificationConnectionService


bearer = HTTPBearer(auto_error=False)
COOKIE_NAME = "stock_agent_session"


def is_operator(account: UserAccount) -> bool:
    configured = os.getenv("ADMIN_ACCOUNT_ID", "").strip()
    return bool(configured) and account.id == configured


def require_web_origin(request: Request) -> None:
    expected = os.getenv("WEB_ORIGIN", "http://127.0.0.1:8000").rstrip("/")
    if request.headers.get("origin") != expected:
        raise HTTPException(status_code=403, detail="Untrusted web origin")


def get_rule_validation_agent() -> RuleValidationAgent:
    return GeminiRuleValidationAgent()


def get_analysis_service(
    db: Session = Depends(get_db),
    market_data_provider: MarketDataProvider = Depends(get_market_data_provider),
    agent: AnalysisAgent = Depends(get_analysis_agent),
) -> AnalysisProvider:
    return build_analysis_service(
        db,
        market_data_provider=market_data_provider,
        agent=agent,
    )


def get_watchlist_repository(db: Session = Depends(get_db)) -> WatchlistRepositoryInterface:
    return WatchlistRepository(db)


def get_alert_condition_repository(db: Session = Depends(get_db)) -> AlertConditionRepositoryInterface:
    return AlertConditionRepository(db)


def get_session_service(db: Session = Depends(get_db)) -> SessionService:
    return SessionService(SqlAlchemyAuthSessionRepository(db))


def get_current_account(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    sessions: SessionService = Depends(get_session_service),
) -> UserAccount:
    if credentials is not None:
        token = credentials.credentials
        request.state.auth_via_cookie = False
    else:
        token = request.cookies.get(COOKIE_NAME)
        request.state.auth_via_cookie = token is not None
    if not token:
        raise HTTPException(status_code=401, detail="authentication required")
    try:
        return sessions.authenticate(token)
    except AttemptUnauthorized as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def require_beta_access(
    account: UserAccount = Depends(get_current_account),
) -> UserAccount:
    if not account.has_beta_access:
        raise HTTPException(status_code=403, detail="Beta access required")
    return account


def require_beta_mutation(
    request: Request,
    account: UserAccount = Depends(require_beta_access),
) -> UserAccount:
    if getattr(request.state, "auth_via_cookie", False):
        require_web_origin(request)
    return account


def require_operator_mutation(
    request: Request,
    account: UserAccount = Depends(get_current_account),
) -> UserAccount:
    if not is_operator(account):
        raise HTTPException(status_code=403, detail="Operator permission required")
    if getattr(request.state, "auth_via_cookie", False):
        require_web_origin(request)
    return account


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


def get_notification_connection_repository(
    db: Session = Depends(get_db),
):
    key = os.getenv("NOTIFICATION_TOKEN_FERNET_KEY")
    if not key:
        raise HTTPException(
            status_code=503,
            detail="notification token encryption is not configured",
        )
    try:
        cipher = Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="notification token encryption key is invalid",
        ) from exc
    return SqlAlchemyNotificationConnectionRepository(db, cipher)


def get_notification_connection_service(
    repository=Depends(get_notification_connection_repository),
):
    settings = kakao_settings()
    rest_api_key = settings["rest_api_key"]
    if not rest_api_key:
        raise HTTPException(
            status_code=503,
            detail="KAKAO_REST_API_KEY is required",
        )
    redirect_uri = os.getenv(
        "KAKAO_NOTIFICATION_REDIRECT_URI",
        "http://127.0.0.1:8000/notification-connections/kakao/callback",
    )
    key = os.environ["NOTIFICATION_TOKEN_FERNET_KEY"]
    return KakaoNotificationConnectionService(
        repository,
        rest_api_key=rest_api_key,
        redirect_uri=redirect_uri,
        state_cipher=Fernet(key.encode()),
        client_secret=settings["client_secret"],
    )
