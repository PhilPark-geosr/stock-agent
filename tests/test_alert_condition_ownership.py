from datetime import datetime, timezone

import pytest

from app.domain.alert_conditions import RuleValidationResult
from app.domain.auth import LoginIdentity, UserAccount
from app.domain.symbols import StockSymbol
from app.repositories import AlertConditionRepository, WatchlistRepository
from app.repositories.auth import SqlAlchemyUserAccountRepository


VALIDATION = RuleValidationResult(
    is_valid=True,
    normalized_name="price move",
    normalized_rule="Alert when price rises five percent.",
    target_symbol="AAPL",
    validation_summary="valid",
)


def _account(db_session, subject: str) -> UserAccount:
    return SqlAlchemyUserAccountRepository(db_session).save_or_get_existing(
        UserAccount.register(LoginIdentity("kakao", subject))
    )


def test_condition_requires_active_owned_subscription(db_session):
    account = _account(db_session, "owner-1")
    conditions = AlertConditionRepository(db_session)

    with pytest.raises(LookupError, match="active watchlist subscription"):
        conditions.save_validated(
            owner_id=account.id,
            symbol="AAPL",
            user_rule="Notify me when AAPL rises five percent.",
            validation=VALIDATION,
        )


def test_conditions_are_scoped_to_subscription_owner(db_session):
    owner = _account(db_session, "owner-1")
    stranger = _account(db_session, "owner-2")
    watchlist = WatchlistRepository(db_session)
    watchlist.add(owner.id, StockSymbol.of("AAPL"))
    watchlist.add(stranger.id, StockSymbol.of("AAPL"))
    conditions = AlertConditionRepository(db_session)

    condition = conditions.save_validated(
        owner_id=owner.id,
        symbol="AAPL",
        user_rule="Notify me when AAPL rises five percent.",
        validation=VALIDATION,
    )

    assert condition.subscription_id is not None
    assert conditions.list(owner.id) == [condition]
    assert conditions.list(stranger.id) == []
    assert conditions.delete(stranger.id, condition.id) is False
    assert conditions.delete(owner.id, condition.id) is True
    assert conditions.list(owner.id) == []


def test_ending_subscription_ends_conditions_and_resubscribe_does_not_restore_them(db_session):
    owner = _account(db_session, "owner-1")
    watchlist = WatchlistRepository(db_session)
    subscription = watchlist.add(owner.id, StockSymbol.of("AAPL"))
    conditions = AlertConditionRepository(db_session)
    condition = conditions.save_validated(
        owner_id=owner.id,
        symbol="AAPL",
        user_rule="Notify me when AAPL rises five percent.",
        validation=VALIDATION,
    )

    assert watchlist.delete(owner.id, StockSymbol.of("AAPL")) is True
    db_session.refresh(condition)
    assert subscription.ended_at is not None
    assert condition.ended_at == subscription.ended_at

    replacement = watchlist.add(owner.id, StockSymbol.of("AAPL"))
    assert replacement.id != subscription.id
    assert conditions.list(owner.id) == []


def test_legacy_unowned_conditions_are_invisible(db_session):
    from app.domain.models import CustomAlertConditionRecord

    record = CustomAlertConditionRecord(
        subscription_id=None,
        symbol="AAPL",
        name="legacy",
        user_rule="Legacy rule",
        validation_summary="legacy",
        required_tools=[],
        related_symbols=[],
        news_symbols=[],
    )
    db_session.add(record)
    db_session.commit()
    account = _account(db_session, "owner-1")

    assert AlertConditionRepository(db_session).list(account.id) == []
