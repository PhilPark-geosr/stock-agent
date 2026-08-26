"""Notification interfaces."""

from __future__ import annotations

from typing import Protocol


class AlertNotifyError(RuntimeError):
    """Raised when alert notification delivery fails."""


class NotificationSender(Protocol):
    def send(self, *, connection, message: str) -> None:
        ...
