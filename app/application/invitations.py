import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.domain.invitations import Invitation, hash_code
from app.interfaces.invitations import InvitationRepository


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class IssuedInvitation:
    code: str
    expires_at: datetime


class InvitationIssuer:
    def __init__(self, invitations: InvitationRepository, *, now: Callable[[], datetime] = utc_now):
        self.invitations = invitations
        self.now = now

    def issue_invitation(self) -> IssuedInvitation:
        code = secrets.token_urlsafe(32)
        issued_at = self.now()
        invitation = Invitation(
            id=str(uuid4()), code_hash=hash_code(code), issued_at=issued_at,
            expires_at=issued_at + timedelta(days=7),
        )
        self.invitations.save(invitation)
        return IssuedInvitation(code, invitation.expires_at)
