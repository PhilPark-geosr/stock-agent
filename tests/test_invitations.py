from datetime import datetime, timedelta, timezone

import pytest

from app.application.invitations import InvitationIssuer
from app.domain.invitations import Invitation, hash_code

NOW = datetime(2026, 9, 21, tzinfo=timezone.utc)


class MemoryInvitations:
    def __init__(self):
        self.saved = []

    def save(self, invitation):
        self.saved.append(invitation)


def test_issue_records_one_unused_invitation_and_returns_original_code():
    repository = MemoryInvitations()
    result = InvitationIssuer(repository, now=lambda: NOW).issue_invitation()
    assert len(repository.saved) == 1
    invitation = repository.saved[0]
    assert invitation.code_hash == hash_code(result.code)
    assert result.code not in repr(invitation)
    assert invitation.issued_at == NOW
    assert invitation.used_at is None
    assert result.expires_at == invitation.expires_at == NOW + timedelta(days=7)


@pytest.mark.parametrize('offset, expected', [(-1, True), (0, False), (1, False)])
def test_invitation_expiry_boundary(offset, expected):
    invitation = Invitation('id', hash_code('code'), NOW, NOW + timedelta(days=7))
    assert invitation.can_use(invitation.expires_at + timedelta(microseconds=offset)) is expected


def test_used_invitation_is_unavailable():
    invitation = Invitation('id', hash_code('code'), NOW, NOW + timedelta(days=7), used_at=NOW)
    assert not invitation.can_use(NOW)


def test_storage_failure_does_not_return_issued_code():
    class FailingRepository:
        def save(self, invitation):
            raise RuntimeError('storage unavailable')

    with pytest.raises(RuntimeError, match='storage unavailable'):
        InvitationIssuer(FailingRepository(), now=lambda: NOW).issue_invitation()
