from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier, Event
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.application.briefing_delivery import BriefingDelivery
from app.cli.briefing_prompt import preview_fixture
from app.core.database import Base
from app.domain.briefing_records import PromptVersionRecord
from app.domain.briefings import BriefingSettings
from app.domain.auth import LoginIdentity, UserAccount
from app.repositories.auth import SqlAlchemyUserAccountRepository
from app.repositories.briefings import BriefingHistory


def test_atomic_claims_across_separate_connections(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'concurrent.db').as_posix()}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    context, _ = preview_fixture()
    now = datetime(2026, 9, 1, 23, 30, tzinfo=timezone.utc)
    clock = lambda: now
    with sessions() as db:
        account = SqlAlchemyUserAccountRepository(db).save_or_get_existing(UserAccount.register(LoginIdentity("kakao", "concurrent")))
        owner = account.id
        db.add(PromptVersionRecord(id="p", content="test", created_at=now))
        db.commit()
    barrier = Barrier(2)
    def reserve():
        with sessions() as db:
            barrier.wait(timeout=5)
            row, created = BriefingHistory(db, clock).reserve(owner, "same-request", {}, context, "p", None, None)
            return row.id, created
    with ThreadPoolExecutor(max_workers=2) as workers:
        rows = list(workers.map(lambda _: reserve(), range(2)))
    assert rows[0][0] == rows[1][0]
    assert sum(created for _, created in rows) == 1
    run_id = rows[0][0]
    with sessions() as db:
        history = BriefingHistory(db, clock)
        history.save_settings(owner, "KR", BriefingSettings(n=1, kakao_enabled=True))
        row = history.get(owner, run_id)
        history.finish(row, row.claim_token, status="completed", result={}, message="test")
    entered, release = Event(), Event()
    calls = []
    class Connections:
        def get_active(self, **kwargs):
            return SimpleNamespace(id=None)
    class Sender:
        def send(self, **kwargs):
            calls.append(kwargs)
            entered.set()
            assert release.wait(timeout=5)
    def deliver():
        with sessions() as db:
            return BriefingDelivery(BriefingHistory(db, clock), Connections(), Sender(), clock).deliver(owner, run_id).status
    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(deliver)
        try:
            assert entered.wait(timeout=5)
            second = workers.submit(deliver)
            assert second.result(timeout=5) == "sending"
        finally:
            release.set()
        assert first.result(timeout=5) == "sent"
    assert len(calls) == 1
    engine.dispose()
