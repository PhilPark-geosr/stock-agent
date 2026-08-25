from datetime import datetime, timezone

from app.api.deps import get_authorization_url, get_login_attempt_service, get_session_service
from app.application.auth_sessions import AttemptPending, AttemptUnauthorized, LoginStart, SessionResult
from app.domain.auth import LoginIdentity, UserAccount
from app.main import app


class FakeAttempts:
    def start(self, challenge):
        return LoginStart("attempt-1", "raw-state", datetime(2026, 8, 17, tzinfo=timezone.utc))

    def exchange(self, attempt_id, verifier):
        if verifier == "pending": raise AttemptPending()
        if verifier == "bad": raise AttemptUnauthorized()
        return SessionResult("service-token", UserAccount("u1", LoginIdentity("kakao", "7")))


class FakeSessions:
    def authenticate(self, token):
        if token != "service-token": raise AttemptUnauthorized()
        return UserAccount("u1", LoginIdentity("kakao", "7"))

    def revoke(self, token):
        if token != "service-token": raise AttemptUnauthorized()


def test_auth_attempt_and_session_endpoints(client) -> None:
    app.dependency_overrides[get_login_attempt_service] = lambda: FakeAttempts()
    app.dependency_overrides[get_session_service] = lambda: FakeSessions()
    app.dependency_overrides[get_authorization_url] = lambda: (lambda state: f"https://login.test/?state={state}")

    start = client.post("/auth/login-attempts", json={"verifier_challenge": "challenge"})
    assert start.status_code == 201
    assert start.json()["authorization_url"].endswith("state=raw-state")

    assert client.post("/auth/login-attempts/attempt-1/exchange", json={"verifier": "pending"}).status_code == 202
    exchanged = client.post("/auth/login-attempts/attempt-1/exchange", json={"verifier": "ok"})
    assert exchanged.json()["session_token"] == "service-token"

    assert client.get("/auth/session", headers={"Authorization": "Bearer service-token"}).json()["id"] == "u1"
    assert client.delete("/auth/session", headers={"Authorization": "Bearer service-token"}).status_code == 204
    assert client.get("/auth/session").status_code == 401
