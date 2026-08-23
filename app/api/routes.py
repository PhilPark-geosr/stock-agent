from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.api.deps import (
    get_alert_condition_repository,
    get_analysis_service,
    get_briefing_service,
    get_rule_validation_agent,
    get_watchlist_repository,
    get_authorization_url,
    get_login_attempt_service,
    get_session_service,
    get_login_service,
    get_current_account,
    require_internal_operator,
)
from app.application.auth_sessions import AttemptExpired, AttemptNotFound, AttemptPending, AttemptUnauthorized, LoginAttemptService, SessionService
from app.application.login import LoginService
from app.domain.auth import ExternalLoginCredential
from app.domain.auth import UserAccount
from app.domain.symbols import StockSymbol
from app.application.custom_rule_agent import CustomRuleAgentError
from app.integrations.kakao_auth import (
    KakaoAuthError,
    kakao_settings,
)
from app.interfaces.analysis import AgentConfigurationError, AnalysisAgentError
from app.interfaces.market_data import MarketDataError
from app.interfaces.notifications import AlertNotifyError
from app.interfaces.repositories import AlertConditionRepository, WatchlistRepository
from app.interfaces.rule_validation import RuleValidationAgent, RuleValidationError
from app.schemas import (
    AnalysisResultHistoryItem,
    AnalysisResultRead,
    BriefingDetailRead,
    BriefingRead,
    BriefingRunRequest,
    CustomAlertConditionCreate,
    CustomAlertConditionRead,
    WatchlistCreate,
    WatchlistItemRead,
)
from app.services.scheduler import run_scheduled_batch
from app.services import (
    AnalysisProvider,
    BriefingService,
    EmptyWatchlistError,
    NonTradingDayError,
    ScheduledBatchResult,
)


router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))
bearer = HTTPBearer(auto_error=False)


def _require_active_subscription(
    account: UserAccount,
    symbol: str,
    watchlist_repository: WatchlistRepository,
) -> None:
    try:
        stock_symbol = StockSymbol.of(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if watchlist_repository.get(account.id, stock_symbol) is None:
        raise HTTPException(status_code=404, detail="active watchlist subscription not found")


class LoginAttemptCreate(BaseModel):
    verifier_challenge: str


class LoginAttemptExchange(BaseModel):
    verifier: str


def _account_payload(account):
    return {"id": account.id, "login_provider": account.login_identity.provider}


@router.post("/auth/login-attempts", status_code=status.HTTP_201_CREATED)
def start_login_attempt(payload: LoginAttemptCreate, attempts: LoginAttemptService = Depends(get_login_attempt_service), authorization_url=Depends(get_authorization_url)):
    result = attempts.start(payload.verifier_challenge)
    try:
        url = authorization_url(result.state)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"attempt_id": result.attempt_id, "authorization_url": url, "expires_at": result.expires_at}


@router.post("/auth/login-attempts/{attempt_id}/exchange")
def exchange_login_attempt(attempt_id: str, payload: LoginAttemptExchange, attempts: LoginAttemptService = Depends(get_login_attempt_service)):
    try:
        result = attempts.exchange(attempt_id, payload.verifier)
    except AttemptPending:
        return Response(status_code=status.HTTP_202_ACCEPTED)
    except AttemptNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AttemptExpired as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except AttemptUnauthorized as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return {"session_token": result.token, "account": _account_payload(result.account)}


def _token(credentials: HTTPAuthorizationCredentials | None) -> str:
    if credentials is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return credentials.credentials


@router.get("/auth/session")
def get_auth_session(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), sessions: SessionService = Depends(get_session_service)):
    try:
        return _account_payload(sessions.authenticate(_token(credentials)))
    except AttemptUnauthorized as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.delete("/auth/session", status_code=status.HTTP_204_NO_CONTENT)
def delete_auth_session(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), sessions: SessionService = Depends(get_session_service)):
    try:
        sessions.revoke(_token(credentials))
    except AttemptUnauthorized as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"default_symbol": "005930.KS"},
    )


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/auth/kakao/callback", response_class=HTMLResponse)
def kakao_callback(
    request: Request,
    code: str | None = Query(default=None),
    state_value: str | None = Query(default=None, alias="state"),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    login_service: LoginService = Depends(get_login_service),
    attempts: LoginAttemptService = Depends(get_login_attempt_service),
):
    if error:
        return templates.TemplateResponse(
            request,
            "kakao_callback.html",
            {
                "success": False,
                "message": error_description or error,
                "access_token": None, "refresh_token": None,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if not code or not state_value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="code and state are required")

    try:
        redirect_uri = kakao_settings()["redirect_uri"]
        account = login_service.login(ExternalLoginCredential(code, redirect_uri))
        attempts.complete(state_value, account)
    except AttemptExpired as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except AttemptUnauthorized as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except KakaoAuthError as exc:
        return templates.TemplateResponse(
            request,
            "kakao_callback.html",
            {"success": False, "message": str(exc), "access_token": None, "refresh_token": None},
            status_code=status.HTTP_502_BAD_GATEWAY,
        )

    return templates.TemplateResponse(
        request,
        "kakao_callback.html",
        {
            "success": True,
            "message": "로그인이 완료되었습니다. 앱으로 돌아가세요.",
            "access_token": None,
            "refresh_token": None,
        },
    )


@router.post("/watchlist", response_model=WatchlistItemRead, status_code=status.HTTP_201_CREATED)
def add_watchlist_item(
    payload: WatchlistCreate,
    account: UserAccount = Depends(get_current_account),
    watchlist_repository: WatchlistRepository = Depends(get_watchlist_repository),
):
    return watchlist_repository.add(account.id, StockSymbol.of(payload.symbol))


@router.get("/watchlist", response_model=list[WatchlistItemRead])
def list_watchlist_items(
    account: UserAccount = Depends(get_current_account),
    watchlist_repository: WatchlistRepository = Depends(get_watchlist_repository),
):
    return watchlist_repository.list(account.id)


@router.delete("/watchlist/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
def delete_watchlist_item(
    symbol: str,
    account: UserAccount = Depends(get_current_account),
    watchlist_repository: WatchlistRepository = Depends(get_watchlist_repository),
):
    deleted = watchlist_repository.delete(account.id, StockSymbol.of(symbol))
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="watchlist item not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/alert-conditions",
    response_model=CustomAlertConditionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_alert_condition(
    payload: CustomAlertConditionCreate,
    account: UserAccount = Depends(get_current_account),
    alert_condition_repository: AlertConditionRepository = Depends(get_alert_condition_repository),
    validation_agent: RuleValidationAgent = Depends(get_rule_validation_agent),
):
    try:
        validation = validation_agent.validate(
            user_rule=payload.user_rule,
            target_symbol=payload.symbol,
        )
    except (RuleValidationError, AgentConfigurationError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    if not validation.is_valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "validation_summary": validation.validation_summary,
                "rewrite_guidance": validation.rewrite_guidance,
            },
        )

    try:
        return alert_condition_repository.save_validated(
            owner_id=account.id,
            symbol=payload.symbol,
            user_rule=payload.user_rule,
            validation=validation,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/alert-conditions", response_model=list[CustomAlertConditionRead])
def list_alert_conditions(
    account: UserAccount = Depends(get_current_account),
    alert_condition_repository: AlertConditionRepository = Depends(get_alert_condition_repository),
):
    return alert_condition_repository.list(account.id)


@router.delete("/alert-conditions/{condition_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alert_condition(
    condition_id: int,
    account: UserAccount = Depends(get_current_account),
    alert_condition_repository: AlertConditionRepository = Depends(get_alert_condition_repository),
):
    if not alert_condition_repository.delete(account.id, condition_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="alert condition not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/scheduler/run", response_model=ScheduledBatchResult)
def run_scheduler(
    force: bool = Query(default=False, description="Skip market-hours check"),
    analysis_service: AnalysisProvider = Depends(get_analysis_service),
):
    try:
        return run_scheduled_batch(analysis_service, ignore_market_hours=force)
    except AlertNotifyError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/stocks/{symbol}/analysis", response_model=list[AnalysisResultHistoryItem])
def list_analysis_history(
    symbol: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    account: UserAccount = Depends(get_current_account),
    watchlist_repository: WatchlistRepository = Depends(get_watchlist_repository),
    analysis_service: AnalysisProvider = Depends(get_analysis_service),
):
    _require_active_subscription(account, symbol, watchlist_repository)
    try:
        return analysis_service.list_analysis_history(symbol, limit=limit, offset=offset)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/stocks/{symbol}/analysis",
    response_model=AnalysisResultRead,
    status_code=status.HTTP_201_CREATED,
)
def run_manual_analysis(
    symbol: str,
    account: UserAccount = Depends(get_current_account),
    watchlist_repository: WatchlistRepository = Depends(get_watchlist_repository),
    analysis_service: AnalysisProvider = Depends(get_analysis_service),
):
    _require_active_subscription(account, symbol, watchlist_repository)
    try:
        result = analysis_service.run_manual_analysis(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except MarketDataError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except (AnalysisAgentError, AgentConfigurationError, CustomRuleAgentError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except AlertNotifyError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return result


@router.get("/stocks/{symbol}/analysis/latest", response_model=AnalysisResultRead)
def get_latest_analysis(
    symbol: str,
    account: UserAccount = Depends(get_current_account),
    watchlist_repository: WatchlistRepository = Depends(get_watchlist_repository),
    analysis_service: AnalysisProvider = Depends(get_analysis_service),
):
    _require_active_subscription(account, symbol, watchlist_repository)
    try:
        result = analysis_service.get_latest_analysis(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except MarketDataError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except (AnalysisAgentError, AgentConfigurationError, CustomRuleAgentError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except AlertNotifyError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return result


@router.get("/stocks/{symbol}/analysis/{result_id}", response_model=AnalysisResultRead)
def get_analysis_by_id(
    symbol: str,
    result_id: int,
    account: UserAccount = Depends(get_current_account),
    watchlist_repository: WatchlistRepository = Depends(get_watchlist_repository),
    analysis_service: AnalysisProvider = Depends(get_analysis_service),
):
    _require_active_subscription(account, symbol, watchlist_repository)
    try:
        return analysis_service.get_analysis_by_id(symbol, result_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/internal/briefings/run", response_model=BriefingDetailRead)
def run_briefing(
    payload: BriefingRunRequest,
    briefing_service: BriefingService = Depends(get_briefing_service),
    account: UserAccount = Depends(get_current_account),
    _internal: None = Depends(require_internal_operator),
):
    try:
        briefing = briefing_service.generate(
            user_account_id=account.id,
            exchange=payload.exchange,
            briefing_type=payload.briefing_type,
            trading_date=payload.trading_date,
            force=payload.force,
        )
    except (NonTradingDayError, EmptyWatchlistError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _briefing_detail(briefing_service, briefing)


@router.get("/users/me/briefings", response_model=list[BriefingRead])
def list_my_briefings(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    briefing_service: BriefingService = Depends(get_briefing_service),
    account: UserAccount = Depends(get_current_account),
):
    return briefing_service.list_for_user(account.id, limit=limit, offset=offset)


@router.get("/users/me/briefings/{briefing_id}", response_model=BriefingDetailRead)
def get_my_briefing(
    briefing_id: int,
    briefing_service: BriefingService = Depends(get_briefing_service),
    account: UserAccount = Depends(get_current_account),
):
    try:
        briefing = briefing_service.get_for_user(briefing_id, account.id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _briefing_detail(briefing_service, briefing)


def _briefing_detail(briefing_service: BriefingService, briefing) -> dict:
    return {
        "id": briefing.id,
        "user_account_id": briefing.user_account_id,
        "briefing_type": briefing.briefing_type,
        "exchange": briefing.exchange,
        "trading_date": briefing.trading_date,
        "status": briefing.status,
        "summary": briefing.summary,
        "generated_at": briefing.generated_at,
        "version": briefing.version,
        "resolved_symbols": briefing.resolved_symbols,
        "failure_count": briefing.failure_count,
        "items": briefing_service.get_items(briefing.id),
        "deliveries": briefing_service.get_deliveries(briefing.id),
        "scopes": briefing_service.get_scopes(briefing.id),
        "failures": briefing_service.get_failures(briefing.id),
    }
