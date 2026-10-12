from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.application.stock_search import SecuritySelectionService, index_briefing_subjects
from app.core.catalog_runtime import run_catalog_tick
from app.domain.briefing_records import BriefingRunRecord
from app.domain.catalog import CatalogBatch, CatalogEntry, CatalogStateRecord, SecurityRecord
from app.domain.models import CustomAlertConditionRecord
from app.domain.symbols import StockSymbol
from app.integrations.catalog_sources import AlphaVantageCatalogSource, CatalogSourceError, KrxCatalogSource
from app.repositories.catalog import CatalogConflict, SecurityCatalogReader, SecurityCatalogWriter
from app.repositories.repositories import WatchlistRepository

NOW = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)


def entry(symbol="AAA", **kwargs):
    return CatalogEntry(identity=symbol, symbol=symbol, name=symbol, exchange="TEST", kind="common",
                        listed_on=date(2020, 1, 1), **kwargs)


def publish(db, entries, now=NOW, country="US"):
    state = db.get(CatalogStateRecord, country)
    if state:
        state.next_at = now
        db.commit()
    writer = SecurityCatalogWriter(db, lambda: now)
    token = writer.claim(country)
    batch = CatalogBatch(country=country, source="TEST", source_date=now.date(), fetched_at=now,
                         entries=entries, evidence="test source")
    writer.publish(batch, token, 60)
    return batch


def test_publication_missing_is_unknown_and_reused_ticker_gets_new_identity(db_session):
    publish(db_session, [entry(), entry("BBB")])
    old_id = db_session.scalar(select(SecurityRecord.id).where(SecurityRecord.symbol == "AAA"))
    publish(db_session, [entry("BBB")], NOW + timedelta(days=1))
    assert db_session.get(SecurityRecord, old_id).status == "unknown"
    publish(db_session, [entry(delisted_on=date(2026, 10, 13)), entry("BBB"),
        CatalogEntry(identity="new-AAA", symbol="AAA", name="new company", exchange="TEST", kind="common",
                     listed_on=date(2026, 10, 14))], NOW + timedelta(days=2))
    rows = list(db_session.scalars(select(SecurityRecord).where(SecurityRecord.symbol == "AAA")))
    assert {r.status for r in rows} == {"active", "delisted"}
    assert len({r.id for r in rows}) == 2
    with pytest.raises(CatalogConflict):
        SecurityCatalogReader(db_session, lambda: NOW + timedelta(days=2)).require_active(symbol="AAA")


def test_future_effective_dates_not_applied_early(db_session):
    future = NOW.date() + timedelta(days=1)
    publish(db_session, [entry(delisted_on=future), CatalogEntry(identity="new", symbol="NEW", name="new",
        exchange="TEST", kind="common", listed_on=future)])
    assert {r.symbol: r.status for r in db_session.scalars(select(SecurityRecord))} == {"AAA": "active", "NEW": "pending"}


def test_old_worker_cannot_publish_or_overwrite_recovered_worker(db_session):
    first = SecurityCatalogWriter(db_session, lambda: NOW)
    first_token = first.claim("US")
    assert first.claim("US") is None
    later = NOW + timedelta(minutes=11)
    second = SecurityCatalogWriter(db_session, lambda: later)
    second_token = second.claim("US")
    batch = CatalogBatch(country="US", source="TEST", source_date=NOW.date(), fetched_at=later,
                         entries=[entry()], evidence="test")
    with pytest.raises(CatalogConflict):
        second.publish(batch, first_token, 60)
    first.fail("US", first_token, "old failure")
    assert db_session.get(CatalogStateRecord, "US", populate_existing=True).token == second_token
    assert second.publish(batch, second_token, 60) == 1


def test_invalid_country_batch_keeps_last_good_and_other_market_updates(db_session):
    publish(db_session, [entry()])
    state = db_session.get(CatalogStateRecord, "US")
    state.next_at = NOW
    db_session.commit()
    class Source:
        country = "US"
        def fetch(self, now): raise CatalogSourceError("provider_incomplete")
    class Korea:
        country = "KR"
        def fetch(self, now):
            return CatalogBatch(country="KR", source="TEST", source_date=now.date(), fetched_at=now,
                                entries=[entry("005930.KS")], evidence="test")
    results = run_catalog_tick(sessionmaker(bind=db_session.bind), [Source(), Korea()], clock=lambda: NOW)
    db_session.expire_all()
    assert results == {"US": "provider_incomplete", "KR": 1}
    assert db_session.get(CatalogStateRecord, "US").version == 1
    assert db_session.scalar(select(SecurityRecord.status).where(SecurityRecord.symbol == "AAA")) == "active"


def test_scope_sort_before_pagination_and_cursor_owner_isolation(client, current_account, db_session):
    first = client.get("/securities/search", params={"scope": "catalog", "sort": "name_asc", "limit": 1}).json()
    assert first["items"][0]["symbol"] == "AAPL"
    second = client.get("/securities/search", params={"scope": "catalog", "sort": "name_asc", "limit": 1,
        "cursor": first["next_cursor"]}).json()
    assert second["items"][0]["symbol"] == "MSFT"
    assert client.get("/securities/search", params={"scope": "catalog", "sort": "code_asc", "limit": 1,
        "cursor": first["next_cursor"]}).status_code == 409
    with pytest.raises(CatalogConflict):
        SecuritySelectionService(db_session).search("another-owner", "catalog", sort="name_asc", limit=1, cursor=first["next_cursor"])
    own = client.get("/securities/search", params={"scope": "watchlist"}).json()
    assert own["total"] == 1 and own["items"][0]["symbol"] == "005930.KS"
    assert client.get("/securities/search", params={"scope": "catalog", "q": "＠삼성"}).json()["total"] == 1


def test_register_rechecks_status_and_identity(client, db_session):
    row = db_session.get(SecurityRecord, "test-MSFT")
    row.status = "delisted"
    db_session.commit()
    assert client.post("/watchlist", json={"symbol": "MSFT", "security_id": row.id}).status_code == 409
    assert client.post("/watchlist", json={"symbol": "MSFT", "security_id": "test-AAPL"}).status_code == 409
    assert client.post("/watchlist", json={"symbol": "NOTREAL"}).status_code == 409


def test_alert_rechecks_exact_subscription_after_external_validation(client, db_session, current_account, rule_validation_agent):
    repo = WatchlistRepository(db_session)
    old = repo.get(current_account.id, StockSymbol.of("005930.KS")).id
    def validate(**kwargs):
        repo.delete(current_account.id, StockSymbol.of("005930.KS"))
        repo.add(current_account.id, StockSymbol.of("005930.KS"), security_id="test-005930.KS", security_name="삼성전자")
        return rule_validation_agent.result
    rule_validation_agent.validate = validate
    response = client.post("/alert-conditions", json={"symbol": "005930.KS", "subscription_id": old, "user_rule": "price rises 5 percent"})
    assert response.status_code == 404
    assert not list(db_session.scalars(select(CustomAlertConditionRecord)))


def test_alert_cannot_query_another_subscription_or_call_model(client, rule_validation_agent):
    response = client.post("/alert-conditions", json={"symbol": "005930.KS", "subscription_id": 999, "user_rule": "price rises 5 percent"})
    assert response.status_code == 404
    assert rule_validation_agent.calls == []


def test_old_fetch_does_not_become_fresh_by_searching(client, db_session):
    state = db_session.get(CatalogStateRecord, "US")
    state.fetched_at = datetime.now(timezone.utc) - timedelta(days=3)
    db_session.commit()
    result = client.get("/securities/search", params={"scope": "catalog", "country": "US"}).json()
    assert result["catalog"][0]["state"] == "STALE"
    assert all(not item["selectable"] for item in result["items"])
    assert client.post("/watchlist", json={"symbol": "AAPL", "security_id": "test-AAPL"}).status_code == 409


def saved_run(db, owner, symbols, refs=None):
    row = BriefingRunRecord(id=str(uuid4()), owner_id=owner, request_key=str(uuid4()), request_data={},
        market="KR", purpose="post_market", trade_date="2026-10-01", context={"symbols": symbols, "security_refs": refs or {}},
        prompt_id="test", status="completed", created_at=NOW, result={"summary": "Mention MSFT but target differs"})
    db.add(row)
    db.flush()
    index_briefing_subjects(db, row)
    db.commit()
    return row


def test_history_scope_preserves_deleted_delisted_records_and_owner(client, db_session, current_account, agent, market_data):
    owner = current_account.id
    own = saved_run(db_session, owner, ["005930.KS", "UNKNOWN"], {"005930.KS": {"id": "test-005930.KS", "name": "삼성전자"}})
    other = saved_run(db_session, "another-owner", ["SECRET"])
    WatchlistRepository(db_session).delete(owner, StockSymbol.of("005930.KS"))
    db_session.get(SecurityRecord, "test-005930.KS").status = "delisted"
    db_session.commit()
    result = client.get("/securities/search", params={"scope": "briefings"}).json()
    assert result["total"] == 2
    assert all(r["selectable"] for r in result["items"])
    assert client.get("/securities/search", params={"scope": "briefings", "q": "MSFT"}).json()["total"] == 0
    runs = client.get("/briefings", params={"subject": "test-005930.KS"}).json()
    assert [r["id"] for r in runs] == [own.id]
    assert client.get("/briefings", params={"subject": "test-005930.KS", "date_from": "2026-10-02"}).json() == []
    assert client.get("/briefings", params={"date_from": "2026-10-02", "date_to": "2026-10-01"}).status_code == 422
    assert client.get(f"/briefings/{other.id}").status_code == 404
    assert not agent.calls and not market_data.calls


def test_unknown_historical_ticker_is_not_merged_with_current_catalog(db_session, current_account):
    saved_run(db_session, current_account.id, ["AAPL"])
    saved_run(db_session, current_account.id, ["AAPL"])
    result = SecuritySelectionService(db_session).search(current_account.id, "briefings", q="AAPL")
    assert len(result["items"]) == 2
    assert all(r["security_id"] is None and r["key"].startswith("snapshot:") for r in result["items"])


def test_provider_requests_and_delisting_date_are_parsed(caplog):
    import logging
    caplog.set_level(logging.INFO, logger="httpx")
    calls = []
    def handler(request):
        calls.append(request)
        header = "symbol,name,exchange,assetType,ipoDate,delistingDate,status\n"
        data = "AAA,Example,NASDAQ,Stock,2020-01-01,null,Active\n" if request.url.params["state"] == "active" else "OLD,Old,NASDAQ,Stock,2010-01-01,2025-01-01,Delisted\n"
        return httpx.Response(200, text=header + data)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        batch = AlphaVantageCatalogSource("private-key", client).fetch(NOW)
    assert len(calls) == 2 and {r.url.params["state"] for r in calls} == {"active", "delisted"}
    assert all(r.url.params["function"] == "LISTING_STATUS" and r.url.params["date"] == "2026-10-09" for r in calls)
    assert batch.entries[1].delisted_on == date(2025, 1, 1)
    assert "private-key" not in caplog.text and "REDACTED" in caplog.text


def test_provider_error_or_empty_market_is_not_a_valid_snapshot():
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"Information": "limit"}))) as client:
        with pytest.raises(CatalogSourceError, match="provider_rate_limit"):
            AlphaVantageCatalogSource("private-key", client).fetch(NOW)
    def krx(request):
        assert request.headers["AUTH_KEY"] == "private-key"
        assert "apikey" not in request.url.params
        return httpx.Response(200, json={"OutBlock_1": []})
    with httpx.Client(transport=httpx.MockTransport(krx)) as client:
        with pytest.raises(CatalogSourceError, match="provider_incomplete"):
            KrxCatalogSource("private-key", client).fetch(NOW)


def test_krx_combines_both_markets_and_excludes_non_stock_types():
    calls = []
    def handler(request):
        calls.append(request.url.path)
        code = "005930" if "stk_" in request.url.path else "035900"
        row = {"ISU_CD": "KR" + code, "ISU_SRT_CD": code, "ISU_ABBRV": "테스트",
               "ISU_NM": "테스트 종목", "ISU_ENG_NM": "Test stock", "LIST_DD": "2020/01/01", "KIND_STKCERT_TP_NM": "보통주"}
        return httpx.Response(200, json={"OutBlock_1": [row, dict(row, KIND_STKCERT_TP_NM="ETF")]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        batch = KrxCatalogSource("private", client).fetch(NOW)
    assert {r.symbol for r in batch.entries} == {"005930.KS", "035900.KQ"}
    assert len(calls) == 2


def test_initial_unavailable_is_not_an_empty_successful_catalog(db_session):
    result = SecuritySelectionService(db_session).search("owner", "catalog")
    assert result["total"] == 0 and all(c["state"] == "UNAVAILABLE" for c in result["catalog"])


def test_incomplete_or_regressing_batch_does_not_replace_good_catalog(db_session):
    publish(db_session, [entry(f"TEST{i}") for i in range(30)])
    writer = SecurityCatalogWriter(db_session, lambda: NOW + timedelta(hours=2))
    token = writer.claim("US")
    small = CatalogBatch(country="US", source="TEST", source_date=NOW.date(), fetched_at=NOW,
                         entries=[entry()], evidence="truncated")
    with pytest.raises(CatalogConflict, match="completeness"):
        writer.publish(small, token, 60)
    writer.fail("US", token, "refresh_failed")
    assert db_session.get(CatalogStateRecord, "US").version == 1
    assert len(list(db_session.scalars(select(SecurityRecord).where(SecurityRecord.status == "active")))) == 30


def test_api_requires_authentication(client):
    from app.main import app
    from app.api.deps import get_current_account
    del app.dependency_overrides[get_current_account]
    assert client.get("/securities/search?scope=catalog").status_code == 401
