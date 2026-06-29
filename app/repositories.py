from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.alert_conditions import CustomAlertCondition, RuleValidationResult
from app.models import AnalysisResult, CustomAlertConditionRecord, WatchlistItem


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


class WatchlistRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self) -> list[WatchlistItem]:
        return list(self.db.scalars(select(WatchlistItem).order_by(WatchlistItem.symbol)))

    def get(self, symbol: str) -> WatchlistItem | None:
        normalized = normalize_symbol(symbol)
        return self.db.scalar(select(WatchlistItem).where(WatchlistItem.symbol == normalized))

    def add(self, symbol: str) -> WatchlistItem:
        normalized = normalize_symbol(symbol)
        existing = self.get(normalized)
        if existing is not None:
            return existing

        item = WatchlistItem(symbol=normalized)
        self.db.add(item)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = self.get(normalized)
            if existing is not None:
                return existing
            raise
        self.db.refresh(item)
        return item

    def delete(self, symbol: str) -> bool:
        item = self.get(symbol)
        if item is None:
            return False

        self.db.delete(item)
        self.db.commit()
        return True


class AlertConditionRepository:
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

    def list(self) -> list[CustomAlertConditionRecord]:
        return list(self.db.scalars(select(CustomAlertConditionRecord).order_by(CustomAlertConditionRecord.id)))

    def save_validated(
        self,
        *,
        symbol: str,
        user_rule: str,
        validation: RuleValidationResult,
    ) -> CustomAlertConditionRecord:
        if not validation.is_valid or not validation.normalized_name or not validation.normalized_rule:
            raise ValueError("only valid alert conditions can be saved")

        normalized = normalize_symbol(symbol)
        record = CustomAlertConditionRecord(
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
                    CustomAlertConditionRecord.symbol == normalized,
                    CustomAlertConditionRecord.user_rule == user_rule.strip(),
                )
            )
            if existing is not None:
                return existing
            raise
        self.db.refresh(record)
        return record

    def delete(self, condition_id: int) -> bool:
        record = self.db.get(CustomAlertConditionRecord, condition_id)
        if record is None:
            return False
        self.db.delete(record)
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


class AnalysisRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_latest(self, symbol: str) -> AnalysisResult | None:
        normalized = normalize_symbol(symbol)
        statement = (
            select(AnalysisResult)
            .where(AnalysisResult.symbol == normalized)
            .order_by(AnalysisResult.analyzed_at.desc(), AnalysisResult.id.desc())
            .limit(1)
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
        )
        self.db.add(result)
        self.db.commit()
        self.db.refresh(result)
        return result

    def mark_alert_sent(self, result: AnalysisResult) -> AnalysisResult:
        result.alert_sent_at = datetime.now(timezone.utc)
        self.db.add(result)
        self.db.commit()
        self.db.refresh(result)
        return result

    def has_sent_alert_for_conditions(self, symbol: str, triggered_alerts: list[str]) -> bool:
        normalized = normalize_symbol(symbol)
        conditions_key = tuple(sorted(triggered_alerts or []))
        if not conditions_key:
            return False

        statement = (
            select(AnalysisResult)
            .where(AnalysisResult.symbol == normalized)
            .where(AnalysisResult.alert_sent_at.is_not(None))
        )
        for row in self.db.scalars(statement):
            if tuple(sorted(row.triggered_alerts or [])) == conditions_key:
                return True
        return False

    def count_by_symbol(self, symbol: str) -> int:
        normalized = normalize_symbol(symbol)
        rows = self.db.scalars(select(AnalysisResult).where(AnalysisResult.symbol == normalized))
        return sum(1 for _ in rows)
