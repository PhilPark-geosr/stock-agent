"""Notification interfaces."""

from __future__ import annotations

from typing import Protocol


class AlertNotifyError(RuntimeError):
    """Raised when alert notification delivery fails."""


class AlertNotifier(Protocol):
    def send_alert(self, alert_reason: str) -> None:
        ...
