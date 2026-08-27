import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, unquote

import httpx
from cryptography.fernet import Fernet, InvalidToken

from app.domain.notifications import NotificationCredentials


class NotificationConnectionError(RuntimeError):
    pass


class KakaoNotificationConnectionService:
    def __init__(
        self,
        repository,
        *,
        rest_api_key: str,
        redirect_uri: str,
        state_cipher: Fernet,
        client_secret: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.repository = repository
        self.rest_api_key = rest_api_key
        self.redirect_uri = redirect_uri
        self.state_cipher = state_cipher
        self.client_secret = client_secret
        self.client = client or httpx.Client(timeout=30)

    def authorize(self, owner_id: str) -> str:
        state = self.state_cipher.encrypt(
            json.dumps({"owner_id": owner_id}).encode()
        ).decode()
        query = urlencode(
            {
                "client_id": self.rest_api_key,
                "redirect_uri": self.redirect_uri,
                "response_type": "code",
                "scope": "talk_message",
                "state": state,
            }
        )
        return f"https://kauth.kakao.com/oauth/authorize?{query}"

    def owner_id_from_state(self, state: str) -> str:
        try:
            payload = self.state_cipher.decrypt(unquote(state).encode(), ttl=300)
            return json.loads(payload)["owner_id"]
        except (InvalidToken, KeyError, ValueError, json.JSONDecodeError) as exc:
            raise NotificationConnectionError(
                "invalid or expired notification connection state"
            ) from exc

    def complete(
        self,
        *,
        code: str,
        state: str,
        expected_subject_id: str,
        granted_scopes: list[str] | None = None,
    ):
        owner_id = self.owner_id_from_state(state)
        if granted_scopes is not None and "talk_message" not in granted_scopes:
            raise NotificationConnectionError("talk_message consent is required")

        token_payload = self._exchange_token(code)
        access_token = token_payload.get("access_token")
        if not access_token:
            raise NotificationConnectionError(
                "Kakao did not return an access token"
            )

        subject_id = self._get_subject_id(access_token)
        if subject_id != str(expected_subject_id):
            raise NotificationConnectionError(
                "Kakao identity does not match the logged-in account"
            )

        scopes = (
            granted_scopes
            if granted_scopes is not None
            else self._get_granted_scopes(access_token)
        )
        if "talk_message" not in scopes:
            raise NotificationConnectionError("talk_message consent is required")

        now = datetime.now(timezone.utc)
        credentials = NotificationCredentials(
            access_token=access_token,
            refresh_token=token_payload.get("refresh_token"),
            access_token_expires_at=now
            + timedelta(seconds=int(token_payload.get("expires_in", 21600))),
            refresh_token_expires_at=self._refresh_expiry(token_payload, now),
        )
        return self.repository.create(
            owner_id=owner_id,
            channel="kakao",
            credentials=credentials,
        )

    def _exchange_token(self, code: str) -> dict:
        data = {
            "grant_type": "authorization_code",
            "client_id": self.rest_api_key,
            "redirect_uri": self.redirect_uri,
            "code": code,
        }
        if self.client_secret:
            data["client_secret"] = self.client_secret
        try:
            response = self.client.post(
                "https://kauth.kakao.com/oauth/token",
                data=data,
            )
        except httpx.RequestError as exc:
            raise NotificationConnectionError(
                "Kakao token request failed"
            ) from exc
        self._raise_for_status(response, "token")
        return response.json()

    def _get_subject_id(self, access_token: str) -> str:
        try:
            response = self.client.get(
                "https://kapi.kakao.com/v2/user/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except httpx.RequestError as exc:
            raise NotificationConnectionError(
                "Kakao user request failed"
            ) from exc
        self._raise_for_status(response, "user")
        return str(response.json().get("id"))

    def _get_granted_scopes(self, access_token: str) -> list[str]:
        try:
            response = self.client.get(
                "https://kapi.kakao.com/v2/user/scopes",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except httpx.RequestError as exc:
            raise NotificationConnectionError(
                "Kakao scope request failed"
            ) from exc
        self._raise_for_status(response, "scope")
        return [
            scope.get("id")
            for scope in response.json().get("scopes", [])
            if scope.get("agreed")
        ]

    @staticmethod
    def _refresh_expiry(payload: dict, now: datetime) -> datetime | None:
        expires_in = payload.get("refresh_token_expires_in")
        if expires_in is None:
            return None
        return now + timedelta(seconds=int(expires_in))

    @staticmethod
    def _raise_for_status(response: httpx.Response, operation: str) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise NotificationConnectionError(
                f"Kakao {operation} request failed: {response.status_code}"
            ) from exc
