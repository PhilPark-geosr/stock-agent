from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api import admin, web_auth
from app.api.deps import get_login_attempt_service, get_session_service
from app.application.auth_sessions import LoginAttemptService, SessionService
from app.core.database import get_db
from app.domain.auth import LoginIdentity, UserAccount
from app.domain.models import InvitationRecord
from app.repositories.auth import SqlAlchemyAuthSessionRepository, SqlAlchemyLoginAttemptRepository, SqlAlchemyUserAccountRepository

ORIGIN = 'https://service.test'
NOW = datetime.now(timezone.utc)


@pytest.fixture
def web_client(db_session, monkeypatch):
    monkeypatch.setenv('WEB_ORIGIN', ORIGIN)
    monkeypatch.setenv('WEB_COOKIE_SECURE', 'true')
    monkeypatch.delenv('ADMIN_ACCOUNT_ID', raising=False)
    app = FastAPI()
    app.include_router(web_auth.router)
    app.include_router(admin.router)
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app, base_url=ORIGIN) as client:
        yield client


def account(db, subject='operator'):
    return SqlAlchemyUserAccountRepository(db).save_or_get_existing(UserAccount.register(LoginIdentity('kakao', subject)))


def login(client, db, who, *, now=NOW):
    service = SessionService(SqlAlchemyAuthSessionRepository(db), now=lambda: now)
    token = service.issue(who).token
    client.cookies.set(web_auth.COOKIE_NAME, token)
    return token


def test_real_operator_issues_one_invitation_without_beta_permission(web_client, db_session, monkeypatch):
    who = account(db_session)
    monkeypatch.setenv('ADMIN_ACCOUNT_ID', who.id)
    login(web_client, db_session, who)
    assert web_client.get('/auth/web/session').json() == {
        'id': who.id, 'login_provider': 'kakao', 'is_operator': True, 'has_beta_access': False,
    }
    response = web_client.post('/admin/invitations', headers={'Origin': ORIGIN})
    assert response.status_code == 201
    row = db_session.scalar(select(InvitationRecord))
    assert row is not None and row.used_at is None
    assert (row.expires_at - row.issued_at) == timedelta(days=7)
    assert response.json()['code'] not in repr(row.__dict__)
    assert response.headers['cache-control'] == 'no-store'


@pytest.mark.parametrize('mode,expected', [('missing',401),('invalid',401),('expired',401),('revoked',401),('ordinary',403),('unset',403)])
def test_unauthorized_cannot_create_invitation(web_client, db_session, monkeypatch, mode, expected):
    who = account(db_session)
    if mode != 'unset':
        monkeypatch.setenv('ADMIN_ACCOUNT_ID', 'other' if mode == 'ordinary' else who.id)
    if mode == 'invalid':
        web_client.cookies.set(web_auth.COOKIE_NAME, 'invalid')
    elif mode != 'missing':
        token = login(web_client, db_session, who, now=NOW - timedelta(days=31) if mode == 'expired' else NOW)
        if mode == 'revoked':
            SessionService(SqlAlchemyAuthSessionRepository(db_session)).revoke(token)
    response = web_client.post('/admin/invitations', headers={'Origin': ORIGIN})
    assert response.status_code == expected
    assert db_session.scalar(select(InvitationRecord)) is None


@pytest.mark.parametrize('origin', [None, 'https://evil.test', 'https://service.test.evil.test'])
def test_changes_reject_untrusted_origin(web_client, db_session, monkeypatch, origin):
    who = account(db_session)
    monkeypatch.setenv('ADMIN_ACCOUNT_ID', who.id)
    login(web_client, db_session, who)
    headers = {'Origin': origin} if origin else {}
    assert web_client.post('/admin/invitations', headers=headers).status_code == 403
    assert web_client.delete('/auth/web/session', headers=headers).status_code == 403
    assert web_client.post('/auth/web/login-attempts/unknown/exchange', json={'verifier':'v'}, headers=headers).status_code == 403
    assert web_client.get('/auth/web/session').status_code == 200
    assert db_session.scalar(select(InvitationRecord)) is None


def test_exchange_pending_success_reuse_logout_and_cookie(web_client, db_session):
    service = LoginAttemptService(SqlAlchemyLoginAttemptRepository(db_session), SessionService(SqlAlchemyAuthSessionRepository(db_session)))
    attempt = service.start(service.challenge_for('verifier'))
    url = f'/auth/web/login-attempts/{attempt.attempt_id}/exchange'
    headers = {'Origin': ORIGIN}
    assert web_client.post(url, json={'verifier':'verifier'}, headers=headers).status_code == 202
    assert web_client.post(url, json={'verifier':'wrong'}, headers=headers).status_code == 401
    who = account(db_session)
    service.complete(attempt.state, who)
    result = web_client.post(url, json={'verifier':'verifier'}, headers=headers)
    assert result.status_code == 200
    assert result.json() == {
        'id': who.id, 'login_provider': 'kakao', 'is_operator': False, 'has_beta_access': False,
    }
    cookie = result.headers['set-cookie']
    assert all(part in cookie for part in ['HttpOnly', 'Secure', 'SameSite=lax', 'Path=/', 'Max-Age=2592000'])
    token = web_client.cookies.get(web_auth.COOKIE_NAME)
    assert token not in result.text
    assert web_client.post(url, json={'verifier':'verifier'}, headers=headers).status_code == 401
    assert web_client.get('/auth/web/session').status_code == 200
    assert web_client.delete('/auth/web/session', headers=headers).status_code == 204
    assert web_client.get('/auth/web/session').status_code == 401
    web_client.cookies.set(web_auth.COOKIE_NAME, token)
    assert web_client.get('/auth/web/session').status_code == 401


def test_exchange_expired_or_missing(web_client, db_session):
    service = LoginAttemptService(SqlAlchemyLoginAttemptRepository(db_session), SessionService(SqlAlchemyAuthSessionRepository(db_session)), now=lambda: NOW - timedelta(minutes=6))
    attempt = service.start(service.challenge_for('v'))
    headers = {'Origin': ORIGIN}
    assert web_client.post(f'/auth/web/login-attempts/{attempt.attempt_id}/exchange', json={'verifier':'v'}, headers=headers).status_code == 410
    assert web_client.post('/auth/web/login-attempts/missing/exchange', json={'verifier':'v'}, headers=headers).status_code == 404


def test_save_failure_is_sanitized(web_client, db_session, monkeypatch):
    from app.repositories.invitations import SqlAlchemyInvitationRepository
    who = account(db_session)
    monkeypatch.setenv('ADMIN_ACCOUNT_ID', who.id)
    login(web_client, db_session, who)
    def fail(self, invitation):
        raise RuntimeError('private database details')
    monkeypatch.setattr(SqlAlchemyInvitationRepository, 'save', fail)
    response = web_client.post('/admin/invitations', headers={'Origin': ORIGIN})
    assert response.status_code == 500
    assert 'private database' not in response.text
    assert db_session.scalar(select(InvitationRecord)) is None


def test_default_secure_cookie_and_explicit_http_development_override(monkeypatch):
    monkeypatch.delenv('WEB_COOKIE_SECURE', raising=False)
    assert web_auth.cookie_secure() is True
    monkeypatch.setenv('WEB_COOKIE_SECURE', 'false')
    assert web_auth.cookie_secure() is False
    monkeypatch.setenv('WEB_COOKIE_SECURE', 'unexpected')
    assert web_auth.cookie_secure() is True


def test_current_setting_is_checked_for_existing_session(web_client, db_session, monkeypatch):
    who = account(db_session)
    login(web_client, db_session, who)
    assert web_client.get('/auth/web/session').json()['is_operator'] is False
    monkeypatch.setenv('ADMIN_ACCOUNT_ID', who.id)
    assert web_client.get('/auth/web/session').json()['is_operator'] is True
    monkeypatch.setenv('ADMIN_ACCOUNT_ID', 'another')
    assert web_client.post('/admin/invitations', headers={'Origin': ORIGIN}).status_code == 403
