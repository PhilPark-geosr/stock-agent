"""Repository interfaces used by application services."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Protocol

from app.domain.alert_conditions import CustomAlertCondition, RuleValidationResult
from app.domain.models import (
    AnalysisResult,
    BriefingDelivery,
    BriefingItem,
    CustomAlertConditionRecord,
    InvestmentBriefing,
    WatchlistItem,
)


class WatchlistRepository(Protocol):
    def list(self, user_id: str = "default") -> list[WatchlistItem]:
        ...

    def get(self, symbol: str, user_id: str = "default") -> WatchlistItem | None:
        ...

    def add(self, symbol: str, user_id: str = "default") -> WatchlistItem:
        ...

    def delete(self, symbol: str, user_id: str = "default") -> bool:
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
    def get_latest(self, symbol: str, user_id: str = "default") -> AnalysisResult | None:
        ...

    def save(
        self,
        *,
        symbol: str,
        user_id: str = "default",
        overall_judgment: str,
        summary: str,
        normalized_judgment: str = "UNKNOWN",
        briefing_type: str | None = None,
        trading_date: date | None = None,
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

    def get_previous_comparable(
        self,
        *,
        user_id: str,
        symbol: str,
        before_id: int | None = None,
        briefing_type: str | None = None,
        trading_date: date | None = None,
    ) -> AnalysisResult | None:
        ...


class BriefingRepository(Protocol):
    def create_or_get(
        self, *, user_id: str, exchange: str, briefing_type: str, trading_date: date
    ) -> tuple[InvestmentBriefing, bool]:
        ...

    def replace_items(self, briefing: InvestmentBriefing, items: list[dict[str, Any]]) -> list[BriefingItem]:
        ...

    def finalize(
        self,
        briefing: InvestmentBriefing,
        *,
        status: str,
        summary: str,
        resolved_symbols: list[str],
        failure_count: int,
    ) -> InvestmentBriefing:
        ...

    def ensure_delivery(self, briefing_id: int, channel: str) -> BriefingDelivery:
        ...

    def record_delivery_attempt(
        self,
        delivery: BriefingDelivery,
        *,
        status: str,
        error: str | None = None,
    ) -> BriefingDelivery:
        ...

    def list_for_user(self, user_id: str, *, limit: int, offset: int) -> list[InvestmentBriefing]:
        ...

    def get_for_user(self, briefing_id: int, user_id: str) -> InvestmentBriefing | None:
        ...

    def list_items(self, briefing_id: int) -> list[BriefingItem]:
        ...

    def list_deliveries(self, briefing_id: int) -> list[BriefingDelivery]:
        ...
