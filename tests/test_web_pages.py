from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.web_auth import COOKIE_NAME
from app.application.auth_sessions import SessionService
from app.core.database import get_db
from app.domain.auth import LoginIdentity, UserAccount
from app.main import create_app
from app.repositories.auth import SqlAlchemyAuthSessionRepository, SqlAlchemyUserAccountRepository


@pytest.fixture
def pages(tmp_path, db_session, monkeypatch):
    monkeypatch.setenv('ADMIN_ACCOUNT_ID', 'operator')
    monkeypatch.setenv('WEB_ORIGIN', 'http://testserver')
    (tmp_path / 'index.html').write_text('<html><div id="root">React shell</div></html>', encoding='utf-8')
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'assets' / 'main.js').write_text('window.webLoaded=true;', encoding='utf-8')
    app = create_app(web_dist=tmp_path)
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)
    yield client
    client.close()


def login(client, db, account_id='operator', expired=False):
    account = SqlAlchemyUserAccountRepository(db).save_or_get_existing(
        UserAccount(account_id, LoginIdentity('kakao', account_id))
    )
    now = datetime.now(timezone.utc) - timedelta(days=31 if expired else 0)
    token = SessionService(SqlAlchemyAuthSessionRepository(db), now=lambda: now).issue(account).token
    client.cookies.set(COOKIE_NAME, token)


def test_login_assets_and_api_routes_are_distinct(pages):
    response = pages.get('/login')
    assert response.status_code == 200
    assert 'React shell' in response.text
    assert response.headers['cache-control'] == 'no-store'
    assert pages.get('/assets/main.js').text == 'window.webLoaded=true;'
    assert pages.get('/assets/missing.js').status_code == 404
    assert pages.get('/auth/web/session').status_code == 401
    assert pages.get('/unknown-api').status_code == 404
    assert pages.get('/auth/kakao/callback').status_code == 400
    assert pages.get('/health').status_code == 200


def test_anonymous_and_expired_admin_navigation_returns_to_login(pages, db_session):
    for expired in (False, True):
        if expired:
            login(pages, db_session, expired=True)
        response = pages.get('/admin', follow_redirects=False)
        assert response.status_code == 303
        assert response.headers['location'] == '/login'


def test_operator_page_and_api_are_connected(pages, db_session):
    login(pages, db_session)
    assert pages.get('/admin').status_code == 200
    result = pages.post('/admin/invitations', headers={'Origin': 'http://testserver'})
    assert result.status_code == 201
    assert set(result.json()) == {'code', 'expires_at'}


def test_member_gets_forbidden_page_with_no_account_data_embedded(pages, db_session):
    login(pages, db_session, account_id='member')
    response = pages.get('/admin')
    assert response.status_code == 403
    assert 'React shell' in response.text
    assert 'member' not in response.text
    assert response.headers['cache-control'] == 'no-store'
    assert pages.get('/auth/web/session').json()['id'] == 'member'
    assert pages.post('/admin/invitations', headers={'Origin': 'http://testserver'}).status_code == 403


def test_missing_web_build_is_explicit_and_does_not_hide_api(tmp_path):
    client = TestClient(create_app(web_dist=tmp_path / 'not-built'))
    assert client.get('/login').status_code == 503
    assert client.get('/health').status_code == 200
    client.close()
