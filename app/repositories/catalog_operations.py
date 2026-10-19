"""Operator evidence, audit retention and existing-alert eligibility."""
from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse
import re
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator
from sqlalchemy import delete, or_, select, update

from app.core.catalog_policy import CatalogPolicy
from app.domain.catalog import (CatalogAttemptRecord, CatalogDelistingRecord, CatalogRevisionRecord,
                                CatalogStateRecord, SecurityRecord, utcnow)
from app.domain.models import WatchlistSubscription
from app.repositories.catalog import CatalogConflict, SecurityCatalogReader


class DelistingEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    security_id: str = Field(min_length=1, max_length=36)
    source_identity: str = Field(pattern=r"^KR[0-9A-Z]{10}$")
    effective_on: date
    source_url: str = Field(max_length=1000)
    reviewed_by: str = Field(min_length=1, max_length=120)
    confirmed: StrictBool

    @field_validator("confirmed")
    @classmethod
    def confirmation(cls, value):
        if not value:
            raise ValueError("operator confirmation is required")
        return value

    @field_validator("reviewed_by")
    @classmethod
    def reviewer(cls, value):
        if not value.strip():
            raise ValueError("reviewer is required")
        return value.strip()

    @field_validator("source_url")
    @classmethod
    def official_document(cls, value):
        url = urlparse(value)
        if (url.scheme != "https" or url.hostname != "kind.krx.co.kr" or url.username or url.password
                or url.port not in (None, 443) or not (url.path.startswith("/external/")
                or (url.path == "/common/disclsviewer.do" and re.fullmatch(r"[0-9]{14}", parse_qs(url.query).get("acptno", [""])[0])))):
            raise ValueError("use the exact official KIND disclosure URL")
        return value


class CatalogMaintenance:
    def __init__(self, db, clock=utcnow):
        self.db, self.clock = db, clock

    def _lock(self, country):
        count = self.db.execute(update(CatalogStateRecord).where(CatalogStateRecord.country == country,
            or_(CatalogStateRecord.token.is_(None), CatalogStateRecord.lease_until <= self.clock())).values(
                version=CatalogStateRecord.version)).rowcount
        if not count:
            self.db.rollback()
            raise CatalogConflict("country refresh is running or no catalog exists")

    def record_delisting(self, evidence):
        try:
            self._lock("KR")
            row = self.db.get(SecurityRecord, evidence.security_id, populate_existing=True)
            if (not row or row.country != "KR" or row.source != "KRX"
                    or row.source_identity != evidence.source_identity or evidence.effective_on < row.listed_on):
                raise CatalogConflict("delisting identity or effective date does not match")
            existing = self.db.scalar(select(CatalogDelistingRecord).where(
                CatalogDelistingRecord.security_id == row.id, CatalogDelistingRecord.revoked_at.is_(None)))
            if existing:
                if existing.effective_on == evidence.effective_on and existing.source_url == evidence.source_url:
                    self.db.commit()
                    return existing.id
                raise CatalogConflict("revoke the existing evidence with a reason before correcting it")
            record = CatalogDelistingRecord(id=str(uuid4()), security_id=row.id,
                effective_on=evidence.effective_on, source_url=evidence.source_url,
                reviewed_by=evidence.reviewed_by, recorded_at=self.clock())
            self.db.add(record)
            self.db.commit()
            return record.id
        except Exception:
            self.db.rollback()
            raise

    def revoke_delisting(self, key, reason):
        if not reason or not reason.strip() or len(reason) > 1000:
            raise ValueError("a correction reason of 1..1000 characters is required")
        try:
            self._lock("KR")
            row = self.db.get(CatalogDelistingRecord, key, populate_existing=True)
            if not row:
                raise CatalogConflict("delisting evidence not found")
            if row.revoked_at is None:
                row.revoked_at, row.revocation_reason = self.clock(), reason.strip()
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def prune(self):
        policy = CatalogPolicy.load()
        result = {}
        for country in ("KR", "US"):
            try:
                self._lock(country)
            except CatalogConflict:
                result[country] = "skipped"
                continue
            state = self.db.get(CatalogStateRecord, country, populate_existing=True)
            snapshots = self.db.execute(delete(CatalogRevisionRecord).where(
                CatalogRevisionRecord.country == country, CatalogRevisionRecord.version != state.version,
                CatalogRevisionRecord.fetched_at < self.clock() - timedelta(days=policy.snapshot_days))).rowcount
            attempts = self.db.execute(delete(CatalogAttemptRecord).where(
                CatalogAttemptRecord.country == country, CatalogAttemptRecord.status != "running",
                CatalogAttemptRecord.finished_at < self.clock() - timedelta(days=policy.attempt_days))).rowcount
            self.db.commit()
            result[country] = {"snapshots": snapshots, "attempts": attempts}
        return result


class CatalogAlertGate:
    def __init__(self, db, clock=utcnow):
        self.db = db
        self.reader = SecurityCatalogReader(db, clock)

    def reason(self, subscription_id):
        row = self.db.get(WatchlistSubscription, subscription_id, populate_existing=True)
        if not row or row.ended_at is not None:
            return "관심종목 종료 — 알림 보류"
        if not row.security_id:
            return "종목 연결 확인 필요 — 알림 보류"
        security = self.reader.get(row.security_id)
        if not security or security.symbol != row.symbol:
            return "종목 정보 불일치 — 알림 보류"
        if self.reader.effective_status(security) != "active":
            return "상폐 또는 상장 상태 미확인 — 알림 보류"
        if self.reader.metadata(security.country)["state"] != "READY":
            return "종목 자료 갱신 필요 — 알림 보류"
        return None

    def allowed(self, subscription_id):
        return self.reason(subscription_id) is None
