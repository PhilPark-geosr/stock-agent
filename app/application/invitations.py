import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.domain.invitations import Invitation, hash_code
from app.domain.auth import UserAccount
from app.interfaces.invitations import InvitationRepository


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class IssuedInvitation:
    code: str
    expires_at: datetime


class InvalidInvitation(RuntimeError):
    pass


class InvitationCodeValidator:
    def __init__(self, invitations: InvitationRepository):
        self.invitations = invitations

    def validate(self, code: str, now: datetime) -> Invitation:
        invitation = self.invitations.find_by_code(code)
        if invitation is None or not invitation.can_use(now):
            raise InvalidInvitation("invalid invitation")
        return invitation


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


class InvitationRedeemer:
    def __init__(
        self,
        invitations: InvitationRepository,
        *,
        validator: InvitationCodeValidator | None = None,
        now: Callable[[], datetime] = utc_now,
    ):
        self.invitations = invitations
        self.validator = validator or InvitationCodeValidator(invitations)
        self.now = now

    def redeem(self, account: UserAccount, code: str) -> UserAccount:
        # Check the persisted grant before looking at the submitted code. A user
        # who is already enrolled must not consume another invitation.
        if account.has_beta_access or self.invitations.has_beta_access(account.id):
            return UserAccount(account.id, account.login_identity, has_beta_access=True)

        redeemed_at = self.now()
        invitation = self.validator.validate(code, redeemed_at)
        if not self.invitations.redeem(invitation, account.id, redeemed_at):
            raise InvalidInvitation("invalid invitation")
        return UserAccount(account.id, account.login_identity, has_beta_access=True)
