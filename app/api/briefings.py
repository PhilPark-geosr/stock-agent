from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
import os
from sqlalchemy.orm import Session

from app.api.deps import get_current_account
from app.core.briefings import build_briefing_coordinator
from app.core.database import get_db
from app.domain.briefings import (
    BriefingConflict, BriefingError, BriefingRequest, BriefingSettings, Contract, Market,
    market_for_symbol,
)

router = APIRouter(prefix="/briefings", tags=["briefings"])


def get_briefings(db: Session = Depends(get_db)):
    return build_briefing_coordinator(db)


class RetryRequest(Contract):
    request_id: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    acknowledge_unknown: bool = False


@router.get("/settings/{market}")
def settings(market: Market, account=Depends(get_current_account), service=Depends(get_briefings)):
    return service.history.settings(account.id, market)


@router.put("/settings/{market}")
def save_settings(market: Market, body: BriefingSettings, account=Depends(get_current_account), service=Depends(get_briefings)):
    if (body.pre_market_enabled or body.post_market_enabled) and not body.n:
        raise HTTPException(422, "자동 제공에는 차트 관찰기간 n이 필요합니다.")
    try:
        if body.symbols is not None:
            allowed = {r.symbol for r in service.context_source.watchlist.list(account.id)
                       if market_for_symbol(r.symbol) == market}
            if set(body.symbols) - allowed:
                raise BriefingError("선택한 시장에 등록된 본인의 관심종목만 선택할 수 있습니다.")
        return service.history.save_settings(account.id, market, body)
    except BriefingConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except BriefingError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/options/{market}")
def options(market: Market, account=Depends(get_current_account), service=Depends(get_briefings)):
    result = service.context_source.options(account.id, market, service.clock())
    try:
        service.prompts.active()
        result["prompt_ready"] = True
    except BriefingError:
        result["prompt_ready"] = False
    result["disclosure_configured"] = bool(os.getenv("DART_API_KEY" if market == "KR" else "SEC_USER_AGENT"))
    result["kakao_connected"] = service.delivery.connections.get_active(owner_id=account.id, channel="kakao") is not None
    result["scheduler_enabled"] = os.getenv("BRIEFING_SCHEDULER_ENABLED", "true").lower() == "true"
    return result


@router.post("", status_code=201)
def generate(body: BriefingRequest, account=Depends(get_current_account), service=Depends(get_briefings)):
    try:
        return service.history.payload(service.generate(account.id, body))
    except BriefingConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except BriefingError as exc:
        raise HTTPException(422, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("")
def history(limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0),
            account=Depends(get_current_account), service=Depends(get_briefings)):
    return [service.history.payload(r, detail=False) for r in service.history.list(account.id, limit, offset)]


@router.get("/{run_id}")
def detail(run_id: str, account=Depends(get_current_account), service=Depends(get_briefings)):
    try:
        return service.history.payload(service.history.get(account.id, run_id))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/{run_id}/delivery")
def redeliver(run_id: str, body: RetryRequest, account=Depends(get_current_account), service=Depends(get_briefings)):
    try:
        service.delivery.deliver(account.id, run_id, retry_id=body.request_id,
            acknowledge_unknown=body.acknowledge_unknown)
        return service.history.payload(service.history.get(account.id, run_id))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except BriefingConflict as exc:
        raise HTTPException(409, str(exc)) from exc
