"""Send KakaoTalk memo alerts."""

from __future__ import annotations

import json
import logging
from typing import Protocol

import httpx

from app.kakao_auth import kakao_settings, persist_tokens_to_env, refresh_access_token

logger = logging.getLogger(__name__)

KAKAO_MEMO_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"


class KakaoNotifyError(RuntimeError):
    """Raised when Kakao memo send fails."""


class AlertNotifier(Protocol):
    def send_alert(self, alert_reason: str) -> None:
        ...


class KakaoAlertNotifier:
    def __init__(self, *, client: httpx.Client | None = None) -> None:
        self._client = client

    def send_alert(self, alert_reason: str) -> None:
        send_alert_reason(alert_reason, client=self._client)


class NoOpAlertNotifier:
    def send_alert(self, alert_reason: str) -> None:
        return


def send_alert_reason(
    alert_reason: str,
    *,
    client: httpx.Client | None = None,
    allow_token_refresh: bool = True,
) -> None:
    message = alert_reason.strip()
    if not message:
        return

    access_token = kakao_settings()["access_token"]
    if not access_token:
        raise KakaoNotifyError("KAKAO_ACCESS_TOKEN is required")

    template_object = json.dumps(
        {"object_type": "text", "text": message, "link": {}},
        ensure_ascii=False,
    )
    http = client or httpx.Client(timeout=30.0)
    owns_client = client is None
    try:
        response = http.post(
            KAKAO_MEMO_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
            },
            data={"template_object": template_object},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401 and allow_token_refresh:
                refresh_payload = refresh_access_token()
                persist_tokens_to_env(refresh_payload)
                return send_alert_reason(
                    alert_reason,
                    client=client,
                    allow_token_refresh=False,
                )
            raise KakaoNotifyError(
                f"Kakao memo send failed: {exc.response.status_code} {exc.response.text}"
            ) from exc
        payload = response.json()
        if payload.get("result_code") != 0:
            raise KakaoNotifyError(f"Kakao memo send failed: {payload}")
        logger.info("Kakao alert sent (%d chars)", len(message))
    finally:
        if owns_client:
            http.close()


def get_default_alert_notifier() -> AlertNotifier:
    if kakao_settings()["access_token"]:
        return KakaoAlertNotifier()
    return NoOpAlertNotifier()
