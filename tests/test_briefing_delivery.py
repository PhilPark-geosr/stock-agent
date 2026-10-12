from types import SimpleNamespace

import pytest

from app.services.briefing_delivery import (
    BriefingDeliveryService,
    NotificationConnectionRequired,
)


def test_delivery_is_blocked_before_creating_state_without_active_connection():
    calls = []

    class Repository:
        def ensure_delivery(self, briefing_id, channel):
            calls.append(("ensure", briefing_id, channel))
            raise AssertionError("delivery state must not be created")

    class Renderer:
        def render(self, briefing, items, failures):
            raise AssertionError("briefing must not be rendered")

    class Notifier:
        def send_alert(self, message):
            raise AssertionError("message must not be sent")

    service = BriefingDeliveryService(
        repository=Repository(),
        renderer=Renderer(),
        notifier=Notifier(),
        connection_is_active=lambda user_account_id, channel: False,
    )

    with pytest.raises(NotificationConnectionRequired):
        service.deliver(SimpleNamespace(id=7, user_account_id="user-1"))

    assert calls == []
