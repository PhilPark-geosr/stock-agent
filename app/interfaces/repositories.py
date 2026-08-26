"""Repository interfaces used by application services."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from app.domain.alert_conditions import CustomAlertCondition, RuleValidationResult
from app.domain.models import (
    AnalysisResult,
    CustomAlertConditionRecord,
    NotificationDeliveryRecord,
    WatchlistSubscription,
)
from app.domain.notifications import NotificationConnection, NotificationCredentials
from app.domain.symbols import StockSymbol


class WatchlistRepository(Protocol):
    def list(self, owner_id: str) -> list[WatchlistSubscription]:
        ...

    def get(self, owner_id: str, symbol: StockSymbol) -> WatchlistSubscription | None:
        ...

    def add(self, owner_id: str, symbol: StockSymbol) -> WatchlistSubscription:
        ...

    def delete(self, owner_id: str, symbol: StockSymbol) -> bool:
        ...

    def list_distinct_active_symbols(self) -> list[StockSymbol]:
        ...

    def list_active_for_symbol(self, symbol: StockSymbol | str) -> list[WatchlistSubscription]:
        ...


class AlertConditionRepository(Protocol):
    def list_enabled_for_symbol(self, symbol: str) -> list[CustomAlertCondition]:
        ...

    def list(self, owner_id: str) -> list[CustomAlertConditionRecord]:
        ...

    def save_validated(
        self,
        *,
        owner_id: str,
        symbol: str,
        user_rule: str,
        validation: RuleValidationResult,
    ) -> CustomAlertConditionRecord:
        ...

    def delete(self, owner_id: str, condition_id: int) -> bool:
        ...


class AnalysisRepository(Protocol):
    def get_latest(self, symbol: str) -> AnalysisResult | None:
        ...

    def save(
        self,
        *,
        symbol: str,
        overall_judgment: str,
        summary: str,
        data_timestamp: datetime | None = None,
        key_reasons: list[str] | None = None,
        risk_factors: list[str] | None = None,
        support_levels: dict[str, Any] | None = None,
        should_alert: bool = False,
        triggered_alerts: list[str] | None = None,
        alert_reason: str | None = None,
        raw_result: dict[str, Any] | None = None,
    ) -> AnalysisResult:
        ...

    def count_by_symbol(self, symbol: str) -> int:
        ...


class NotificationConnectionRepository(Protocol):
    def get_active(
        self,
        *,
        owner_id: str,
        channel: str,
    ) -> NotificationConnection | None:
        ...

    def create(
        self,
        *,
        owner_id: str,
        channel: str,
        credentials: NotificationCredentials,
    ) -> NotificationConnection:
        ...

    def get_credentials(
        self,
        connection_id: str,
    ) -> NotificationCredentials:
        ...

    def update_credentials(
        self,
        connection_id: str,
        credentials: NotificationCredentials,
    ) -> None:
        ...

    def disconnect(self, connection_id: str) -> bool:
        ...


class NotificationDeliveryRepository(Protocol):
    def reserve_default_alert(
        self,
        *,
        recipient_id: str,
        analysis_id: int,
        connection_id: str,
        message: str,
    ):
        ...

    def mark_sent(self, delivery_id: int) -> NotificationDeliveryRecord:
        ...

    def mark_failed(
        self,
        delivery_id: int,
        *,
        reason: str,
    ) -> NotificationDeliveryRecord:
        ...
