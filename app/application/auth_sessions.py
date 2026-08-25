from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.domain.auth import AuthSession, LoginAttempt, UserAccount
from app.interfaces.auth import AuthSessionRepository, LoginAttemptRepository


class AttemptError(RuntimeError): pass
class AttemptPending(AttemptError): pass
class AttemptExpired(AttemptError): pass
class AttemptUnauthorized(AttemptError): pass
class AttemptNotFound(AttemptError): pass


@dataclass(frozen=True)
class LoginStart:
    attempt_id: str
    state: str
    expires_at: datetime


@dataclass(frozen=True)
class SessionResult:
    token: str
    account: UserAccount


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class SessionService:
    def __init__(self, sessions: AuthSessionRepository, *, now=_utc_now) -> None:
        self.sessions = sessions
        self.now = now

    @staticmethod
    def hash_token(token: str) -> str:
        return _hash(token)

    def issue(self, account: UserAccount) -> SessionResult:
        token = secrets.token_urlsafe(32)
        session = AuthSession(
            id=str(uuid4()), account=account, token_hash=self.hash_token(token),
            expires_at=self.now() + timedelta(days=30),
        )
        self.sessions.save(session)
        return SessionResult(token, account)

    def authenticate(self, token: str) -> UserAccount:
        session = self.sessions.find_by_token_hash(self.hash_token(token))
        if session is None or session.revoked_at is not None or _as_utc(self.now()) >= _as_utc(session.expires_at):
            raise AttemptUnauthorized("invalid session")
        return session.account

    def revoke(self, token: str) -> None:
        session = self.sessions.find_by_token_hash(self.hash_token(token))
        if session is None or session.revoked_at is not None:
            raise AttemptUnauthorized("invalid session")
        session.revoked_at = self.now()
        self.sessions.save(session)


class LoginAttemptService:
    def __init__(self, attempts: LoginAttemptRepository, sessions: SessionService, *, now=_utc_now) -> None:
        self.attempts, self.sessions, self.now = attempts, sessions, now

    @staticmethod
    def challenge_for(verifier: str) -> str:
        digest = hashlib.sha256(verifier.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    def start(self, verifier_challenge: str) -> LoginStart:
        state = secrets.token_urlsafe(32)
        attempt = LoginAttempt(
            id=str(uuid4()), state_hash=_hash(state), verifier_challenge=verifier_challenge,
            expires_at=self.now() + timedelta(minutes=5),
        )
        self.attempts.save(attempt)
        return LoginStart(attempt.id, state, attempt.expires_at)

    def complete(self, state: str, account: UserAccount) -> None:
        attempt = self.attempts.find_by_state_hash(_hash(state))
        if attempt is None:
            raise AttemptUnauthorized("invalid state")
        if _as_utc(self.now()) >= _as_utc(attempt.expires_at):
            raise AttemptExpired("login attempt expired")
        attempt.account = account
        self.attempts.save(attempt)

    def exchange(self, attempt_id: str, verifier: str) -> SessionResult:
        attempt = self.attempts.get(attempt_id)
        if attempt is None:
            raise AttemptNotFound("login attempt not found")
        if not hmac.compare_digest(self.challenge_for(verifier), attempt.verifier_challenge):
            raise AttemptUnauthorized("invalid verifier")
        if _as_utc(self.now()) >= _as_utc(attempt.expires_at):
            raise AttemptExpired("login attempt expired")
        if attempt.consumed_at is not None:
            raise AttemptUnauthorized("login attempt already consumed")
        if attempt.account is None:
            raise AttemptPending("login pending")
        attempt.consumed_at = self.now()
        self.attempts.save(attempt)
        return self.sessions.issue(attempt.account)
