from datetime import datetime, timezone
from dataclasses import replace

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.invitations import InvitationIssuer
from app.domain.models import InvitationRecord
from app.repositories.invitations import SqlAlchemyInvitationRepository


def test_invitation_survives_new_session_without_plaintext(db_session):
    repository = SqlAlchemyInvitationRepository(db_session)
    result = InvitationIssuer(repository, now=lambda: datetime(2026, 9, 21, tzinfo=timezone.utc)).issue_invitation()
    with Session(db_session.bind) as another:
        invitation = SqlAlchemyInvitationRepository(another).find_by_code(result.code)
        assert invitation is not None
        assert invitation.can_use(datetime(2026, 9, 22, tzinfo=timezone.utc))
        assert invitation.expires_at == result.expires_at
        assert invitation.used_at is None
        assert SqlAlchemyInvitationRepository(another).find_by_code('unknown') is None
        row = another.execute(text('SELECT * FROM invitations')).one()
        assert result.code not in repr(row)


def test_duplicate_hash_rejected_and_existing_record_preserved(db_session):
    repository = SqlAlchemyInvitationRepository(db_session)
    result = InvitationIssuer(repository).issue_invitation()
    original = repository.find_by_code(result.code)
    with pytest.raises(IntegrityError):
        repository.save(replace(original, id='duplicate'))
    assert repository.find_by_code(result.code) == original
    assert len(db_session.scalars(select(InvitationRecord)).all()) == 1
