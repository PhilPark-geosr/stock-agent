from datetime import datetime, timedelta, timezone

import pytest

from app.application.auth_sessions import (
    AttemptExpired,
    AttemptPending,
    AttemptUnauthorized,
    LoginAttemptService,
    SessionService,
)
from app.domain.auth import LoginIdentity, UserAccount

NOW = datetime(2026, 8, 17, tzinfo=timezone.utc)


class MemoryAttempts:
    def __init__(self) -> None:
        self.items = {}

    def save(self, attempt): self.items[attempt.id] = attempt
    def get(self, attempt_id): return self.items.get(attempt_id)
    def find_by_state_hash(self, state_hash):
        return next((item for item in self.items.values() if item.state_hash == state_hash), None)


class MemorySessions:
    def __init__(self) -> None:
        self.items = {}

    def save(self, session): self.items[session.token_hash] = session
    def find_by_token_hash(self, token_hash): return self.items.get(token_hash)


def test_login_attempt_expires_after_five_minutes() -> None:
    attempts = MemoryAttempts()
    service = LoginAttemptService(attempts, SessionService(MemorySessions(), now=lambda: NOW), now=lambda: NOW)
    start = service.start("challenge")
    assert start.expires_at == NOW + timedelta(minutes=5)


def test_exchange_rejects_pending_wrong_verifier_and_expired_attempts() -> None:
    attempts = MemoryAttempts()
    clock = [NOW]
    service = LoginAttemptService(attempts, SessionService(MemorySessions(), now=lambda: clock[0]), now=lambda: clock[0])
    verifier = "secret-verifier"
    start = service.start(service.challenge_for(verifier))
    with pytest.raises(AttemptPending): service.exchange(start.attempt_id, verifier)
    with pytest.raises(AttemptUnauthorized): service.exchange(start.attempt_id, "wrong")
    clock[0] = NOW + timedelta(minutes=6)
    with pytest.raises(AttemptExpired): service.exchange(start.attempt_id, verifier)


def test_completed_attempt_is_exchanged_only_once_and_session_is_revocable() -> None:
    attempts, sessions = MemoryAttempts(), MemorySessions()
    session_service = SessionService(sessions, now=lambda: NOW)
    service = LoginAttemptService(attempts, session_service, now=lambda: NOW)
    verifier = "secret-verifier"
    start = service.start(service.challenge_for(verifier))
    account = UserAccount.register(LoginIdentity("kakao", "7"))
    service.complete(start.state, account)

    result = service.exchange(start.attempt_id, verifier)

    assert len(result.token) >= 43
    assert result.account == account
    assert result.token not in sessions.items
    assert session_service.authenticate(result.token).id == account.id
    with pytest.raises(AttemptUnauthorized): service.exchange(start.attempt_id, verifier)
    session_service.revoke(result.token)
    with pytest.raises(AttemptUnauthorized): session_service.authenticate(result.token)


def test_session_has_thirty_day_absolute_expiry() -> None:
    sessions = MemorySessions()
    service = SessionService(sessions, now=lambda: NOW)
    account = UserAccount.register(LoginIdentity("kakao", "7"))
    result = service.issue(account)
    stored = sessions.find_by_token_hash(service.hash_token(result.token))
    assert stored.expires_at == NOW + timedelta(days=30)

