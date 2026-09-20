from typing import Protocol

from app.domain.invitations import Invitation


class InvitationRepository(Protocol):
    def save(self, invitation: Invitation) -> None: ...

    def find_by_code(self, code: str) -> Invitation | None: ...
