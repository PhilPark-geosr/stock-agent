from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.invitations import Invitation, hash_code
from app.domain.models import BetaAccessGrantRecord, InvitationRecord


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

    def has_beta_access(self, account_id: str) -> bool:
        return self.db.get(BetaAccessGrantRecord, account_id) is not None

    def _add_grant(self, account_id: str, invitation_id: str, granted_at: datetime) -> None:
        self.db.add(BetaAccessGrantRecord(
            account_id=account_id,
            invitation_id=invitation_id,
            granted_at=granted_at,
        ))

    def redeem(self, invitation: Invitation, account_id: str, used_at: datetime) -> bool:
        if self.has_beta_access(account_id):
            return True
        try:
            claimed = self.db.execute(
                update(InvitationRecord)
                .where(
                    InvitationRecord.id == invitation.id,
                    InvitationRecord.used_at.is_(None),
                    InvitationRecord.expires_at > used_at,
                )
                .values(used_at=used_at)
            )
            if claimed.rowcount != 1:
                self.db.rollback()
                return False
            self._add_grant(account_id, invitation.id, used_at)
            self.db.commit()
            return True
        except IntegrityError:
            self.db.rollback()
            # Concurrent redemption with another code for this same account is
            # successful enrollment; its failed transaction did not consume
            # this invitation.
            if self.has_beta_access(account_id):
                return True
            return False
        except Exception:
            self.db.rollback()
            raise
