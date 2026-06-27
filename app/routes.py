from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.agent import AgentConfigurationError, AnalysisAgentError
from app.custom_rule_agent import CustomRuleAgentError
from app.database import get_db
from app.kakao_auth import (
    KakaoAuthError,
    build_authorize_url,
    exchange_code_for_token,
    persist_tokens_to_env,
)
from app.market_data import MarketDataError
from app.repositories import AlertConditionRepository, WatchlistRepository
from app.rule_validation import GeminiRuleValidationAgent, RuleValidationAgent, RuleValidationError
from app.schemas import (
    AnalysisResultRead,
    CustomAlertConditionCreate,
    CustomAlertConditionRead,
    WatchlistCreate,
    WatchlistItemRead,
)
from app.kakao_notify import KakaoNotifyError
from app.scheduler import run_scheduled_batch
from app.services import AnalysisProvider, ScheduledBatchResult, get_analysis_service


router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


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


def get_rule_validation_agent() -> RuleValidationAgent:
    return GeminiRuleValidationAgent()


@router.get("/auth/kakao/login")
def kakao_login():
    try:
        return RedirectResponse(build_authorize_url(), status_code=status.HTTP_302_FOUND)
    except KakaoAuthError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get("/auth/kakao/callback", response_class=HTMLResponse)
def kakao_callback(
    request: Request,
    code: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
):
    if error:
        return templates.TemplateResponse(
            request,
            "kakao_callback.html",
            {
                "success": False,
                "message": error_description or error,
                "access_token": None,
                "refresh_token": None,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if not code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="code is required")

    try:
        token_payload = exchange_code_for_token(code)
        persist_tokens_to_env(token_payload)
    except KakaoAuthError as exc:
        hint = ""
        if "KOE010" in str(exc) or "invalid_client" in str(exc):
            hint = (
                " REST API 키에 클라이언트 시크릿이 켜져 있으면 .env에 "
                "KAKAO_CLIENT_SECRET= 을 넣거나, 콘솔에서 시크릿을 끄세요."
            )
        return templates.TemplateResponse(
            request,
            "kakao_callback.html",
            {"success": False, "message": str(exc) + hint, "access_token": None, "refresh_token": None},
            status_code=status.HTTP_502_BAD_GATEWAY,
        )

    return templates.TemplateResponse(
        request,
        "kakao_callback.html",
        {
            "success": True,
            "message": ".env에 아래 토큰을 저장했습니다. access_token은 만료되면 refresh_token으로 갱신하세요.",
            "access_token": token_payload.get("access_token"),
            "refresh_token": token_payload.get("refresh_token"),
        },
    )


@router.post("/watchlist", response_model=WatchlistItemRead, status_code=status.HTTP_201_CREATED)
def add_watchlist_item(payload: WatchlistCreate, db: Session = Depends(get_db)):
    return WatchlistRepository(db).add(payload.symbol)


@router.get("/watchlist", response_model=list[WatchlistItemRead])
def list_watchlist_items(db: Session = Depends(get_db)):
    return WatchlistRepository(db).list()


@router.delete("/watchlist/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
def delete_watchlist_item(symbol: str, db: Session = Depends(get_db)):
    deleted = WatchlistRepository(db).delete(symbol)
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
    db: Session = Depends(get_db),
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

    return AlertConditionRepository(db).save_validated(
        symbol=payload.symbol,
        user_rule=payload.user_rule,
        validation=validation,
    )


@router.get("/alert-conditions", response_model=list[CustomAlertConditionRead])
def list_alert_conditions(db: Session = Depends(get_db)):
    return AlertConditionRepository(db).list()


@router.delete("/alert-conditions/{condition_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alert_condition(condition_id: int, db: Session = Depends(get_db)):
    if not AlertConditionRepository(db).delete(condition_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="alert condition not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/scheduler/run", response_model=ScheduledBatchResult)
def run_scheduler(
    force: bool = Query(default=False, description="Skip market-hours check"),
    db: Session = Depends(get_db),
):
    try:
        return run_scheduled_batch(db, ignore_market_hours=force)
    except KakaoNotifyError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/stocks/{symbol}/analysis/latest", response_model=AnalysisResultRead)
def get_latest_analysis(
    symbol: str,
    analysis_service: AnalysisProvider = Depends(get_analysis_service),
):
    try:
        result = analysis_service.get_latest_analysis(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except MarketDataError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except (AnalysisAgentError, AgentConfigurationError, CustomRuleAgentError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except KakaoNotifyError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return result
