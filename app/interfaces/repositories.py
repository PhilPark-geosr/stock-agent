"""Repository interfaces used by application services."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Protocol

from app.domain.alert_conditions import CustomAlertCondition, RuleValidationResult
from app.domain.models import (
    AnalysisResult,
    BriefingDelivery,
    BriefingFailure,
    BriefingItem,
    BriefingScope,
    CustomAlertConditionRecord,
    InvestmentBriefing,
    WatchlistSubscription,
)
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

    def list_owner_ids(self) -> list[str]:
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
        symbol: str,
        before_id: int | None = None,
        briefing_type: str | None = None,
        trading_date: date | None = None,
    ) -> AnalysisResult | None:
        ...

    def get_for_briefing(
        self,
        *,
        symbol: str,
        briefing_type: str,
        trading_date: date,
    ) -> AnalysisResult | None:
        ...


class BriefingRepository(Protocol):
    def acquire_generation(
        self,
        *,
        user_account_id: str,
        exchange: str,
        briefing_type: str,
        trading_date: date,
        force: bool = False,
        stale_after_seconds: int = 900,
    ) -> tuple[InvestmentBriefing, bool]:
        ...

    def replace_items(self, briefing: InvestmentBriefing, items: list[dict[str, Any]]) -> list[BriefingItem]:
        ...

    def replace_scope(
        self,
        briefing_id: int,
        *,
        source_type: str,
        source_value: str | None,
        resolved_symbols: list[str],
    ) -> BriefingScope:
        ...

    def replace_failures(
        self, briefing_id: int, failures: list[dict[str, Any]]
    ) -> list[BriefingFailure]:
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

    def complete_generation(
        self,
        briefing: InvestmentBriefing,
        *,
        items: list[dict[str, Any]],
        failures: list[dict[str, Any]],
        status: str,
        summary: str,
        resolved_symbols: list[str],
        scope_source_type: str,
        scope_source_value: str | None,
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

    def list_for_user(self, user_account_id: str, *, limit: int, offset: int) -> list[InvestmentBriefing]:
        ...

    def get_for_user(self, briefing_id: int, user_account_id: str) -> InvestmentBriefing | None:
        ...

    def list_items(self, briefing_id: int) -> list[BriefingItem]:
        ...

    def list_deliveries(self, briefing_id: int) -> list[BriefingDelivery]:
        ...

    def list_scopes(self, briefing_id: int) -> list[BriefingScope]:
        ...

    def list_failures(self, briefing_id: int) -> list[BriefingFailure]:
        ...

    def get_failure_retry_state(self, briefing_id: int) -> dict[str, dict[str, Any]]:
        ...
