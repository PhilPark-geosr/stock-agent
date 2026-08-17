from app.domain.auth import LoginIdentity, UserAccount
from app.domain.symbols import StockSymbol
from app.repositories import WatchlistRepository
from app.repositories.auth import SqlAlchemyUserAccountRepository


def _account(db_session, subject: str) -> UserAccount:
    return SqlAlchemyUserAccountRepository(db_session).save_or_get_existing(
        UserAccount.register(LoginIdentity("kakao", subject))
    )


def test_subscription_is_idempotent_per_owner_and_symbol(db_session):
    account = _account(db_session, "owner-1")
    repository = WatchlistRepository(db_session)

    first = repository.add(account.id, StockSymbol.of(" aapl "))
    duplicate = repository.add(account.id, StockSymbol.of("AAPL"))

    assert duplicate.id == first.id
    assert duplicate.owner_id == account.id
    assert duplicate.symbol == "AAPL"
    assert len(repository.list(account.id)) == 1


def test_different_accounts_can_subscribe_to_same_symbol(db_session):
    first_account = _account(db_session, "owner-1")
    second_account = _account(db_session, "owner-2")
    repository = WatchlistRepository(db_session)

    first = repository.add(first_account.id, StockSymbol.of("AAPL"))
    second = repository.add(second_account.id, StockSymbol.of("AAPL"))

    assert first.id != second.id
    assert repository.list(first_account.id) == [first]
    assert repository.list(second_account.id) == [second]
    assert repository.list_distinct_active_symbols() == [StockSymbol.of("AAPL")]


def test_ending_subscription_is_owned_and_resubscription_creates_new_id(db_session):
    owner = _account(db_session, "owner-1")
    stranger = _account(db_session, "owner-2")
    repository = WatchlistRepository(db_session)
    first = repository.add(owner.id, StockSymbol.of("AAPL"))

    assert repository.delete(stranger.id, StockSymbol.of("AAPL")) is False
    assert repository.get(owner.id, StockSymbol.of("AAPL")) == first

    assert repository.delete(owner.id, StockSymbol.of("AAPL")) is True
    assert repository.get(owner.id, StockSymbol.of("AAPL")) is None

    second = repository.add(owner.id, StockSymbol.of("AAPL"))
    assert second.id != first.id


def test_legacy_unowned_rows_are_invisible(db_session):
    from app.domain.models import WatchlistSubscription

    db_session.add(WatchlistSubscription(owner_id=None, symbol="AAPL"))
    db_session.commit()

    account = _account(db_session, "owner-1")
    repository = WatchlistRepository(db_session)

    assert repository.list(account.id) == []
    assert repository.list_distinct_active_symbols() == []
