from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from fastapi import HTTPException

from app.api.deps import get_current_account
from app.api.notification_test import get_notification_test_service
from app.application.notification_test import (
    NotificationTestConnectionRequired, NotificationTestService, TEST_MESSAGE,
)
from app.domain.auth import UserAccount
from app.domain.notifications import NotificationCredentials
from app.integrations.kakao_notify import KakaoNotificationSender
from app.main import app


def test_service_sends_fixed_message_using_only_current_owners_connection():
    connection = SimpleNamespace(id='mine', owner_id='owner')
    repository = Mock()
    repository.get_active.side_effect = lambda *, owner_id, channel: connection if owner_id == 'owner' else None
    repository.get_credentials.return_value = NotificationCredentials('private-token', None, None)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={'result_code': 0})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        sender = KakaoNotificationSender(repository, rest_api_key='key', client=client)
        service = NotificationTestService(repository, sender)
        service.send('owner')
        with pytest.raises(NotificationTestConnectionRequired):
            service.send('other')

    assert len(requests) == 1
    assert requests[0].url.path == '/v2/api/talk/memo/default/send'
    assert requests[0].headers['Authorization'] == 'Bearer private-token'
    from urllib.parse import parse_qs
    import json
    template = json.loads(parse_qs(requests[0].content.decode())['template_object'][0])
    assert template['text'] == TEST_MESSAGE
    repository.get_credentials.assert_called_once_with('mine')


@pytest.fixture
def test_sender(client):
    service = Mock()
    app.dependency_overrides[get_notification_test_service] = lambda: service
    return service


def test_endpoint_sends_for_authenticated_account(client, current_account, test_sender):
    response = client.post('/notification-connections/kakao/test', json={'owner_id': 'someone-else', 'message': 'override'})
    assert response.status_code == 204
    assert response.content == b''
    test_sender.send.assert_called_once_with(current_account.id)


@pytest.mark.parametrize('error,status', [
    (NotificationTestConnectionRequired(), 409),
    (httpx.ReadTimeout('private upstream details'), 502),
    (ValueError('private upstream response'), 502),
])
def test_endpoint_hides_errors_without_retry(client, test_sender, error, status):
    test_sender.send.side_effect = error
    response = client.post('/notification-connections/kakao/test')
    assert response.status_code == status
    assert 'private' not in response.text
    test_sender.send.assert_called_once()


def test_endpoint_requires_beta_access(client, current_account, test_sender):
    app.dependency_overrides[get_current_account] = lambda: UserAccount(
        current_account.id, current_account.login_identity, has_beta_access=False,
    )
    assert client.post('/notification-connections/kakao/test').status_code == 403
    test_sender.send.assert_not_called()


def test_endpoint_requires_login(client, test_sender):
    def unauthenticated():
        raise HTTPException(status_code=401)
    app.dependency_overrides[get_current_account] = unauthenticated
    assert client.post('/notification-connections/kakao/test').status_code == 401
    test_sender.send.assert_not_called()


def test_cookie_endpoint_checks_origin(client, current_account, test_sender, monkeypatch):
    from fastapi import Request

    def cookie_account(request: Request):
        request.state.auth_via_cookie = True
        return current_account

    monkeypatch.setenv('WEB_ORIGIN', 'https://expected.test')
    app.dependency_overrides[get_current_account] = cookie_account
    assert client.post('/notification-connections/kakao/test', headers={'Origin': 'https://wrong.test'}).status_code == 403
    test_sender.send.assert_not_called()
    assert client.post('/notification-connections/kakao/test', headers={'Origin': 'https://expected.test'}).status_code == 204
