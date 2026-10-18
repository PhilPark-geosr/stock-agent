from cryptography.fernet import Fernet
import httpx
import pytest
from urllib.parse import parse_qs, urlsplit
import json
from app.application.notification_connections import KakaoNotificationConnectionService, NotificationConnectionError
from app.repositories.notifications import SqlAlchemyNotificationConnectionRepository
from app.domain.models import UserAccountRecord
from app.main import app
from app.api.deps import get_notification_connection_service

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


def test_web_notification_authorization_mode_is_inside_encrypted_state(db_session):
    repo = SqlAlchemyNotificationConnectionRepository(db_session, Fernet(Fernet.generate_key()))
    service = KakaoNotificationConnectionService(repo, rest_api_key="key", redirect_uri="http://callback", state_cipher=Fernet(Fernet.generate_key()))
    web_state = parse_qs(urlsplit(service.authorize("owner", client="web")).query)["state"][0]
    electron_state = parse_qs(urlsplit(service.authorize("owner")).query)["state"][0]

    assert service.context_from_state(web_state) == {"owner_id": "owner", "client": "web"}
    assert service.context_from_state(electron_state) == {"owner_id": "owner", "client": "electron"}
    with pytest.raises(NotificationConnectionError):
        service.context_from_state(web_state + "tampered")
    expired = service.state_cipher.encrypt_at_time(json.dumps({"owner_id": "owner", "client": "web"}).encode(), current_time=1).decode()
    with pytest.raises(NotificationConnectionError):
        service.context_from_state(expired)


def test_web_notification_callback_returns_to_configured_app_and_electron_keeps_html(client, current_account, monkeypatch):
    monkeypatch.setenv("WEB_ORIGIN", "http://testserver")
    calls = []

    class Service:
        def authorize(self, owner_id, *, client="electron"):
            calls.append((owner_id, client))
            return "https://kauth.kakao.com/oauth/authorize?state=opaque"

        def context_from_state(self, state):
            if state == "invalid":
                raise NotificationConnectionError("invalid state")
            return {"owner_id": current_account.id, "client": state}

        def complete(self, **kwargs):
            if kwargs["code"] == "bad":
                raise NotificationConnectionError("consent failed")

    app.dependency_overrides[get_notification_connection_service] = lambda: Service()
    web_start = client.post("/notification-connections/kakao/authorize", json={"client": "web"})
    electron_start = client.post("/notification-connections/kakao/authorize")
    assert web_start.status_code == electron_start.status_code == 200
    assert calls == [(current_account.id, "web"), (current_account.id, "electron")]

    success = client.get("/notification-connections/kakao/callback?state=web&code=ok", follow_redirects=False)
    failure = client.get("/notification-connections/kakao/callback?state=web&code=bad", follow_redirects=False)
    denied = client.get("/notification-connections/kakao/callback?state=web&error=access_denied", follow_redirects=False)
    electron = client.get("/notification-connections/kakao/callback?state=electron&code=ok", follow_redirects=False)
    invalid = client.get("/notification-connections/kakao/callback?state=invalid&code=ok", follow_redirects=False)

    assert success.status_code == failure.status_code == 303
    assert success.headers["location"] == "http://testserver/app?notification_connection=connected"
    assert failure.headers["location"] == "http://testserver/app?notification_connection=failed"
    assert denied.headers["location"] == "http://testserver/app?notification_connection=failed"
    assert electron.status_code == 200 and "완료" in electron.text
    assert invalid.status_code == 400 and "location" not in invalid.headers
