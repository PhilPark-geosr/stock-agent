from datetime import datetime, timedelta, timezone
import httpx
from app.domain.notifications import NotificationConnection, NotificationCredentials
from app.integrations.kakao_notify import KakaoNotificationSender

class CredentialRepository:
    def __init__(self, credentials): self.credentials=credentials; self.updated=[]; self.disconnected=[]
    def get_credentials(self, _): return self.credentials
    def update_credentials(self, _, credentials): self.credentials=credentials; self.updated.append(credentials)
    def disconnect(self, connection_id): self.disconnected.append(connection_id)

def test_sender_refreshes_expiring_token_preserves_refresh_token_and_sends_once():
    now=datetime(2026, 1, 1, tzinfo=timezone.utc)
    repo=CredentialRepository(NotificationCredentials("old-access", "old-refresh", now, now+timedelta(days=10)))
    requests=[]
    def handler(request):
        requests.append(request)
        if request.url.host == "kauth.kakao.com": return httpx.Response(200, json={"access_token":"new-access","expires_in":21600})
        return httpx.Response(200, json={"result_code":0})
    sender=KakaoNotificationSender(repo, rest_api_key="key", client=httpx.Client(transport=httpx.MockTransport(handler)), now_provider=lambda: now)
    connection=NotificationConnection("id", "owner", "kakao", now)

    sender.send(connection=connection, message="alert")

    assert repo.credentials.refresh_token == "old-refresh"
    assert requests[-1].headers["Authorization"] == "Bearer new-access"
    assert len([request for request in requests if "memo" in request.url.path]) == 1

def test_sender_disconnects_when_refresh_credential_is_rejected():
    now=datetime(2026, 1, 1, tzinfo=timezone.utc)
    repo=CredentialRepository(NotificationCredentials("old", "expired", now, now))
    sender=KakaoNotificationSender(repo, rest_api_key="key", client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(401, json={}))), now_provider=lambda: now)
    connection=NotificationConnection("id", "owner", "kakao", now)

    try: sender.send(connection=connection, message="alert")
    except RuntimeError: pass

    assert repo.disconnected == ["id"]

def test_sender_recovers_once_from_unauthorized_access_token():
    now=datetime(2026, 1, 1, tzinfo=timezone.utc)
    repo=CredentialRepository(NotificationCredentials("stale", "refresh", now+timedelta(hours=1), now+timedelta(days=1)))
    calls=[]
    def handler(request):
        calls.append(request)
        if request.url.host == "kauth.kakao.com": return httpx.Response(200, json={"access_token":"fresh","expires_in":100})
        if request.headers["Authorization"] == "Bearer stale": return httpx.Response(401, json={})
        return httpx.Response(200, json={"result_code":0})
    sender=KakaoNotificationSender(repo, rest_api_key="key", client=httpx.Client(transport=httpx.MockTransport(handler)), now_provider=lambda: now)
    sender.send(connection=NotificationConnection("id", "owner", "kakao", now), message="alert")
    assert len([request for request in calls if "memo" in request.url.path]) == 2
    assert repo.disconnected == []

def test_sender_keeps_connection_active_on_network_failure():
    now=datetime(2026, 1, 1, tzinfo=timezone.utc)
    repo=CredentialRepository(NotificationCredentials("access", "refresh", now+timedelta(hours=1), now+timedelta(days=1)))
    def handler(request): raise httpx.ConnectError("offline", request=request)
    sender=KakaoNotificationSender(repo, rest_api_key="key", client=httpx.Client(transport=httpx.MockTransport(handler)), now_provider=lambda: now)
    with __import__("pytest").raises(httpx.ConnectError): sender.send(connection=NotificationConnection("id", "owner", "kakao", now), message="alert")
    assert repo.disconnected == []
