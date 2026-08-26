"""Send KakaoTalk memo alerts."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx

from app.domain.notifications import NotificationCredentials
from app.interfaces.notifications import AlertNotifyError

KAKAO_MEMO_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"


class KakaoNotifyError(AlertNotifyError):
    """Raised when Kakao memo send fails."""


class KakaoNotificationSender:
    def __init__(
        self,
        connection_repository,
        *,
        rest_api_key: str,
        client_secret: str | None = None,
        client: httpx.Client | None = None,
        now_provider=None,
    ) -> None:
        self.repository = connection_repository
        self.rest_api_key = rest_api_key
        self.client_secret = client_secret
        self.client = client or httpx.Client(timeout=30.0)
        self.now_provider = now_provider or (
            lambda: datetime.now(timezone.utc)
        )

    def send(self, *, connection, message: str) -> None:
        credentials = self.repository.get_credentials(connection.id)
        if credentials.requires_refresh(self.now_provider()):
            credentials = self._refresh(connection.id, credentials)

        response = self._send(credentials.access_token, message)
        if response.status_code == 401:
            credentials = self._refresh(connection.id, credentials)
            response = self._send(credentials.access_token, message)

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise KakaoNotifyError(
                f"Kakao memo request failed: {response.status_code}"
            ) from exc
        if response.json().get("result_code") != 0:
            raise KakaoNotifyError("Kakao memo request did not succeed")

    def _send(self, access_token: str, message: str) -> httpx.Response:
        template = json.dumps(
            {
                "object_type": "text",
                "text": message.strip(),
                "link": {},
            },
            ensure_ascii=False,
        )
        return self.client.post(
            KAKAO_MEMO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            data={"template_object": template},
        )

    def _refresh(
        self,
        connection_id: str,
        credentials: NotificationCredentials,
    ) -> NotificationCredentials:
        now = self.now_provider()
        refresh_expired = (
            credentials.refresh_token_expires_at is not None
            and credentials.refresh_token_expires_at <= now
        )
        if not credentials.refresh_token or refresh_expired:
            self.repository.disconnect(connection_id)
            raise KakaoNotifyError("Kakao refresh token is unavailable")

        data = {
            "grant_type": "refresh_token",
            "client_id": self.rest_api_key,
            "refresh_token": credentials.refresh_token,
        }
        if self.client_secret:
            data["client_secret"] = self.client_secret
        response = self.client.post(KAKAO_TOKEN_URL, data=data)

        if response.status_code in (400, 401):
            self.repository.disconnect(connection_id)
            raise KakaoNotifyError("Kakao refresh token was rejected")
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise KakaoNotifyError(
                f"Kakao token refresh failed: {response.status_code}"
            ) from exc

        payload = response.json()
        refreshed = NotificationCredentials(
            access_token=payload["access_token"],
            refresh_token=(
                payload.get("refresh_token")
                or credentials.refresh_token
            ),
            access_token_expires_at=now
            + timedelta(seconds=int(payload.get("expires_in", 21600))),
            refresh_token_expires_at=self._refresh_expiry(
                payload,
                credentials,
                now,
            ),
        )
        self.repository.update_credentials(connection_id, refreshed)
        return refreshed

    @staticmethod
    def _refresh_expiry(
        payload: dict,
        current: NotificationCredentials,
        now: datetime,
    ) -> datetime | None:
        expires_in = payload.get("refresh_token_expires_in")
        if expires_in is None:
            return current.refresh_token_expires_at
        return now + timedelta(seconds=int(expires_in))


__all__ = ["KakaoNotificationSender", "KakaoNotifyError"]
