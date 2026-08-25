import httpx
from urllib.parse import parse_qs, urlparse

from app.api.deps import get_login_attempt_service, get_login_service
from app.domain.auth import ExternalLoginCredential, LoginIdentity, UserAccount
from app.integrations.kakao_auth import KakaoExternalLogin, build_authorize_url
from app.main import app


def test_service_authorize_url_has_state_and_no_talk_message_scope(monkeypatch) -> None:
    url = build_authorize_url(state="state-123", rest_api_key="rest-key", redirect_uri="https://service/callback")
    query = parse_qs(urlparse(url).query)
    assert query["state"] == ["state-123"]
    assert query["redirect_uri"] == ["https://service/callback"]
    assert "scope" not in query
    assert "talk_message" not in url


def test_kakao_external_login_exchanges_code_and_uses_user_id_only() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "temporary", "refresh_token": "discard-me"})
        assert request.headers["Authorization"] == "Bearer temporary"
        return httpx.Response(200, json={"id": 987, "kakao_account": {"email": "ignored@test"}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = KakaoExternalLogin(
            rest_api_key="rest-key", redirect_uri="https://service/callback", client=client,
            token_url="https://kakao.test/oauth/token", user_url="https://kakao.test/v2/user/me",
        )
        identity = adapter.login(ExternalLoginCredential("auth-code", "https://service/callback"))

    assert identity == LoginIdentity("kakao", "987")
    assert len(requests) == 2


class FakeLoginService:
    def login(self, credential):
        assert credential.authorization_code == "code"
        return UserAccount("u1", LoginIdentity("kakao", "7"))


class FakeAttempts:
    def complete(self, state, account):
        assert state == "valid-state"
        assert account.id == "u1"


def test_kakao_callback_completes_attempt_without_exposing_tokens(client) -> None:
    app.dependency_overrides[get_login_service] = lambda: FakeLoginService()
    app.dependency_overrides[get_login_attempt_service] = lambda: FakeAttempts()

    response = client.get("/auth/kakao/callback?code=code&state=valid-state")

    assert response.status_code == 200
    assert "로그인" in response.text
    assert "access_token" not in response.text
    assert "refresh_token" not in response.text
