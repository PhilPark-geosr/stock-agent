from cryptography.fernet import Fernet
import httpx
import pytest
from app.application.notification_connections import KakaoNotificationConnectionService, NotificationConnectionError
from app.repositories.notifications import SqlAlchemyNotificationConnectionRepository
from app.domain.models import UserAccountRecord

def test_authorize_and_callback_require_talk_scope_matching_login_identity_and_hide_tokens(db_session):
    account=UserAccountRecord(id="owner", login_provider="kakao", provider_subject_id="42")
    db_session.add(account); db_session.commit()
    repo=SqlAlchemyNotificationConnectionRepository(db_session, Fernet(Fernet.generate_key()))
    def handler(request):
        if request.url.host == "kauth.kakao.com": return httpx.Response(200, json={"access_token":"secret-a","refresh_token":"secret-r","expires_in":100,"refresh_token_expires_in":200})
        return httpx.Response(200, json={"id":42})
    service=KakaoNotificationConnectionService(repo, rest_api_key="key", redirect_uri="http://callback", state_cipher=Fernet(Fernet.generate_key()), client=httpx.Client(transport=httpx.MockTransport(handler)))

    url=service.authorize("owner")
    state=url.split("state=")[1].split("&")[0]
    connection=service.complete(code="code", state=state, expected_subject_id="42", granted_scopes=["talk_message"])

    assert "scope=talk_message" in url
    assert connection.owner_id == "owner"
    assert "secret" not in repr(connection)

def test_callback_rejects_missing_talk_message_scope(db_session):
    repo=SqlAlchemyNotificationConnectionRepository(db_session, Fernet(Fernet.generate_key()))
    service=KakaoNotificationConnectionService(repo, rest_api_key="key", redirect_uri="http://callback", state_cipher=Fernet(Fernet.generate_key()))
    state=service.authorize("owner").split("state=")[1].split("&")[0]
    with pytest.raises(NotificationConnectionError): service.complete(code="code", state=state, expected_subject_id="42", granted_scopes=[])

def test_notification_http_is_unavailable_without_encryption_key_but_analysis_app_stays_available(client, monkeypatch):
    monkeypatch.delenv("NOTIFICATION_TOKEN_FERNET_KEY", raising=False)
    assert client.get("/notification-connections/kakao").status_code == 503
    assert client.get("/health").status_code == 200

def test_callback_converts_provider_network_failure_to_connection_error(db_session):
    db_session.add(UserAccountRecord(id="owner", login_provider="kakao", provider_subject_id="42"))
    db_session.commit()
    repo=SqlAlchemyNotificationConnectionRepository(db_session, Fernet(Fernet.generate_key()))
    def offline(request): raise httpx.ConnectError("offline", request=request)
    service=KakaoNotificationConnectionService(repo, rest_api_key="key", redirect_uri="http://callback",
        state_cipher=Fernet(Fernet.generate_key()), client=httpx.Client(transport=httpx.MockTransport(offline)))
    state=service.authorize("owner").split("state=")[1].split("&")[0]

    with pytest.raises(NotificationConnectionError, match="Kakao token request failed"):
        service.complete(code="code", state=state, expected_subject_id="42", granted_scopes=["talk_message"])
