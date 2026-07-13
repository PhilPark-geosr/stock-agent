"""Repository interfaces used by application services."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from app.domain.alert_conditions import CustomAlertCondition, RuleValidationResult
from app.domain.models import AnalysisResult, CustomAlertConditionRecord, WatchlistItem


class WatchlistRepository(Protocol):
    def list(self) -> list[WatchlistItem]:
        ...

    def get(self, symbol: str) -> WatchlistItem | None:
        ...

    def add(self, symbol: str) -> WatchlistItem:
        ...

    def delete(self, symbol: str) -> bool:
        ...


class AlertConditionRepository(Protocol):
    def list_enabled_for_symbol(self, symbol: str) -> list[CustomAlertCondition]:
        ...

    def list(self) -> list[CustomAlertConditionRecord]:
        ...

    def save_validated(
        self,
        *,
        symbol: str,
        user_rule: str,
        validation: RuleValidationResult,
    ) -> CustomAlertConditionRecord:
        ...

    def delete(self, condition_id: int) -> bool:
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

    def mark_alert_sent(self, result: AnalysisResult) -> AnalysisResult:
        ...

    def has_sent_alert_for_conditions(self, symbol: str, triggered_alerts: list[str]) -> bool:
        ...

    def count_by_symbol(self, symbol: str) -> int:
        ...
