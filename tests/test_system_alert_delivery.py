from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet

from app.application.system_alerts import SystemAlertDispatcher
from app.domain.notifications import NotificationCredentials
from app.domain.models import AnalysisResult, UserAccountRecord, WatchlistSubscription
from app.repositories.notifications import (
    SqlAlchemyNotificationConnectionRepository,
    SqlAlchemyNotificationDeliveryRepository,
)
from app.core.container import build_analysis_service


class RecordingSender:
    def __init__(self, failing_owners=()):
        self.messages = []
        self.failing_owners = set(failing_owners)

    def send(self, *, connection, message):
        self.messages.append((connection.owner_id, message))
        if connection.owner_id in self.failing_owners:
            raise RuntimeError("channel unavailable")


def _credentials():
    now = datetime.now(timezone.utc)
    return NotificationCredentials("access", "refresh", now + timedelta(hours=1), now + timedelta(days=30))


def test_notification_connection_credentials_are_encrypted_and_disconnect_clears_them(db_session):
    db_session.add(UserAccountRecord(id="owner", login_provider="kakao", provider_subject_id="42"))
    db_session.commit()
    repository = SqlAlchemyNotificationConnectionRepository(db_session, Fernet(Fernet.generate_key()))

    connection = repository.create(owner_id="owner", channel="kakao", credentials=_credentials())
    record = repository.get_record(connection.id)

    assert record.encrypted_access_token != "access"
    assert repository.get_credentials(connection.id).access_token == "access"
    repository.disconnect(connection.id)
    assert repository.get_active(owner_id="owner", channel="kakao") is None
    assert record.encrypted_access_token is None

    reconnected = repository.create(owner_id="owner", channel="kakao", credentials=_credentials())
    assert reconnected.id != connection.id


def test_dispatch_sends_one_default_alert_per_subscriber_and_analysis(db_session):
    for owner in ("a", "b"):
        db_session.add(UserAccountRecord(id=owner, login_provider="kakao", provider_subject_id=owner))
        db_session.add(WatchlistSubscription(owner_id=owner, symbol="005930.KS"))
    analysis = AnalysisResult(
        symbol="005930.KS", overall_judgment="caution", summary="volatile", shared_safe=True,
        should_alert=True, triggered_alerts=["price", "volume"], alert_reason="급등과 거래량 급증",
    )
    db_session.add(analysis)
    db_session.commit()
    connections = SqlAlchemyNotificationConnectionRepository(db_session, Fernet(Fernet.generate_key()))
    for owner in ("a", "b"):
        connections.create(owner_id=owner, channel="kakao", credentials=_credentials())
    deliveries = SqlAlchemyNotificationDeliveryRepository(db_session)
    sender = RecordingSender(failing_owners={"b"})
    dispatcher = SystemAlertDispatcher(
        watchlist_repository=__import__("app.repositories.repositories", fromlist=["WatchlistRepository"]).WatchlistRepository(db_session),
        connection_repository=connections, delivery_repository=deliveries, sender=sender,
    )

    result = dispatcher.dispatch(analysis)
    duplicate = dispatcher.dispatch(analysis)

    assert (result.eligible, result.sent, result.failed) == (2, 1, 1)
    assert duplicate.skipped_duplicate == 2
    assert sender.messages == [("a", "급등과 거래량 급증"), ("b", "급등과 거래량 급증")]
    assert [item.status for item in deliveries.list_for_analysis(analysis.id)] == ["sent", "failed"]

def test_scheduled_batch_dispatches_but_manual_analysis_does_not(db_session, market_data, agent, current_account):
    class Dispatcher:
        def __init__(self): self.ids=[]
        def dispatch(self, analysis): self.ids.append(analysis.id)
    dispatcher=Dispatcher()
    service=build_analysis_service(db_session, market_data_provider=market_data, agent=agent, system_alert_dispatcher=dispatcher)

    service.run_manual_analysis("005930.KS")
    service.run_scheduled_batch()

    assert len(dispatcher.ids) == 1

def test_dispatch_ignores_analysis_without_a_valid_system_alert(db_session):
    sender=RecordingSender()
    dispatcher=SystemAlertDispatcher(watchlist_repository=__import__("app.repositories.repositories", fromlist=["WatchlistRepository"]).WatchlistRepository(db_session),
        connection_repository=object(), delivery_repository=object(), sender=sender)
    analysis=AnalysisResult(id=1, symbol="005930.KS", overall_judgment="neutral", summary="steady", shared_safe=True,
        should_alert=False, triggered_alerts=[], alert_reason=None)
    assert dispatcher.dispatch(analysis).eligible == 0
    assert sender.messages == []
