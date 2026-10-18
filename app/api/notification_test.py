"""Authenticated boundary for testing the current account's notification connection."""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.deps import get_notification_connection_repository, require_beta_mutation
from app.application.notification_test import NotificationTestConnectionRequired, NotificationTestService
from app.domain.auth import UserAccount
from app.integrations.kakao_auth import kakao_settings
from app.integrations.kakao_notify import KakaoNotificationSender
from app.interfaces.notifications import AlertNotifyError
from app.repositories.notifications import NotificationCredentialError


router = APIRouter()


def get_notification_test_service(repository=Depends(get_notification_connection_repository)):
    settings = kakao_settings()
    if not settings['rest_api_key']:
        raise HTTPException(status_code=503, detail='Kakao notification is not configured')
    with httpx.Client(timeout=30) as client:
        yield NotificationTestService(repository, KakaoNotificationSender(
            repository, rest_api_key=settings['rest_api_key'],
            client_secret=settings['client_secret'], client=client,
        ))


@router.post('/notification-connections/kakao/test', status_code=204)
def send_test_notification(
    account: UserAccount = Depends(require_beta_mutation),
    service: NotificationTestService = Depends(get_notification_test_service),
):
    try:
        service.send(account.id)
    except NotificationTestConnectionRequired:
        raise HTTPException(status_code=409, detail='Kakao notification connection required') from None
    except (AlertNotifyError, httpx.HTTPError, NotificationCredentialError, ValueError, KeyError):
        raise HTTPException(status_code=502, detail='Test notification could not be confirmed') from None
    return Response(status_code=204)
