"""Kakao OAuth and talk memo helpers."""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlencode

import httpx

from app.settings import _ENV_FILE

KAKAO_AUTH_URL = "https://kauth.kakao.com/oauth/authorize"
KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8000/auth/kakao/callback"
DEFAULT_SCOPE = "talk_message"


class KakaoAuthError(RuntimeError):
    """Raised when Kakao OAuth or API calls fail."""


def kakao_settings() -> dict[str, str | None]:
    from app.settings import load_environment

    load_environment()
    return {
        "rest_api_key": os.getenv("KAKAO_REST_API_KEY"),
        "redirect_uri": os.getenv("KAKAO_REDIRECT_URI", DEFAULT_REDIRECT_URI),
        "client_secret": os.getenv("KAKAO_CLIENT_SECRET"),
        "access_token": os.getenv("KAKAO_ACCESS_TOKEN"),
        "refresh_token": os.getenv("KAKAO_REFRESH_TOKEN"),
    }


def build_authorize_url(*, rest_api_key: str | None = None, redirect_uri: str | None = None) -> str:
    settings = kakao_settings()
    client_id = rest_api_key or settings["rest_api_key"]
    if not client_id:
        raise KakaoAuthError("KAKAO_REST_API_KEY is required")

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri or settings["redirect_uri"] or DEFAULT_REDIRECT_URI,
        "response_type": "code",
        "scope": DEFAULT_SCOPE,
    }
    return f"{KAKAO_AUTH_URL}?{urlencode(params)}"


def exchange_code_for_token(
    code: str,
    *,
    rest_api_key: str | None = None,
    redirect_uri: str | None = None,
    client_secret: str | None = None,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    settings = kakao_settings()
    client_id = rest_api_key or settings["rest_api_key"]
    if not client_id:
        raise KakaoAuthError("KAKAO_REST_API_KEY is required")

    body: dict[str, str] = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "redirect_uri": redirect_uri or settings["redirect_uri"] or DEFAULT_REDIRECT_URI,
        "code": code,
    }
    secret = client_secret if client_secret is not None else settings["client_secret"]
    if secret:
        body["client_secret"] = secret

    http = client or httpx.Client(timeout=30.0)
    owns_client = client is None
    try:
        response = http.post(
            KAKAO_TOKEN_URL,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise KakaoAuthError(
                f"Kakao token request failed: {exc.response.status_code} {exc.response.text}"
            ) from exc
        return response.json()
    finally:
        if owns_client:
            http.close()


def refresh_access_token(
    *,
    refresh_token: str | None = None,
    rest_api_key: str | None = None,
    client_secret: str | None = None,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    settings = kakao_settings()
    token = refresh_token or settings["refresh_token"]
    if not token:
        raise KakaoAuthError("KAKAO_REFRESH_TOKEN is required")

    client_id = rest_api_key or settings["rest_api_key"]
    if not client_id:
        raise KakaoAuthError("KAKAO_REST_API_KEY is required")

    body: dict[str, str] = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": token,
    }
    secret = client_secret if client_secret is not None else settings["client_secret"]
    if secret:
        body["client_secret"] = secret

    http = client or httpx.Client(timeout=30.0)
    owns_client = client is None
    try:
        response = http.post(
            KAKAO_TOKEN_URL,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise KakaoAuthError(
                f"Kakao token refresh failed: {exc.response.status_code} {exc.response.text}"
            ) from exc
        return response.json()
    finally:
        if owns_client:
            http.close()


def persist_tokens_to_env(token_payload: dict[str, Any]) -> None:
    """Merge Kakao tokens into the project .env file."""

    access_token = token_payload.get("access_token")
    refresh_token = token_payload.get("refresh_token")
    if not access_token:
        raise KakaoAuthError("Kakao response did not include access_token")

    lines: list[str] = []
    if _ENV_FILE.exists():
        lines = _ENV_FILE.read_text(encoding="utf-8").splitlines()

    values = {
        "KAKAO_ACCESS_TOKEN": str(access_token),
    }
    if refresh_token:
        values["KAKAO_REFRESH_TOKEN"] = str(refresh_token)

    for key, value in values.items():
        pattern = re.compile(rf"^{re.escape(key)}=.*$")
        replaced = False
        for index, line in enumerate(lines):
            if pattern.match(line):
                lines[index] = f"{key}={value}"
                replaced = True
                break
        if not replaced:
            lines.append(f"{key}={value}")

    _ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ.update(values)
