from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.application.stock_search import SecuritySelectionService, index_briefing_subjects
from app.domain.briefing_records import BriefingRunRecord
from app.domain.catalog import BriefingSubjectRecord, CatalogStateRecord, SecurityRecord
from app.domain.models import CustomAlertConditionRecord, WatchlistSubscription
from app.domain.symbols import StockSymbol
from app.repositories.catalog import SecurityCatalogReader
from app.repositories.repositories import WatchlistRepository


@pytest.fixture
def legacy(db_session, current_account):
    row = WatchlistRepository(db_session).add(current_account.id, StockSymbol.of("MSFT"))
    return row


def payload(**changes):
    return {"symbol": "MSFT", "security_id": "test-MSFT", "confirmed": True, **changes}


def link(client, row, **changes):
    return client.post(f"/watchlist/{row.id}/security-link", json=payload(**changes))


def table_rows(db, model):
    return list(db.execute(select(model.__table__)).mappings())


def test_confirmed_link_preserves_subscription_conditions_and_history(client, legacy, db_session, current_account, rule_validation_agent):
    started = legacy.created_at
    for enabled in (True, False):
        db_session.add(CustomAlertConditionRecord(subscription_id=legacy.id, symbol="MSFT", name="existing",
            user_rule=f"rule-{enabled}", validation_summary="validated", enabled=enabled))
    run = BriefingRunRecord(id=str(uuid4()), owner_id=current_account.id, request_key=str(uuid4()), request_data={},
        market="US", purpose="post_market", trade_date="2026-10-01", context={"symbols": ["MSFT"]},
        prompt_id="test", status="completed", created_at=datetime.now(timezone.utc), result={"summary": "original"})
    db_session.add(run)
    db_session.flush()
    index_briefing_subjects(db_session, run)
    db_session.commit()
    models = [CustomAlertConditionRecord, BriefingRunRecord, BriefingSubjectRecord]
    before = [table_rows(db_session, model) for model in models]
    response = link(client, legacy)
    assert response.status_code == 200, response.text
    assert response.json()["id"] == legacy.id
    assert response.json()["security_id"] == "test-MSFT"
    assert legacy.created_at.replace(tzinfo=None) == started.replace(tzinfo=None)
    assert legacy.ended_at is None
    assert [table_rows(db_session, model) for model in models] == before
    assert link(client, legacy).json() == response.json()
    assert len(WatchlistRepository(db_session).list(current_account.id)) == 2
    assert rule_validation_agent.calls == []
    assert SecuritySelectionService(db_session).subscription(current_account.id, legacy.id, "MSFT").id == legacy.id


@pytest.mark.parametrize("confirmation", [False, 1, "true", None])
def test_explicit_boolean_confirmation_required(client, legacy, confirmation):
    body = payload(confirmed=confirmation)
    if confirmation is None:
        del body["confirmed"]
    assert client.post(f"/watchlist/{legacy.id}/security-link", json=body).status_code == 422
    assert legacy.security_id is None


@pytest.mark.parametrize("case", ["delisted", "unknown", "pending", "stale", "mismatch", "reused", "already_linked"])
def test_link_rejects_invalid_or_changed_candidate(client, legacy, db_session, case):
    security = db_session.get(SecurityRecord, "test-MSFT")
    changes = {}
    if case in ("delisted", "unknown", "pending"):
        security.status = case
    elif case == "stale":
        db_session.get(CatalogStateRecord, "US").fetched_at = datetime.now(timezone.utc) - timedelta(days=3)
    elif case == "mismatch":
        changes["security_id"] = "test-AAPL"
    elif case == "reused":
        legacy.created_at = datetime.now(timezone.utc) - timedelta(days=30)
    elif case == "already_linked":
        legacy.security_id = "test-AAPL"
    db_session.commit()
    before = table_rows(db_session, WatchlistSubscription)
    assert link(client, legacy, **changes).status_code == 409
    assert table_rows(db_session, WatchlistSubscription) == before


def test_owner_and_deleted_then_recreated_subscription_are_not_retargeted(client, legacy, db_session, current_account):
    other = WatchlistRepository(db_session).add("someone-else", StockSymbol.of("MSFT"))
    assert link(client, other).status_code == 404
    repo = WatchlistRepository(db_session)
    repo.delete(current_account.id, StockSymbol.of("MSFT"))
    replacement = repo.add(current_account.id, StockSymbol.of("MSFT"))
    assert link(client, legacy).status_code == 404
    assert replacement.security_id is None
    assert other.security_id is None


def test_deletion_between_initial_read_and_catalog_lock_is_rechecked(db_session, current_account, legacy):
    class DeletingReader(SecurityCatalogReader):
        def require_active(self, *args, **kwargs):
            security = super().require_active(*args, **kwargs)
            WatchlistRepository(db_session).delete(current_account.id, StockSymbol.of("MSFT"))
            return security
    service = SecuritySelectionService(db_session, DeletingReader(db_session))
    with pytest.raises(LookupError):
        service.link_subscription(current_account.id, legacy.id, "MSFT", "test-MSFT")
    assert legacy.security_id is None
