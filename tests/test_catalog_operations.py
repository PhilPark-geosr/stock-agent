from datetime import timedelta
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.catalog_policy import CatalogPolicy
from app.core.catalog_runtime import run_catalog_tick
from app.domain.catalog import (CatalogAttemptRecord, CatalogBatch, CatalogDelistingRecord,
                                CatalogRevisionRecord, CatalogStateRecord, SecurityRecord)
from app.domain.models import CustomAlertConditionRecord
from app.domain.symbols import StockSymbol
from app.repositories.catalog import CatalogConflict, SecurityCatalogReader, SecurityCatalogWriter
from app.repositories.catalog_operations import CatalogAlertGate, CatalogMaintenance, DelistingEvidence
from app.repositories.repositories import WatchlistRepository
from app.integrations.catalog_sources import AlphaVantageCatalogSource, KrxCatalogSource, CatalogSourceError
from test_stock_search import NOW, entry, publish


def test_policy_defaults_and_invalid_settings_fail_before_requests(db_session, monkeypatch):
    policy = CatalogPolicy.load()
    assert (policy.kr_interval, policy.us_interval, policy.max_source_age_days, policy.max_fetch_age_hours) == (60, 360, 7, 48)
    monkeypatch.setenv("CATALOG_US_INTERVAL_MINUTES", "5")
    class Source:
        country = "US"
        def fetch(self, now): pytest.fail("must validate before external calls")
    with pytest.raises(ValueError, match="at least 360"):
        run_catalog_tick(sessionmaker(bind=db_session.bind), [Source()])
    assert db_session.scalar(select(CatalogAttemptRecord.id)) is None


def test_freshness_boundaries_are_inclusive(db_session):
    publish(db_session, [entry()])
    state = db_session.get(CatalogStateRecord, "US")
    state.source_date = NOW.date() - timedelta(days=7)
    state.fetched_at = NOW - timedelta(hours=48)
    db_session.commit()
    assert SecurityCatalogReader(db_session, lambda: NOW).metadata("US")["state"] == "READY"
    assert SecurityCatalogReader(db_session, lambda: NOW + timedelta(microseconds=1)).metadata("US")["state"] == "STALE"


def test_request_budget_includes_failed_attempts_and_survives_new_writer(db_session, monkeypatch):
    monkeypatch.setenv("CATALOG_US_REQUESTS_PER_24H", "4")
    for minutes in (0, 5):
        writer = SecurityCatalogWriter(db_session, lambda: NOW + timedelta(minutes=minutes))
        token = writer.claim("US")
        assert token
        writer.fail("US", token, "provider_incomplete")
    writer = SecurityCatalogWriter(db_session, lambda: NOW + timedelta(minutes=30))
    assert writer.claim("US") is None
    assert db_session.get(CatalogStateRecord, "US", populate_existing=True).last_error == "request_budget_exhausted"
    assert SecurityCatalogWriter(db_session, lambda: NOW + timedelta(hours=24)).claim("US")


def test_diagnostic_does_not_publish_or_make_stale_data_fresh(db_session):
    publish(db_session, [entry()], NOW - timedelta(days=3))
    class Source:
        country = "US"
        def fetch(self, now):
            return CatalogBatch(country="US", source="TEST", source_date=now.date(), fetched_at=now,
                                entries=[entry()], evidence="test")
    result = run_catalog_tick(sessionmaker(bind=db_session.bind), [Source()], clock=lambda: NOW, verify_only=True)
    assert result["US"]["published"] is False
    assert result["US"]["account_request_limit"] == "not_measured"
    assert SecurityCatalogReader(db_session, lambda: NOW).metadata("US")["state"] == "STALE"
    db_session.expire_all()
    assert db_session.get(CatalogStateRecord, "US").version == 1
    assert db_session.scalar(select(CatalogAttemptRecord).where(CatalogAttemptRecord.status == "verified")).details["accepted_rows"] == 1


def korean_catalog(db):
    publish(db, [entry("005930.KS")], country="KR")
    row = db.scalar(select(SecurityRecord))
    row.source = "KRX"
    row.source_identity = "KR7005930003"
    db.commit()
    return row


def evidence(row, **changes):
    return DelistingEvidence(security_id=row.id, source_identity=row.source_identity,
        effective_on=NOW.date() + timedelta(days=1),
        source_url="https://kind.krx.co.kr/common/disclsviewer.do?method=search&acptno=20261012000001",
        reviewed_by="operator", confirmed=True, **changes)


def test_official_delisting_effective_day_and_correction_are_preserved(db_session):
    row = korean_catalog(db_session)
    maintenance = CatalogMaintenance(db_session, lambda: NOW)
    key = maintenance.record_delisting(evidence(row))
    assert maintenance.record_delisting(evidence(row)) == key
    assert SecurityCatalogReader(db_session, lambda: NOW).effective_status(row) == "active"
    reader = SecurityCatalogReader(db_session, lambda: NOW + timedelta(days=1))
    assert reader.effective_status(row) == "delisted"
    with pytest.raises(CatalogConflict):
        reader.require_active(row.id, row.symbol)
    maintenance.revoke_delisting(key, "corrected official announcement")
    assert reader.effective_status(row) == "active"
    record = db_session.get(CatalogDelistingRecord, key)
    assert record.source_url and record.revoked_at and record.revocation_reason


@pytest.mark.parametrize("url", ["https://kind.krx.co.kr.evil.test/external/a.htm", "http://kind.krx.co.kr/external/a.htm", "https://kind.krx.co.kr/", "https://user@kind.krx.co.kr/external/a.htm"])
def test_delisting_requires_specific_official_document(url):
    with pytest.raises(ValidationError):
        DelistingEvidence(security_id="id", source_identity="KR7005930003", effective_on=NOW.date(),
            source_url=url, reviewed_by="operator", confirmed=True)


def test_delisting_cannot_override_an_active_refresh_or_wrong_identity(db_session):
    row = korean_catalog(db_session)
    with pytest.raises(CatalogConflict):
        CatalogMaintenance(db_session, lambda: NOW).record_delisting(evidence(row).model_copy(update={"source_identity": "KR7000000000"}))
    state = db_session.get(CatalogStateRecord, "KR")
    state.next_at = NOW
    db_session.commit()
    assert SecurityCatalogWriter(db_session, lambda: NOW).claim("KR")
    with pytest.raises(CatalogConflict):
        CatalogMaintenance(db_session, lambda: NOW).record_delisting(evidence(row))


def test_prune_preserves_current_publication_evidence_and_live_attempt(db_session):
    row = korean_catalog(db_session)
    maintenance = CatalogMaintenance(db_session, lambda: NOW)
    key = maintenance.record_delisting(evidence(row))
    db_session.add(CatalogRevisionRecord(country="KR", version=0, source_date=NOW.date(),
        fetched_at=NOW - timedelta(days=91), evidence="old", snapshot={}))
    current = db_session.scalar(select(CatalogRevisionRecord).where(CatalogRevisionRecord.version == 1))
    current.fetched_at = NOW - timedelta(days=91)
    for status in ("failed", "running"):
        db_session.add(CatalogAttemptRecord(id=status, country="KR", started_at=NOW - timedelta(days=366),
            finished_at=NOW - timedelta(days=366) if status == "failed" else None, status=status))
    db_session.commit()
    result = maintenance.prune()
    assert result["KR"] == {"snapshots": 1, "attempts": 1}
    assert db_session.get(CatalogRevisionRecord, current.id)
    assert db_session.get(CatalogDelistingRecord, key)
    assert db_session.get(CatalogAttemptRecord, "running")


def test_existing_alert_hold_restores_without_changing_disabled_conditions(db_session, current_account):
    row = WatchlistRepository(db_session).get(current_account.id, StockSymbol.of("005930.KS"))
    condition = CustomAlertConditionRecord(subscription_id=row.id, symbol=row.symbol, name="off", user_rule="off rule", validation_summary="ok", enabled=False)
    db_session.add(condition)
    db_session.commit()
    gate = CatalogAlertGate(db_session)
    assert gate.allowed(row.id)
    security = db_session.get(SecurityRecord, row.security_id)
    security.status = "unknown"
    db_session.commit()
    assert not gate.allowed(row.id)
    security.status = "active"
    db_session.commit()
    assert gate.allowed(row.id)
    assert condition.enabled is False and condition.ended_at is None
    state = db_session.get(CatalogStateRecord, "KR")
    state.fetched_at -= timedelta(days=3)
    db_session.commit()
    assert not gate.allowed(row.id)


def test_us_scope_and_original_ticker_alias_are_explicit():
    header = "symbol,name,exchange,assetType,ipoDate,delistingDate,status\n"
    def handler(request):
        if request.url.params["state"] == "delisted":
            return httpx.Response(200, text=header + "OLD,Old common,NYSE,Stock,2000-01-01,2020-01-01,Delisted\n")
        return httpx.Response(200, text=header + "BRK.B,Berkshire,NYSE,Stock,1990-01-01,null,Active\nPREF,Preferred shares,NYSE,Stock,1990-01-01,null,Active\nOTC,OTC company,OTC,Stock,1990-01-01,null,Active\nETF,Fund,NYSE,ETF,1990-01-01,null,Active\n")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        batch = AlphaVantageCatalogSource("secret", client).fetch(NOW)
    assert [e.symbol for e in batch.entries] == ["BRK-B", "OLD"]
    assert batch.entries[0].aliases == ["BRK.B"]


def test_krx_rate_limit_uses_the_long_backoff():
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(429))) as client:
        with pytest.raises(CatalogSourceError, match="provider_rate_limit"):
            KrxCatalogSource("secret", client).fetch(NOW)


def test_user_alert_is_checked_before_evaluation_and_again_before_send(db_session, catalog_data):
    from test_user_alert_delivery import _scenario, FixedEvaluator, RecordingSender
    from app.application.user_alerts import UserAlertDispatcher
    from app.application.user_alert_evaluator import AlertEvaluationDecision
    from app.repositories.notifications import (SqlAlchemyAlertEvaluationRepository, SqlAlchemyNotificationDeliveryRepository,
                                               SqlAlchemyUserAlertEvaluationTargetQuery)
    owner, subscription, condition, analysis, connections, _ = _scenario(db_session)
    evaluator = FixedEvaluator(AlertEvaluationDecision(outcome="matched", reason="match", notification_message="message", evidence=[]))
    sender = RecordingSender()
    dispatcher = UserAlertDispatcher(target_query=SqlAlchemyUserAlertEvaluationTargetQuery(db_session),
        evaluation_repository=SqlAlchemyAlertEvaluationRepository(db_session), evaluator=evaluator,
        connection_repository=connections, delivery_repository=SqlAlchemyNotificationDeliveryRepository(db_session),
        sender=sender, catalog_gate=CatalogAlertGate(db_session))
    assert dispatcher.dispatch(analysis).skipped_inactive == 1
    assert not evaluator.calls and not sender.messages
    subscription.security_id = "test-005930.KS"
    db_session.commit()
    original = evaluator.evaluate
    def evaluate(**kwargs):
        result = original(**kwargs)
        db_session.get(SecurityRecord, subscription.security_id).status = "unknown"
        db_session.commit()
        return result
    evaluator.evaluate = evaluate
    assert dispatcher.dispatch(analysis).skipped_inactive == 1
    assert len(evaluator.calls) == 1 and not sender.messages
    db_session.get(SecurityRecord, subscription.security_id).status = "active"
    db_session.commit()
    evaluator.evaluate = original
    # No catch-up of a previously reserved evaluation after recovery.
    assert dispatcher.dispatch(analysis).skipped_duplicate == 1
    from app.repositories.repositories import AnalysisRepository
    fresh = AnalysisRepository(db_session).save(symbol="005930.KS", overall_judgment="up", summary="new")
    assert dispatcher.dispatch(fresh).sent == 1


def test_system_alert_checks_catalog_before_sending(db_session, current_account):
    from app.application.system_alerts import SystemAlertDispatcher
    from app.domain.models import AnalysisResult
    row = WatchlistRepository(db_session).get(current_account.id, StockSymbol.of("005930.KS"))
    db_session.get(SecurityRecord, row.security_id).status = "delisted"
    db_session.commit()
    # The connection/delivery objects must never be used for a held target.
    dispatcher = SystemAlertDispatcher(watchlist_repository=WatchlistRepository(db_session),
        connection_repository=object(), delivery_repository=object(), sender=object(), catalog_gate=CatalogAlertGate(db_session))
    result = dispatcher.dispatch(AnalysisResult(id=1, symbol=row.symbol, should_alert=True, alert_reason="signal"))
    assert result.skipped_catalog == 1 and result.sent == 0


def test_watchlist_explains_hold_and_keeps_record(client, db_session, current_account):
    row = WatchlistRepository(db_session).get(current_account.id, StockSymbol.of("005930.KS"))
    row.security_id = None
    db_session.commit()
    result = client.get("/watchlist").json()
    assert result[0]["id"] == row.id
    assert "연결 확인" in result[0]["alert_hold_reason"]


def test_search_does_not_query_delisting_evidence_per_candidate(db_session):
    from sqlalchemy import event
    from app.application.stock_search import SecuritySelectionService
    publish(db_session, [entry(f"{number:06d}.KS") for number in range(100)], country="KR")
    statements = []
    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(db_session.bind, "before_cursor_execute", capture)
    try:
        result = SecuritySelectionService(db_session, SecurityCatalogReader(db_session, lambda: NOW)).search("owner", "catalog")
    finally:
        event.remove(db_session.bind, "before_cursor_execute", capture)
    assert result["total"] == 100
    assert len([sql for sql in statements if "catalog_delisting_evidence" in sql]) == 1
