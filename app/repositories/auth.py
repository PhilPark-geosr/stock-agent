from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.auth import LoginIdentity, UserAccount
from app.domain.models import UserAccountRecord
from app.interfaces.auth import UserAccountRepository


class SqlAlchemyUserAccountRepository(UserAccountRepository):
    def __init__(self, db: Session) -> None:
        self.db = db

    def find_by_login_identity(self, identity: LoginIdentity) -> UserAccount | None:
        record = self.db.scalar(
            select(UserAccountRecord).where(
                UserAccountRecord.login_provider == identity.provider,
                UserAccountRecord.provider_subject_id == identity.provider_subject_id,
            )
        )
        return self._to_domain(record) if record else None

    def save_or_get_existing(self, account: UserAccount) -> UserAccount:
        existing = self.find_by_login_identity(account.login_identity)
        if existing is not None:
            return existing
        record = UserAccountRecord(
            id=account.id,
            login_provider=account.login_identity.provider,
            provider_subject_id=account.login_identity.provider_subject_id,
        )
        self.db.add(record)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = self.find_by_login_identity(account.login_identity)
            if existing is not None:
                return existing
            raise
        return account

    @staticmethod
    def _to_domain(record: UserAccountRecord) -> UserAccount:
        return UserAccount(
            id=record.id,
            login_identity=LoginIdentity(record.login_provider, record.provider_subject_id),
        )

