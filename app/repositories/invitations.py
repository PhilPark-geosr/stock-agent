from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.invitations import Invitation, hash_code
from app.domain.models import InvitationRecord


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class SqlAlchemyInvitationRepository:
    def __init__(self, db: Session):
        self.db = db

    def save(self, invitation: Invitation) -> None:
        self.db.add(InvitationRecord(
            id=invitation.id, code_hash=invitation.code_hash,
            issued_at=invitation.issued_at, expires_at=invitation.expires_at,
            used_at=invitation.used_at,
        ))
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def find_by_code(self, code: str) -> Invitation | None:
        record = self.db.scalar(select(InvitationRecord).where(InvitationRecord.code_hash == hash_code(code)))
        if record is None:
            return None
        return Invitation(
            record.id, record.code_hash, _utc(record.issued_at), _utc(record.expires_at),
            _utc(record.used_at) if record.used_at is not None else None,
        )
