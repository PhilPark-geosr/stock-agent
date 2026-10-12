from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.api.briefings import get_briefings
from app.cli.briefing_prompt import preview_fixture
from app.core.briefings import build_briefing_coordinator
from app.domain.briefing_records import BriefingRunRecord, PromptVersionRecord
from app.domain.briefings import (
    BriefingConflict, BriefingError, BriefingRequest, BriefingSettings, Evidence, SourceStatus,
)
from app.domain.auth import LoginIdentity, UserAccount
from app.domain.symbols import StockSymbol
from app.integrations.briefing_calendar import calendar
from app.integrations.kakao_notify import KakaoNotifyError
from app.main import app
from app.repositories.auth import SqlAlchemyUserAccountRepository
from app.repositories.repositories import WatchlistRepository


class Clock:
    def __init__(self):
        self.value = datetime(2026, 9, 20, 23, 30, tzinfo=timezone.utc)
    def __call__(self):
        return self.value


class Source:
    def __init__(self):
        self.calls = 0
        self.missing = False
    def fetch(self, symbol, context):
        self.calls += 1
        if self.missing:
            return [], [SourceStatus(symbol=symbol, source="test", kind="chart", status="failed")]
        return [Evidence(id="chart:" + symbol, symbol=symbol, kind="chart", source="test",
            published_at=calendar(context.market).session_close(str(context.sessions[-1])).to_pydatetime(),
            collected_at=context.cutoff_at, text="실제 데이터가 아닌 테스트 일봉",
            data={"candles": [{"date": str(day), "close": 100, "volume": 1000} for day in context.sessions]})], [
            SourceStatus(symbol=symbol, source="test", kind="chart", status="ok")]


class Model:
    def __init__(self):
        self.calls = []
        self.bad = False
        self.error = None
        self.hook = None
    def generate(self, **kwargs):
        self.calls.append(kwargs)
        if self.hook:
            self.hook()
        if self.error:
            raise self.error
        facts = kwargs["payload"]["evidence"]["evidence"]
        return {"summary": "제공된 자료에 근거한 테스트 결과", "items": [
            {"symbol": s, "verdict": "보류", "reason": "추가 관찰이 필요합니다.",
             "evidence_ids": ["invented" if self.bad else next(e["id"] for e in facts if e["symbol"] == s)],
             "comparison_reason": "판단 기준이 유지됐습니다.", "next_observation": "거래량 변화를 관찰합니다."}
            for s in kwargs["payload"]["analyze_symbols"]]}


class Connections:
    def __init__(self):
        self.enabled = True
    def get_active(self, *, owner_id, channel):
        return SimpleNamespace(id="connection", owner_id=owner_id) if self.enabled else None


class Sender:
    def __init__(self):
        self.messages = []
        self.error = None
    def send(self, *, connection, message):
        self.messages.append((connection.owner_id, message))
        if self.error:
            raise self.error


@pytest.fixture
def setup_briefing(db_session, current_account, tmp_path):
    clock, source, model, sender, connections = Clock(), Source(), Model(), Sender(), Connections()
    service = build_briefing_coordinator(db_session, clock=clock, sources=[source], model=model,
        sender=sender, connections=connections)
    path = tmp_path / "prompt.md"
    path.write_text("근거와 한계를 한국어로 설명한다.", encoding="utf-8")
    service.prompts.path = path
    version, _ = service.prompts.preview(service.analyzer, *preview_fixture())
    service.prompts.activate(version)
    model.calls.clear()
    return SimpleNamespace(service=service, clock=clock, source=source, model=model, sender=sender,
        connections=connections, owner=current_account.id, db=db_session, path=path)


def request(**values):
    return BriefingRequest(request_id=str(uuid4()), market="KR", purpose="pre_market", n=2, **values)


def test_selection_analyzes_only_explicit_owned_targets_and_preserves_snapshot(setup_briefing):
    s = setup_briefing
    WatchlistRepository(s.db).add(s.owner, StockSymbol.of("000660.KS"))
    req = request(symbols=["005930.KS"])
    row = s.service.generate(s.owner, req)
    assert row.context["symbols"] == ["005930.KS"]
    assert [item["symbol"] for item in row.result["items"]] == ["005930.KS"]
    assert s.source.calls == 1
    with pytest.raises(BriefingConflict):
        s.service.generate(s.owner, req.model_copy(update={"symbols": ["000660.KS"]}))
    with pytest.raises(BriefingError):
        s.service.generate(s.owner, request(symbols=["AAPL"]))
    with pytest.raises(BriefingError):
        s.service.generate(s.owner, request(symbols=["035420.KS"]))


def test_saved_selection_is_used_for_scheduling_without_including_new_subscriptions(setup_briefing):
    s = setup_briefing
    s.service.history.save_settings(s.owner, "KR", BriefingSettings(n=2, symbols=["005930.KS"]))
    WatchlistRepository(s.db).add(s.owner, StockSymbol.of("000660.KS"))
    context = s.service.context_source.build(s.owner, request(), s.clock())
    assert context.symbols == ["005930.KS"]
    context = s.service.context_source.build(s.owner, request(symbols=["000660.KS"]), s.clock())
    assert context.symbols == ["000660.KS"]
    assert s.service.history.settings(s.owner, "KR").symbols == ["005930.KS"]
    WatchlistRepository(s.db).delete(s.owner, StockSymbol.of("005930.KS"))
    with pytest.raises(BriefingError):
        s.service.context_source.build(s.owner, request(), s.clock())


def test_selection_api_rejects_empty_duplicate_foreign_and_exposes_readiness(client, setup_briefing):
    s = setup_briefing
    app.dependency_overrides[get_briefings] = lambda: s.service
    options = client.get("/briefings/options/KR")
    assert options.status_code == 200
    assert options.json()["symbols"] == ["005930.KS"]
    assert options.json()["purposes"]["pre_market"]["available"] is True
    assert options.json()["purposes"]["post_market"]["available"] is False
    for symbols in ([], ["005930.KS", "005930.ks"], ["035420.KS"], ["AAPL"]):
        assert client.put("/briefings/settings/KR", json={"n": 2, "symbols": symbols}).status_code == 422
    assert client.post("/briefings", json={**request().model_dump(mode="json"), "symbols": []}).status_code == 422
    result = client.put("/briefings/settings/KR", json={"n": 2, "symbols": ["005930.ks"]})
    assert result.status_code == 200 and result.json()["symbols"] == ["005930.KS"]


def test_first_briefing_is_scoped_immutable_and_idempotent(setup_briefing):
    s = setup_briefing
    req = request()
    row = s.service.generate(s.owner, req)
    assert row.status == "completed"
    assert row.result["items"][0]["comparison"] == "비교 불가"
    assert row.context["sessions"] == ["2026-09-17", "2026-09-18"]
    assert s.service.generate(s.owner, req).id == row.id
    assert len(s.model.calls) == 1 and s.source.calls == 1
    with pytest.raises(BriefingConflict):
        s.service.generate(s.owner, req.model_copy(update={"n": 3}))
    WatchlistRepository(s.db).delete(s.owner, StockSymbol.of("005930.KS"))
    assert s.service.history.get(s.owner, row.id).context["symbols"] == ["005930.KS"]
    assert s.service.history.payload(row)["prompt_content"] == "근거와 한계를 한국어로 설명한다."


def test_afternoon_compares_todays_morning_and_previous_day_fallback(setup_briefing):
    s = setup_briefing
    morning = s.service.generate(s.owner, request())
    s.clock.value = datetime(2026, 9, 21, 7, tzinfo=timezone.utc)
    afternoon = s.service.generate(s.owner, request().model_copy(update={"purpose": "post_market"}))
    assert afternoon.previous_id == morning.id
    assert afternoon.result["items"][0]["comparison"] == "유지"
    s.clock.value = datetime(2026, 9, 21, 23, 30, tzinfo=timezone.utc)
    tomorrow = s.service.generate(s.owner, request())
    assert tomorrow.previous_id == afternoon.id
    assert "2026-09-21" in tomorrow.result["items"][0]["comparison_reason"]


def test_no_morning_marks_comparison_unavailable_and_missing_data_defers(setup_briefing):
    s = setup_briefing
    s.clock.value = datetime(2026, 9, 21, 7, tzinfo=timezone.utc)
    row = s.service.generate(s.owner, request().model_copy(update={"purpose": "post_market"}))
    assert "오늘 장전" in " ".join(row.result["items"][0]["limitations"])
    s.source.missing = True
    deferred = s.service.generate(s.owner, request().model_copy(update={"purpose": "post_market"}))
    assert deferred.status == "deferred"
    assert s.service.history.delivery(deferred.id) is None
    assert len(s.model.calls) == 1


def test_invalid_model_evidence_retries_once_and_transport_does_not(setup_briefing):
    s = setup_briefing
    s.model.bad = True
    row = s.service.generate(s.owner, request())
    assert row.status == "failed" and len(s.model.calls) == 2
    assert s.model.calls[1]["validation_errors"]
    assert s.service.history.delivery(row.id) is None
    s.model.bad = False
    s.model.error = RuntimeError("transport credentials=SECRET")
    failed = s.service.generate(s.owner, request())
    assert failed.status == "failed" and len(s.model.calls) == 3
    assert "SECRET" not in failed.failure_reason


def test_prompt_change_freezes_inflight_and_old_results_and_requires_repreview(setup_briefing):
    s = setup_briefing
    old = s.service.prompts.active().id
    s.path.write_text("공시 내용을 더 자세히 설명한다.", encoding="utf-8")
    new, _ = s.service.prompts.preview(s.service.analyzer, *preview_fixture())
    s.path.write_text("검증 이후 바뀐 내용", encoding="utf-8")
    with pytest.raises(BriefingConflict):
        s.service.prompts.activate(new)
    s.path.write_text("공시 내용을 더 자세히 설명한다.", encoding="utf-8")
    s.model.hook = lambda: s.service.prompts.activate(new)
    first = s.service.generate(s.owner, request())
    assert first.prompt_id == old
    s.model.hook = None
    second = s.service.generate(s.owner, request())
    assert second.prompt_id == new
    s.path.unlink()
    assert s.service.prompts.active().id == new
    s.service.prompts.activate(old, rollback=True)
    assert s.service.prompts.active().id == old
    assert s.service.history.payload(first)["prompt_content"] != s.service.history.payload(second)["prompt_content"]


def test_delivery_failure_keeps_result_and_retry_never_reanalyzes(setup_briefing):
    s = setup_briefing
    s.service.history.save_settings(s.owner, "KR", BriefingSettings(n=2, kakao_enabled=True))
    s.sender.error = KakaoNotifyError("rejected")
    row = s.service.generate(s.owner, request())
    assert row.status == "completed"
    assert s.service.history.delivery(row.id).status == "failed"
    s.sender.error = None
    retry_id = str(uuid4())
    s.service.delivery.deliver(s.owner, row.id, retry_id=retry_id)
    s.service.delivery.deliver(s.owner, row.id, retry_id=retry_id)
    assert len(s.sender.messages) == 2 and len(s.model.calls) == 1
    assert s.service.history.delivery(row.id).status == "sent"


def test_unknown_delivery_needs_explicit_ack_and_disconnect_blocks_send(setup_briefing):
    s = setup_briefing
    s.service.history.save_settings(s.owner, "KR", BriefingSettings(n=2, kakao_enabled=True))
    s.sender.error = httpx.ReadTimeout("response lost")
    row = s.service.generate(s.owner, request())
    assert s.service.history.delivery(row.id).status == "unknown"
    with pytest.raises(BriefingConflict):
        s.service.delivery.deliver(s.owner, row.id, retry_id=str(uuid4()))
    s.service.delivery.deliver(s.owner, row.id)
    assert len(s.sender.messages) == 1
    s.connections.enabled = False
    s.service.delivery.deliver(s.owner, row.id, retry_id=str(uuid4()), acknowledge_unknown=True)
    assert s.service.history.delivery(row.id).status == "not_connected"
    assert len(s.sender.messages) == 1


def test_recovery_uses_snapshot_and_rejects_old_worker(setup_briefing):
    s = setup_briefing
    req = request()
    ctx = s.service.context_source.build(s.owner, req, s.clock())
    row, _ = s.service.history.reserve(s.owner, "manual:" + req.request_id, req.model_dump(mode="json"),
        ctx, s.service.prompts.active().id, None, None)
    token = row.claim_token
    snapshot = s.service.evidence.build(ctx)
    s.service.history.snapshot(row.id, token, snapshot)
    s.clock.value += timedelta(minutes=11)
    recovered = s.service.recover(row)
    assert recovered.status == "completed"
    assert s.source.calls == 1
    from app.domain.briefings import LostClaim
    with pytest.raises(LostClaim):
        s.service.history.renew(row.id, token)


def test_missing_n_and_non_session_and_early_close_rules(setup_briefing):
    s = setup_briefing
    with pytest.raises(BriefingError, match="관찰기간"):
        s.service.generate(s.owner, request().model_copy(update={"n": None}))
    s.clock.value = datetime(2026, 9, 19, 0, tzinfo=timezone.utc)
    with pytest.raises(BriefingError, match="거래일"):
        s.service.generate(s.owner, request())
    s.clock.value = datetime(2026, 9, 21, 6, 35, tzinfo=timezone.utc)
    with pytest.raises(BriefingError, match="15분"):
        s.service.generate(s.owner, request().model_copy(update={"purpose": "post_market"}))


def test_api_ownership_settings_and_request_validation(client, setup_briefing):
    s = setup_briefing
    app.dependency_overrides[get_briefings] = lambda: s.service
    response = client.post("/briefings", json=request().model_dump(mode="json"))
    assert response.status_code == 201
    run_id = response.json()["id"]
    assert client.get(f"/briefings/{run_id}").status_code == 200
    assert len(client.get("/briefings").json()) == 1
    body = request().model_dump(mode="json")
    body["owner_id"] = "someone-else"
    assert client.post("/briefings", json=body).status_code == 422
    assert client.put("/briefings/settings/KR", json={"pre_market_enabled": True}).status_code == 422
    from app.api.deps import get_current_account
    other = SqlAlchemyUserAccountRepository(s.db).save_or_get_existing(UserAccount.register(LoginIdentity("kakao", "another")))
    app.dependency_overrides[get_current_account] = lambda: other
    assert client.get(f"/briefings/{run_id}").status_code == 404
    assert client.get("/briefings").json() == []
    assert client.post(f"/briefings/{run_id}/delivery", json={"request_id": str(uuid4())}).status_code == 404


def test_scheduler_isolates_users_and_recovers_outbox_without_reanalysis(setup_briefing):
    from sqlalchemy.orm import sessionmaker
    from app.core.briefing_runtime import run_briefing_tick
    s = setup_briefing
    other = SqlAlchemyUserAccountRepository(s.db).save_or_get_existing(UserAccount.register(LoginIdentity("kakao", "no-watchlist")))
    s.service.history.save_settings(other.id, "KR", BriefingSettings(n=2, pre_market_enabled=True))
    s.service.history.save_settings(s.owner, "KR", BriefingSettings(n=2, pre_market_enabled=True, kakao_enabled=True))
    factory = sessionmaker(bind=s.db.get_bind())
    def builder(db):
        return build_briefing_coordinator(db, clock=s.clock, sources=[s.source], model=s.model,
            sender=s.sender, connections=s.connections)
    run_briefing_tick(factory, now=s.clock(), builder=builder)
    run_briefing_tick(factory, now=s.clock(), builder=builder)
    assert len(s.model.calls) == 1 and len(s.sender.messages) == 1
    row = s.service.history.list(s.owner)[0]
    assert row.request_key == "scheduled:KR:2026-09-21:pre_market"
    assert not s.service.history.list(other.id)
    # Result committed while the process failed before attempting delivery.
    def unavailable(*args, **kwargs):
        raise RuntimeError("interrupted before delivery claim")
    s.service.delivery.deliver = unavailable
    pending = s.service.generate(s.owner, request())
    assert s.service.history.delivery(pending.id).status == "pending"
    run_briefing_tick(factory, now=s.clock(), builder=builder)
    s.db.expire_all()
    assert s.service.history.delivery(pending.id).status == "sent"
    assert len(s.model.calls) == 2 and len(s.sender.messages) == 2


def test_expired_delivery_becomes_unknown_and_incomplete_generation_fails(setup_briefing):
    s = setup_briefing
    row = s.service.generate(s.owner, request())
    delivery = s.service.history.delivery(row.id)
    delivery.status = "sending"
    delivery.lease_until = s.clock() - timedelta(seconds=1)
    delivery.claim_token = str(uuid4())
    delivery.attempts = [{"request_id": "initial", "status": "sending"}]
    s.db.commit()
    s.service.delivery.deliver(s.owner, row.id)
    assert s.service.history.delivery(row.id).status == "unknown"
    assert not s.sender.messages
    req = request()
    context = s.service.context_source.build(s.owner, req, s.clock())
    pending, _ = s.service.history.reserve(s.owner, "manual:" + req.request_id,
        req.model_dump(mode="json"), context, s.service.prompts.active().id, None, None)
    s.clock.value += timedelta(minutes=11)
    assert s.service.recover(pending).status == "failed"
    assert len(s.model.calls) == 1
