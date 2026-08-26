from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.alert_conditions import CustomAlertCondition, RuleValidationResult
from app.domain.models import AnalysisResult, CustomAlertConditionRecord, WatchlistSubscription
from app.domain.symbols import StockSymbol, normalize_symbol
from app.interfaces.repositories import (
    AlertConditionRepository as AlertConditionRepositoryInterface,
    AnalysisRepository as AnalysisRepositoryInterface,
    WatchlistRepository as WatchlistRepositoryInterface,
)


class WatchlistRepository(WatchlistRepositoryInterface):
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self, owner_id: str) -> list[WatchlistSubscription]:
        statement = (
            select(WatchlistSubscription)
            .where(WatchlistSubscription.owner_id == owner_id)
            .where(WatchlistSubscription.ended_at.is_(None))
            .order_by(WatchlistSubscription.symbol)
        )
        return list(self.db.scalars(statement))

    def get(self, owner_id: str, symbol: StockSymbol) -> WatchlistSubscription | None:
        return self.db.scalar(
            select(WatchlistSubscription).where(
                WatchlistSubscription.owner_id == owner_id,
                WatchlistSubscription.symbol == symbol.value,
                WatchlistSubscription.ended_at.is_(None),
            )
        )

    def add(self, owner_id: str, symbol: StockSymbol) -> WatchlistSubscription:
        existing = self.get(owner_id, symbol)
        if existing is not None:
            return existing

        item = WatchlistSubscription(owner_id=owner_id, symbol=symbol.value)
        self.db.add(item)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = self.get(owner_id, symbol)
            if existing is not None:
                return existing
            raise
        self.db.refresh(item)
        return item

    def delete(self, owner_id: str, symbol: StockSymbol) -> bool:
        item = self.get(owner_id, symbol)
        if item is None:
            return False

        ended_at = datetime.now(timezone.utc)
        item.end(ended_at)
        conditions = self.db.scalars(
            select(CustomAlertConditionRecord).where(
                CustomAlertConditionRecord.subscription_id == item.id,
                CustomAlertConditionRecord.ended_at.is_(None),
            )
        )
        for condition in conditions:
            condition.end(ended_at)
            self.db.add(condition)
        self.db.add(item)
        self.db.commit()
        return True

    def list_distinct_active_symbols(self) -> list[StockSymbol]:
        statement = (
            select(WatchlistSubscription.symbol)
            .where(WatchlistSubscription.owner_id.is_not(None))
            .where(WatchlistSubscription.ended_at.is_(None))
            .distinct()
            .order_by(WatchlistSubscription.symbol)
        )
        return [StockSymbol.of(symbol) for symbol in self.db.scalars(statement)]

    def list_active_for_symbol(self, symbol: StockSymbol | str) -> list[WatchlistSubscription]:
        value = symbol.value if isinstance(symbol, StockSymbol) else normalize_symbol(symbol)
        return list(self.db.scalars(select(WatchlistSubscription).where(
            WatchlistSubscription.symbol == value,
            WatchlistSubscription.owner_id.is_not(None),
            WatchlistSubscription.ended_at.is_(None),
        ).order_by(WatchlistSubscription.id)))


class AlertConditionRepository(AlertConditionRepositoryInterface):
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_enabled_for_symbol(self, symbol: str) -> list[CustomAlertCondition]:
        normalized = normalize_symbol(symbol)
        statement = (
            select(CustomAlertConditionRecord)
            .where(CustomAlertConditionRecord.symbol == normalized)
            .where(CustomAlertConditionRecord.enabled.is_(True))
            .order_by(CustomAlertConditionRecord.id)
        )
        return [self._to_domain(row) for row in self.db.scalars(statement)]

    def list(self, owner_id: str) -> list[CustomAlertConditionRecord]:
        statement = (
            select(CustomAlertConditionRecord)
            .join(
                WatchlistSubscription,
                CustomAlertConditionRecord.subscription_id == WatchlistSubscription.id,
            )
            .where(WatchlistSubscription.owner_id == owner_id)
            .where(WatchlistSubscription.ended_at.is_(None))
            .where(CustomAlertConditionRecord.ended_at.is_(None))
            .order_by(CustomAlertConditionRecord.id)
        )
        return list(self.db.scalars(statement))

    def save_validated(
        self,
        *,
        owner_id: str,
        symbol: str,
        user_rule: str,
        validation: RuleValidationResult,
    ) -> CustomAlertConditionRecord:
        if not validation.is_valid or not validation.normalized_name or not validation.normalized_rule:
            raise ValueError("only valid alert conditions can be saved")

        normalized = normalize_symbol(symbol)
        subscription = self.db.scalar(
            select(WatchlistSubscription).where(
                WatchlistSubscription.owner_id == owner_id,
                WatchlistSubscription.symbol == normalized,
                WatchlistSubscription.ended_at.is_(None),
            )
        )
        if subscription is None:
            raise LookupError("active watchlist subscription not found")
        record = CustomAlertConditionRecord(
            subscription_id=subscription.id,
            symbol=normalized,
            name=validation.normalized_name,
            user_rule=user_rule.strip(),
            normalized_rule=validation.normalized_rule,
            validation_summary=validation.validation_summary,
            required_tools=[],
            related_symbols=[],
            news_symbols=[],
        )
        self.db.add(record)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = self.db.scalar(
                select(CustomAlertConditionRecord).where(
                    CustomAlertConditionRecord.subscription_id == subscription.id,
                    CustomAlertConditionRecord.user_rule == user_rule.strip(),
                    CustomAlertConditionRecord.ended_at.is_(None),
                )
            )
            if existing is not None:
                return existing
            raise
        self.db.refresh(record)
        return record

    def delete(self, owner_id: str, condition_id: int) -> bool:
        record = self.db.scalar(
            select(CustomAlertConditionRecord)
            .join(
                WatchlistSubscription,
                CustomAlertConditionRecord.subscription_id == WatchlistSubscription.id,
            )
            .where(
                CustomAlertConditionRecord.id == condition_id,
                CustomAlertConditionRecord.ended_at.is_(None),
                WatchlistSubscription.owner_id == owner_id,
                WatchlistSubscription.ended_at.is_(None),
            )
        )
        if record is None:
            return False
        record.end(datetime.now(timezone.utc))
        self.db.add(record)
        self.db.commit()
        return True

    @staticmethod
    def _to_domain(record: CustomAlertConditionRecord) -> CustomAlertCondition:
        return CustomAlertCondition(
            id=f"custom.{record.id}",
            symbol=record.symbol,
            name=record.name,
            user_rule=record.user_rule,
            normalized_rule=record.normalized_rule,
            validation_summary=record.validation_summary,
            required_tools=record.required_tools or [],
            related_symbols=record.related_symbols or [],
            news_symbols=record.news_symbols or [],
            enabled=record.enabled,
        )


class AnalysisRepository(AnalysisRepositoryInterface):
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_latest(self, symbol: str) -> AnalysisResult | None:
        normalized = normalize_symbol(symbol)
        statement = (
            select(AnalysisResult)
            .where(AnalysisResult.symbol == normalized)
            .where(AnalysisResult.shared_safe.is_(True))
            .order_by(AnalysisResult.analyzed_at.desc(), AnalysisResult.id.desc())
            .limit(1)
        )
        return self.db.scalar(statement)

    def list_by_symbol(
        self,
        symbol: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[AnalysisResult]:
        normalized = normalize_symbol(symbol)
        statement = (
            select(AnalysisResult)
            .where(AnalysisResult.symbol == normalized)
            .where(AnalysisResult.shared_safe.is_(True))
            .order_by(AnalysisResult.analyzed_at.desc(), AnalysisResult.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(self.db.scalars(statement))

    def get_by_id(self, symbol: str, result_id: int) -> AnalysisResult | None:
        normalized = normalize_symbol(symbol)
        statement = (
            select(AnalysisResult)
            .where(AnalysisResult.symbol == normalized)
            .where(AnalysisResult.id == result_id)
            .where(AnalysisResult.shared_safe.is_(True))
        )
        return self.db.scalar(statement)

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
        result = AnalysisResult(
            symbol=normalize_symbol(symbol),
            data_timestamp=data_timestamp,
            overall_judgment=overall_judgment,
            summary=summary,
            key_reasons=key_reasons or [],
            risk_factors=risk_factors or [],
            support_levels=support_levels or {},
            should_alert=should_alert,
            triggered_alerts=triggered_alerts or [],
            alert_reason=alert_reason,
            raw_result=raw_result,
            shared_safe=True,
        )
        self.db.add(result)
        self.db.commit()
        self.db.refresh(result)
        return result

    def count_by_symbol(self, symbol: str) -> int:
        normalized = normalize_symbol(symbol)
        rows = self.db.scalars(
            select(AnalysisResult).where(
                AnalysisResult.symbol == normalized,
                AnalysisResult.shared_safe.is_(True),
            )
        )
        return sum(1 for _ in rows)
