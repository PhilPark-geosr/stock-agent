from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.web_auth import require_operator, require_web_origin
from app.application.invitations import InvitationIssuer
from app.core.database import get_db
from app.repositories.invitations import SqlAlchemyInvitationRepository

router = APIRouter()


@router.post('/admin/invitations', status_code=201,
             dependencies=[Depends(require_web_origin), Depends(require_operator)])
def issue_invitation(response: Response, db: Session = Depends(get_db)):
    try:
        result = InvitationIssuer(SqlAlchemyInvitationRepository(db)).issue_invitation()
    except Exception:
        # Do not include DB exceptions or secret-bearing input in responses/logs.
        raise HTTPException(status_code=500, detail='Invitation could not be issued') from None
    response.headers['Cache-Control'] = 'no-store'
    return {'code': result.code, 'expires_at': result.expires_at}
