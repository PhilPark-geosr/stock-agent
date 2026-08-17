from sqlalchemy.exc import IntegrityError

from app.domain.auth import LoginIdentity, UserAccount
from app.repositories.auth import SqlAlchemyUserAccountRepository


def test_account_repository_round_trips_login_identity(db_session) -> None:
    repository = SqlAlchemyUserAccountRepository(db_session)
    account = UserAccount.register(LoginIdentity("kakao", "42"))

    saved = repository.save_or_get_existing(account)

    assert repository.find_by_login_identity(LoginIdentity("kakao", "42")) == saved


def test_account_repository_recovers_from_concurrent_duplicate(db_session, monkeypatch) -> None:
    repository = SqlAlchemyUserAccountRepository(db_session)
    existing = repository.save_or_get_existing(UserAccount.register(LoginIdentity("kakao", "42")))
    duplicate = UserAccount.register(LoginIdentity("kakao", "42"))

    result = repository.save_or_get_existing(duplicate)

    assert result == existing
    assert result.id != duplicate.id
