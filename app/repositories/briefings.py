from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.models import (
    BriefingDelivery,
    BriefingFailure,
    BriefingItem,
    BriefingScope,
    InvestmentBriefing,
)
from app.interfaces.repositories import BriefingRepository as BriefingRepositoryInterface


class BriefingRepository(BriefingRepositoryInterface):
    def __init__(self, db: Session) -> None:
        self.db = db

    def acquire_generation(
        self,
        *,
        user_id: str,
        exchange: str,
        briefing_type: str,
        trading_date: date,
        force: bool = False,
        stale_after_seconds: int = 900,
    ) -> tuple[InvestmentBriefing, bool]:
        existing = self._find_run(user_id, exchange, briefing_type, trading_date)
        if existing is not None:
            now = datetime.now(timezone.utc)
            started_at = existing.generation_started_at
            if started_at is not None and started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            generation_is_fresh = (
                existing.status == "GENERATING"
                and started_at is not None
                and started_at > now - timedelta(seconds=stale_after_seconds)
            )
            if generation_is_fresh or (
                existing.status in {"COMPLETED", "PARTIAL"} and not force
            ):
                return existing, False

            previous_version = existing.version
            claimed = self.db.execute(
                update(InvestmentBriefing)
                .where(
                    InvestmentBriefing.id == existing.id,
                    InvestmentBriefing.version == previous_version,
                )
                .values(
                    status="GENERATING",
                    generation_started_at=now,
                    generated_at=None,
                    summary="",
                    failure_count=0,
                    version=previous_version + 1,
                )
            )
            self.db.commit()
            self.db.refresh(existing)
            if claimed.rowcount == 1:
                self.db.execute(
                    update(BriefingDelivery)
                    .where(BriefingDelivery.briefing_id == existing.id)
                    .values(status="PENDING", sent_at=None, last_error=None)
                )
                self.db.commit()
            return existing, claimed.rowcount == 1

        briefing = InvestmentBriefing(
            user_id=user_id,
            exchange=exchange,
            briefing_type=briefing_type,
            trading_date=trading_date,
            status="GENERATING",
            generation_started_at=datetime.now(timezone.utc),
        )
        self.db.add(briefing)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = self._find_run(user_id, exchange, briefing_type, trading_date)
            if existing is not None:
                return existing, False
            raise
        self.db.refresh(briefing)
        return briefing, True

    def replace_items(
        self, briefing: InvestmentBriefing, items: list[dict[str, Any]]
    ) -> list[BriefingItem]:
        self.db.execute(delete(BriefingItem).where(BriefingItem.briefing_id == briefing.id))
        rows = [BriefingItem(briefing_id=briefing.id, **item) for item in items]
        self.db.add_all(rows)
        self.db.commit()
        for row in rows:
            self.db.refresh(row)
        return rows

    def replace_scope(
        self,
        briefing_id: int,
        *,
        source_type: str,
        source_value: str | None,
        resolved_symbols: list[str],
    ) -> BriefingScope:
        self.db.execute(delete(BriefingScope).where(BriefingScope.briefing_id == briefing_id))
        scope = BriefingScope(
            briefing_id=briefing_id,
            source_type=source_type,
            source_value=source_value,
            resolved_symbols=resolved_symbols,
        )
        self.db.add(scope)
        self.db.commit()
        self.db.refresh(scope)
        return scope

    def replace_failures(
        self, briefing_id: int, failures: list[dict[str, Any]]
    ) -> list[BriefingFailure]:
        self.db.execute(delete(BriefingFailure).where(BriefingFailure.briefing_id == briefing_id))
        rows = [BriefingFailure(briefing_id=briefing_id, **failure) for failure in failures]
        self.db.add_all(rows)
        self.db.commit()
        for row in rows:
            self.db.refresh(row)
        return rows

    def finalize(
        self,
        briefing: InvestmentBriefing,
        *,
        status: str,
        summary: str,
        resolved_symbols: list[str],
        failure_count: int,
    ) -> InvestmentBriefing:
        briefing.status = status
        briefing.summary = summary
        briefing.resolved_symbols = resolved_symbols
        briefing.failure_count = failure_count
        briefing.generated_at = datetime.now(timezone.utc)
        briefing.generation_started_at = None
        self.db.add(briefing)
        self.db.commit()
        self.db.refresh(briefing)
        return briefing

    def complete_generation(
        self,
        briefing: InvestmentBriefing,
        *,
        items: list[dict[str, Any]],
        failures: list[dict[str, Any]],
        status: str,
        summary: str,
        resolved_symbols: list[str],
    ) -> InvestmentBriefing:
        self.db.execute(delete(BriefingItem).where(BriefingItem.briefing_id == briefing.id))
        self.db.execute(delete(BriefingFailure).where(BriefingFailure.briefing_id == briefing.id))
        self.db.add_all([BriefingItem(briefing_id=briefing.id, **item) for item in items])
        self.db.add_all(
            [BriefingFailure(briefing_id=briefing.id, **failure) for failure in failures]
        )
        briefing.status = status
        briefing.summary = summary
        briefing.resolved_symbols = resolved_symbols
        briefing.failure_count = len(failures)
        briefing.generated_at = datetime.now(timezone.utc)
        briefing.generation_started_at = None
        self.db.add(briefing)
        self.db.commit()
        self.db.refresh(briefing)
        return briefing

    def ensure_delivery(self, briefing_id: int, channel: str) -> BriefingDelivery:
        existing = self.db.scalar(
            select(BriefingDelivery).where(
                BriefingDelivery.briefing_id == briefing_id,
                BriefingDelivery.channel == channel,
            )
        )
        if existing is not None:
            return existing
        delivery = BriefingDelivery(briefing_id=briefing_id, channel=channel)
        self.db.add(delivery)
        self.db.commit()
        self.db.refresh(delivery)
        return delivery

    def record_delivery_attempt(
        self,
        delivery: BriefingDelivery,
        *,
        status: str,
        error: str | None = None,
    ) -> BriefingDelivery:
        delivery.attempt_count += 1
        delivery.status = status
        delivery.last_error = error
        delivery.sent_at = datetime.now(timezone.utc) if status == "SENT" else None
        self.db.add(delivery)
        self.db.commit()
        self.db.refresh(delivery)
        return delivery

    def list_for_user(
        self, user_id: str, *, limit: int, offset: int
    ) -> list[InvestmentBriefing]:
        statement = (
            select(InvestmentBriefing)
            .where(InvestmentBriefing.user_id == user_id)
            .order_by(InvestmentBriefing.trading_date.desc(), InvestmentBriefing.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(self.db.scalars(statement))

    def get_for_user(self, briefing_id: int, user_id: str) -> InvestmentBriefing | None:
        return self.db.scalar(
            select(InvestmentBriefing).where(
                InvestmentBriefing.id == briefing_id,
                InvestmentBriefing.user_id == user_id,
            )
        )

    def list_items(self, briefing_id: int) -> list[BriefingItem]:
        return list(
            self.db.scalars(
                select(BriefingItem)
                .where(BriefingItem.briefing_id == briefing_id)
                .order_by(BriefingItem.rank, BriefingItem.id)
            )
        )

    def list_deliveries(self, briefing_id: int) -> list[BriefingDelivery]:
        return list(
            self.db.scalars(
                select(BriefingDelivery)
                .where(BriefingDelivery.briefing_id == briefing_id)
                .order_by(BriefingDelivery.id)
            )
        )

    def list_scopes(self, briefing_id: int) -> list[BriefingScope]:
        return list(
            self.db.scalars(
                select(BriefingScope)
                .where(BriefingScope.briefing_id == briefing_id)
                .order_by(BriefingScope.id)
            )
        )

    def list_failures(self, briefing_id: int) -> list[BriefingFailure]:
        return list(
            self.db.scalars(
                select(BriefingFailure)
                .where(BriefingFailure.briefing_id == briefing_id)
                .order_by(BriefingFailure.id)
            )
        )

    def _find_run(
        self, user_id: str, exchange: str, briefing_type: str, trading_date: date
    ) -> InvestmentBriefing | None:
        return self.db.scalar(
            select(InvestmentBriefing).where(
                InvestmentBriefing.user_id == user_id,
                InvestmentBriefing.exchange == exchange,
                InvestmentBriefing.briefing_type == briefing_type,
                InvestmentBriefing.trading_date == trading_date,
            )
        )
