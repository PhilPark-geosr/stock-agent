from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.models import BriefingDelivery, BriefingItem, InvestmentBriefing
from app.interfaces.repositories import BriefingRepository as BriefingRepositoryInterface


class BriefingRepository(BriefingRepositoryInterface):
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_or_get(
        self, *, user_id: str, exchange: str, briefing_type: str, trading_date: date
    ) -> tuple[InvestmentBriefing, bool]:
        existing = self._find_run(user_id, exchange, briefing_type, trading_date)
        if existing is not None:
            return existing, False

        briefing = InvestmentBriefing(
            user_id=user_id,
            exchange=exchange,
            briefing_type=briefing_type,
            trading_date=trading_date,
            status="GENERATING",
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
