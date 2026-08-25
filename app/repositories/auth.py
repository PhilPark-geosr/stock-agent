from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.auth import AuthSession, LoginAttempt, LoginIdentity, UserAccount
from app.domain.models import AuthSessionRecord, LoginAttemptRecord, UserAccountRecord
from app.interfaces.auth import AuthSessionRepository, LoginAttemptRepository, UserAccountRepository


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


def _account(db: Session, account_id: str | None) -> UserAccount | None:
    record = db.get(UserAccountRecord, account_id) if account_id else None
    return SqlAlchemyUserAccountRepository._to_domain(record) if record else None


class SqlAlchemyLoginAttemptRepository(LoginAttemptRepository):
    def __init__(self, db: Session) -> None: self.db = db

    def save(self, attempt: LoginAttempt) -> None:
        record = self.db.get(LoginAttemptRecord, attempt.id) or LoginAttemptRecord(id=attempt.id)
        record.state_hash = attempt.state_hash
        record.verifier_challenge = attempt.verifier_challenge
        record.user_account_id = attempt.account.id if attempt.account else None
        record.expires_at = attempt.expires_at
        record.consumed_at = attempt.consumed_at
        self.db.add(record); self.db.commit()

    def get(self, attempt_id: str) -> LoginAttempt | None:
        return self._to_domain(self.db.get(LoginAttemptRecord, attempt_id))

    def find_by_state_hash(self, state_hash: str) -> LoginAttempt | None:
        return self._to_domain(self.db.scalar(select(LoginAttemptRecord).where(LoginAttemptRecord.state_hash == state_hash)))

    def _to_domain(self, record: LoginAttemptRecord | None) -> LoginAttempt | None:
        if record is None: return None
        return LoginAttempt(record.id, record.state_hash, record.verifier_challenge, record.expires_at, _account(self.db, record.user_account_id), record.consumed_at)


class SqlAlchemyAuthSessionRepository(AuthSessionRepository):
    def __init__(self, db: Session) -> None: self.db = db

    def save(self, session: AuthSession) -> None:
        record = self.db.get(AuthSessionRecord, session.id) or AuthSessionRecord(id=session.id)
        record.user_account_id = session.account.id
        record.token_hash = session.token_hash
        record.expires_at = session.expires_at
        record.revoked_at = session.revoked_at
        self.db.add(record); self.db.commit()

    def find_by_token_hash(self, token_hash: str) -> AuthSession | None:
        record = self.db.scalar(select(AuthSessionRecord).where(AuthSessionRecord.token_hash == token_hash))
        if record is None: return None
        account = _account(self.db, record.user_account_id)
        if account is None: return None
        return AuthSession(record.id, account, record.token_hash, record.expires_at, record.revoked_at)
