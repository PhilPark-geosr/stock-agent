from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.domain.briefing_records import (
    BriefingDeliveryRecord, BriefingPreferenceRecord, BriefingRunRecord,
    PromptActivationRecord, PromptVersionRecord,
)
from app.domain.briefings import BriefingConflict, BriefingContext, BriefingSettings, LostClaim, utc


def now_utc():
    return datetime.now(timezone.utc)


class BriefingHistory:
    """Atomic run claims and immutable snapshots, isolated by the authenticated owner."""
    def __init__(self, db, clock=now_utc):
        self.db = db
        self.clock = clock

    def settings(self, owner, market):
        row = self.db.scalar(select(BriefingPreferenceRecord).where(
            BriefingPreferenceRecord.owner_id == owner, BriefingPreferenceRecord.market == market))
        return BriefingSettings(**{k: getattr(row, k) for k in BriefingSettings.model_fields}) if row else BriefingSettings()

    def save_settings(self, owner, market, settings):
        row = self.db.scalar(select(BriefingPreferenceRecord).where(
            BriefingPreferenceRecord.owner_id == owner, BriefingPreferenceRecord.market == market))
        if row is None:
            row = BriefingPreferenceRecord(id=str(uuid4()), owner_id=owner, market=market)
        for key, value in settings.model_dump().items():
            setattr(row, key, value)
        self.db.add(row)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise BriefingConflict("설정이 동시에 변경됐습니다. 다시 저장하세요.") from exc
        return settings

    def get(self, owner, run_id):
        row = self.db.scalar(select(BriefingRunRecord).where(
            BriefingRunRecord.id == run_id, BriefingRunRecord.owner_id == owner))
        if row is None:
            raise LookupError("브리핑을 찾을 수 없습니다.")
        return row

    def by_request(self, owner, key):
        return self.db.scalar(select(BriefingRunRecord).where(
            BriefingRunRecord.owner_id == owner, BriefingRunRecord.request_key == key))

    def list(self, owner, limit=30, offset=0):
        return list(self.db.scalars(select(BriefingRunRecord).where(
            BriefingRunRecord.owner_id == owner).order_by(
                BriefingRunRecord.created_at.desc(), BriefingRunRecord.id.desc()).limit(limit).offset(offset)))

    def previous(self, owner, context: BriefingContext):
        rows = list(self.db.scalars(select(BriefingRunRecord).where(
            BriefingRunRecord.owner_id == owner, BriefingRunRecord.market == context.market,
            BriefingRunRecord.trade_date.in_([str(context.trade_date), str(context.previous_trade_date)]),
            BriefingRunRecord.status.in_(["completed", "partial"]),
            BriefingRunRecord.completed_at < context.started_at,
        ).order_by(BriefingRunRecord.completed_at.desc(), BriefingRunRecord.id.desc())))
        rows = [r for r in rows if utc(datetime.fromisoformat(r.context["cutoff_at"])) < context.cutoff_at
                and set(r.context["symbols"]) & set(context.symbols)]
        if context.purpose == "post_market":
            morning = [r for r in rows if r.trade_date == str(context.trade_date) and r.purpose == "pre_market"]
            if morning:
                return morning[0]
        today = [r for r in rows if r.trade_date == str(context.trade_date)]
        return (today or rows or [None])[0]

    def reserve(self, owner, key, request_data, context, prompt_id, previous_id, original_id):
        now = self.clock()
        row = BriefingRunRecord(id=str(uuid4()), owner_id=owner, request_key=key,
            request_data=request_data, market=context.market, purpose=context.purpose,
            trade_date=str(context.trade_date), context=context.model_dump(mode="json"), prompt_id=prompt_id,
            previous_id=previous_id, original_id=original_id, status="preparing", created_at=now,
            claim_token=str(uuid4()), lease_until=now + timedelta(minutes=10))
        self.db.add(row)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = self.by_request(owner, key)
            if existing is None:
                raise
            return existing, False
        return row, True

    def claim_update(self, run_id, token, **values):
        count = self.db.execute(update(BriefingRunRecord).where(
            BriefingRunRecord.id == run_id, BriefingRunRecord.claim_token == token,
            BriefingRunRecord.status == "preparing", BriefingRunRecord.lease_until > self.clock(),
        ).values(**values), execution_options={"synchronize_session": False}).rowcount
        if count != 1:
            self.db.rollback()
            raise LostClaim("생성 작업 소유권이 만료되거나 변경됐습니다.")

    def renew(self, run_id, token):
        self.claim_update(run_id, token, lease_until=self.clock() + timedelta(minutes=10))
        self.db.commit()

    def snapshot(self, run_id, token, snapshot):
        self.claim_update(run_id, token, snapshot=snapshot.model_dump(mode="json"))
        self.db.commit()

    def finish(self, row, token, *, status, result=None, failure_reason=None, message=None):
        self.claim_update(row.id, token, status=status, result=result, failure_reason=failure_reason,
            completed_at=self.clock(), claim_token=None, lease_until=None)
        if status in ("completed", "partial"):
            enabled = self.settings(row.owner_id, row.market).kakao_enabled
            self.db.add(BriefingDeliveryRecord(id=str(uuid4()), run_id=row.id, owner_id=row.owner_id,
                channel="kakao", message=message or "브리핑이 준비됐습니다.",
                status="pending" if enabled else "not_requested", attempts=[], updated_at=self.clock()))
        self.db.commit()  # Result + pending delivery are one transaction (outbox).
        self.db.expire_all()
        return self.get(row.owner_id, row.id)

    def reclaim(self, row):
        token = str(uuid4())
        count = self.db.execute(update(BriefingRunRecord).where(
            BriefingRunRecord.id == row.id, BriefingRunRecord.status == "preparing",
            BriefingRunRecord.lease_until <= self.clock(),
        ).values(claim_token=token, lease_until=self.clock() + timedelta(minutes=10)),
            execution_options={"synchronize_session": False}).rowcount
        self.db.commit()
        self.db.expire_all()
        return token if count == 1 else None

    def delivery(self, run_id):
        return self.db.scalar(select(BriefingDeliveryRecord).where(BriefingDeliveryRecord.run_id == run_id))

    def payload(self, row, *, detail=True):
        delivery = self.delivery(row.id)
        value = {"id": row.id, "market": row.market, "purpose": row.purpose,
            "trade_date": row.trade_date, "status": row.status, "created_at": row.created_at,
            "failure_reason": row.failure_reason, "previous_id": row.previous_id,
            "original_id": row.original_id, "prompt_id": row.prompt_id,
            "context": row.context, "result": row.result,
            "delivery": None if delivery is None else {
                "status": delivery.status, "reason": delivery.reason, "attempts": delivery.attempts}}
        if detail:
            prompt = self.db.get(PromptVersionRecord, row.prompt_id)
            value.update(snapshot=row.snapshot, prompt_content=prompt.content)
        return value
