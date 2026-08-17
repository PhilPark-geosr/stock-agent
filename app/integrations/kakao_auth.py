"""Kakao OAuth and talk memo helpers."""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlencode

import httpx

from app.domain.auth import ExternalLoginCredential, LoginIdentity
from app.core.settings import _ENV_FILE

KAKAO_AUTH_URL = "https://kauth.kakao.com/oauth/authorize"
KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8000/auth/kakao/callback"
KAKAO_USER_URL = "https://kapi.kakao.com/v2/user/me"


class KakaoAuthError(RuntimeError):
    """Raised when Kakao OAuth or API calls fail."""


def kakao_settings() -> dict[str, str | None]:
    from app.core.settings import load_environment

    load_environment()
    return {
        "rest_api_key": os.getenv("KAKAO_REST_API_KEY"),
        "redirect_uri": os.getenv("KAKAO_REDIRECT_URI", DEFAULT_REDIRECT_URI),
        "client_secret": os.getenv("KAKAO_CLIENT_SECRET"),
        "access_token": os.getenv("KAKAO_ACCESS_TOKEN"),
        "refresh_token": os.getenv("KAKAO_REFRESH_TOKEN"),
    }


def build_authorize_url(*, state: str, rest_api_key: str | None = None, redirect_uri: str | None = None) -> str:
    settings = kakao_settings()
    client_id = rest_api_key or settings["rest_api_key"]
    if not client_id:
        raise KakaoAuthError("KAKAO_REST_API_KEY is required")

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri or settings["redirect_uri"] or DEFAULT_REDIRECT_URI,
        "response_type": "code",
        "state": state,
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


class KakaoExternalLogin:
    def __init__(
        self,
        *,
        rest_api_key: str,
        redirect_uri: str,
        client_secret: str | None = None,
        client: httpx.Client | None = None,
        token_url: str = KAKAO_TOKEN_URL,
        user_url: str = KAKAO_USER_URL,
    ) -> None:
        self.rest_api_key = rest_api_key
        self.redirect_uri = redirect_uri
        self.client_secret = client_secret
        self.client = client
        self.token_url = token_url
        self.user_url = user_url

    def login(self, credential: ExternalLoginCredential) -> LoginIdentity:
        if credential.redirect_uri != self.redirect_uri:
            raise KakaoAuthError("redirect URI does not match configured Kakao callback")
        owns_client = self.client is None
        http = self.client or httpx.Client(timeout=30.0)
        try:
            data = {
                "grant_type": "authorization_code",
                "client_id": self.rest_api_key,
                "redirect_uri": credential.redirect_uri,
                "code": credential.authorization_code,
            }
            if self.client_secret:
                data["client_secret"] = self.client_secret
            token_response = http.post(self.token_url, data=data)
            self._raise_for_status(token_response, "token")
            access_token = token_response.json().get("access_token")
            if not access_token:
                raise KakaoAuthError("Kakao response did not include access_token")
            user_response = http.get(self.user_url, headers={"Authorization": f"Bearer {access_token}"})
            self._raise_for_status(user_response, "user")
            subject_id = user_response.json().get("id")
            if subject_id is None:
                raise KakaoAuthError("Kakao user response did not include id")
            return LoginIdentity("kakao", str(subject_id))
        finally:
            if owns_client:
                http.close()

    @staticmethod
    def _raise_for_status(response: httpx.Response, operation: str) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise KakaoAuthError(f"Kakao {operation} request failed: {response.status_code}") from exc


def persist_tokens_to_env(token_payload: dict[str, Any]) -> None:
    """Persist notification-connection tokens; service login never calls this function."""
    access_token = token_payload.get("access_token")
    refresh_token = token_payload.get("refresh_token")
    if not access_token:
        raise KakaoAuthError("Kakao response did not include access_token")
    lines = _ENV_FILE.read_text(encoding="utf-8").splitlines() if _ENV_FILE.exists() else []
    values = {"KAKAO_ACCESS_TOKEN": str(access_token)}
    if refresh_token:
        values["KAKAO_REFRESH_TOKEN"] = str(refresh_token)
    for key, value in values.items():
        pattern = re.compile(rf"^{re.escape(key)}=.*$")
        for index, line in enumerate(lines):
            if pattern.match(line):
                lines[index] = f"{key}={value}"
                break
        else:
            lines.append(f"{key}={value}")
    _ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ.update(values)
