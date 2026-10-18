"""Cookie-based web sessions; the Electron bearer flow remains independent."""
import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from app.api.deps import (
    get_login_attempt_service,
    get_session_service,
    is_operator,
    require_web_origin,
)
from app.application.auth_sessions import (
    AttemptExpired, AttemptNotFound, AttemptPending, AttemptUnauthorized,
    LoginAttemptService, SessionService,
)
from app.application.invitations import InvalidInvitation, InvitationRedeemer
from app.core.database import get_db
from app.domain.auth import UserAccount
from app.repositories.invitations import SqlAlchemyInvitationRepository
from sqlalchemy.orm import Session

router = APIRouter()
COOKIE_NAME = 'stock_agent_session'


def cookie_secure() -> bool:
    return os.getenv('WEB_COOKIE_SECURE', 'true').lower() != 'false'


def web_current_account(request: Request, sessions: SessionService = Depends(get_session_service)) -> UserAccount:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail='Login required')
    try:
        return sessions.authenticate(token)
    except AttemptUnauthorized:
        raise HTTPException(status_code=401, detail='Invalid session') from None


def require_operator(account: UserAccount = Depends(web_current_account)) -> UserAccount:
    if not is_operator(account):
        raise HTTPException(status_code=403, detail='Operator permission required')
    return account


def account_payload(account: UserAccount) -> dict:
    return {
        'id': account.id,
        'login_provider': account.login_identity.provider,
        'is_operator': is_operator(account),
        'has_beta_access': account.has_beta_access,
    }


class WebLoginExchange(BaseModel):
    verifier: str


class InvitationRedemption(BaseModel):
    code: str


@router.post('/auth/web/login-attempts/{attempt_id}/exchange', dependencies=[Depends(require_web_origin)])
def exchange_web_login(attempt_id: str, payload: WebLoginExchange, response: Response,
                       attempts: LoginAttemptService = Depends(get_login_attempt_service)):
    try:
        result = attempts.exchange(attempt_id, payload.verifier)
    except AttemptPending:
        return Response(status_code=202, headers={'Cache-Control': 'no-store'})
    except AttemptNotFound:
        raise HTTPException(status_code=404, detail='Login attempt not found') from None
    except AttemptExpired:
        raise HTTPException(status_code=410, detail='Login attempt expired') from None
    except AttemptUnauthorized:
        raise HTTPException(status_code=401, detail='Invalid login attempt') from None
    response.set_cookie(COOKIE_NAME, result.token, max_age=30 * 24 * 60 * 60,
                        httponly=True, secure=cookie_secure(), samesite='lax', path='/')
    response.headers['Cache-Control'] = 'no-store'
    return account_payload(result.account)


@router.get('/auth/web/session')
def get_web_session(response: Response, account: UserAccount = Depends(web_current_account)):
    response.headers['Cache-Control'] = 'no-store'
    return account_payload(account)


@router.post('/auth/web/invitations/redeem', dependencies=[Depends(require_web_origin)])
def redeem_web_invitation(
    payload: InvitationRedemption,
    response: Response,
    account: UserAccount = Depends(web_current_account),
    db: Session = Depends(get_db),
):
    try:
        granted = InvitationRedeemer(SqlAlchemyInvitationRepository(db)).redeem(account, payload.code)
    except InvalidInvitation:
        raise HTTPException(status_code=400, detail='Invalid invitation') from None
    except Exception:
        # Do not expose submitted codes or database details.
        raise HTTPException(status_code=500, detail='Invitation could not be redeemed') from None
    response.headers['Cache-Control'] = 'no-store'
    return account_payload(granted)


@router.delete('/auth/web/session', status_code=204, dependencies=[Depends(require_web_origin)])
def delete_web_session(request: Request, account: UserAccount = Depends(web_current_account),
                       sessions: SessionService = Depends(get_session_service)):
    try:
        sessions.revoke(request.cookies[COOKIE_NAME])
    except AttemptUnauthorized:
        raise HTTPException(status_code=401, detail='Invalid session') from None
    response = Response(status_code=204, headers={'Cache-Control': 'no-store'})
    response.delete_cookie(COOKIE_NAME, path='/', httponly=True, secure=cookie_secure(), samesite='lax')
    return response
