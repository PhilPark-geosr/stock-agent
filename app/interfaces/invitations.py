from datetime import datetime
from typing import Protocol

from app.domain.invitations import Invitation


class InvitationRepository(Protocol):
    def save(self, invitation: Invitation) -> None: ...

    def find_by_code(self, code: str) -> Invitation | None: ...

    def has_beta_access(self, account_id: str) -> bool: ...

    def redeem(self, invitation: Invitation, account_id: str, used_at: datetime) -> bool: ...
