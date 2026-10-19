"""Published catalog reader and fenced, atomic writer (FR-U02..05)."""
from datetime import timedelta
from uuid import uuid4, uuid5, NAMESPACE_URL

from sqlalchemy import or_, select, update
from zoneinfo import ZoneInfo
from app.core.catalog_policy import CatalogPolicy
from sqlalchemy.exc import IntegrityError

from app.domain.briefings import utc
from app.domain.catalog import CatalogAttemptRecord, CatalogDelistingRecord, CatalogBatch, CatalogRevisionRecord, CatalogStateRecord, SecurityRecord, utcnow


class CatalogConflict(ValueError):
    pass


class SecurityCatalogReader:
    def __init__(self, db, clock=utcnow):
        self.db, self.clock = db, clock

    def metadata(self, country):
        row = self.db.get(CatalogStateRecord, country, populate_existing=True)
        if not row or not row.version:
            return {"country": country, "state": "UNAVAILABLE", "version": 0, "source_date": None}
        # Age of the source and age of the successful fetch are deliberately separate.
        # Seven calendar days tolerates weekends; configurable policy belongs to runtime.
        policy = CatalogPolicy.load()
        stale = ((self.clock().date() - row.source_date).days > policy.max_source_age_days
                 or self.clock() - utc(row.fetched_at) > timedelta(hours=policy.max_fetch_age_hours))
        return {"country": country, "state": "STALE" if stale else "READY", "version": row.version,
                "source_date": row.source_date, "fetched_at": row.fetched_at, "last_error": row.last_error}

    def confirmed_delistings(self):
        return set(self.db.scalars(select(CatalogDelistingRecord.security_id).where(
            CatalogDelistingRecord.revoked_at.is_(None),
            CatalogDelistingRecord.effective_on <= self.clock().astimezone(ZoneInfo("Asia/Seoul")).date())))

    def effective_status(self, row, confirmed_delistings=None):
        if row.country == "KR":
            if confirmed_delistings is None:
                confirmed_delistings = self.confirmed_delistings()
            if row.id in confirmed_delistings:
                return "delisted"
        return row.status

    def get(self, key):
        return self.db.get(SecurityRecord, key, populate_existing=True)

    def require_active(self, key=None, symbol=None, *, lock=False):
        if key:
            row = self.get(key)
        else:
            rows = list(self.db.scalars(select(SecurityRecord).where(SecurityRecord.symbol == symbol)))
            # Legacy symbols cannot disambiguate reuse, including a historical delisted row.
            row = rows[0] if len(rows) == 1 else None
        if not row or (symbol and row.symbol != symbol):
            raise CatalogConflict("종목 목록에서 대상을 다시 선택하세요.")
        if lock:
            # Publication takes the same country lock before changing rows.
            self.db.execute(update(CatalogStateRecord).where(CatalogStateRecord.country == row.country).values(
                version=CatalogStateRecord.version))
            self.db.refresh(row)
            if symbol and row.symbol != symbol:
                raise CatalogConflict("종목 코드가 변경됐습니다. 다시 선택하세요.")
        if self.effective_status(row) != "active" or self.metadata(row.country)["state"] != "READY":
            raise CatalogConflict("상장 상태를 확인할 수 없습니다. 목록 갱신 후 다시 시도하세요.")
        return row


class SecurityCatalogWriter:
    def __init__(self, db, clock=utcnow):
        self.db, self.clock = db, clock

    def claim(self, country):
        policy = CatalogPolicy.load()
        if self.db.get(CatalogStateRecord, country) is None:
            self.db.add(CatalogStateRecord(country=country, version=0, next_at=self.clock(), failures=0))
            try:
                self.db.commit()
            except IntegrityError:
                self.db.rollback()
        token = str(uuid4())
        count = self.db.execute(update(CatalogStateRecord).where(
            CatalogStateRecord.country == country, CatalogStateRecord.next_at <= self.clock(),
            or_(CatalogStateRecord.token.is_(None), CatalogStateRecord.lease_until <= self.clock()),
        ).values(token=token, lease_until=self.clock() + timedelta(minutes=10)),
            execution_options={"synchronize_session": False}).rowcount
        if count == 1:
            recent = list(self.db.scalars(select(CatalogAttemptRecord.started_at).where(
                CatalogAttemptRecord.country == country,
                CatalogAttemptRecord.started_at > self.clock() - timedelta(hours=24)).order_by(CatalogAttemptRecord.started_at)))
            if (len(recent) + 1) * 2 > policy.request_budget(country):
                self.db.execute(update(CatalogStateRecord).where(CatalogStateRecord.country == country).values(
                    token=None, lease_until=None, next_at=utc(recent[0]) + timedelta(hours=24), last_error="request_budget_exhausted"))
                self.db.commit()
                return None
            self.db.execute(update(CatalogAttemptRecord).where(CatalogAttemptRecord.country == country,
                CatalogAttemptRecord.status == "running").values(status="expired", finished_at=self.clock()))
            self.db.add(CatalogAttemptRecord(id=token, country=country, started_at=self.clock(), status="running"))
        self.db.commit()
        return token if count == 1 else None

    def validate_batch(self, batch):
        now = self.clock()
        state = self.db.get(CatalogStateRecord, batch.country, populate_existing=True)
        identities = [e.identity for e in batch.entries]
        active = [e.symbol for e in batch.entries if e.listed_on <= batch.source_date and
                  (e.delisted_on is None or e.delisted_on > batch.source_date)]
        if (len(identities) != len(set(identities)) or len(active) != len(set(active))
                or batch.source_date > now.date() or utc(batch.fetched_at) > now + timedelta(minutes=1)
                or (state.source_date and batch.source_date < state.source_date)
                or (state.source and state.source != batch.source)):
            raise CatalogConflict("invalid or regressing catalog batch")
        old = list(self.db.scalars(select(SecurityRecord).where(SecurityRecord.country == batch.country)))
        # An implausibly truncated result must not deactivate a market.
        old_active = sum(r.status == "active" for r in old)
        if old_active >= 20 and len(active) < old_active * .8:
            raise CatalogConflict("catalog completeness check failed")
        return state, old

    def publish(self, batch: CatalogBatch, token, interval_minutes):
        state, old = self.validate_batch(batch)
        now = self.clock()
        version = state.version + 1
        count = self.db.execute(update(CatalogStateRecord).where(
            CatalogStateRecord.country == batch.country, CatalogStateRecord.version == state.version,
            CatalogStateRecord.token == token, CatalogStateRecord.lease_until > now,
        ).values(version=version, source=batch.source, source_date=batch.source_date,
                 fetched_at=batch.fetched_at, token=None, lease_until=None, failures=0, last_error=None,
                 next_at=now + timedelta(minutes=interval_minutes)),
            execution_options={"synchronize_session": False}).rowcount
        if count != 1:
            self.db.rollback()
            raise CatalogConflict("catalog lease lost")
        by_identity = {r.source_identity: r for r in old}
        seen = set()
        for entry in batch.entries:
            row = by_identity.get(entry.identity)
            if row is None:
                row = SecurityRecord(id=str(uuid5(NAMESPACE_URL, f"catalog:{batch.country}:{batch.source}:{entry.identity}")),
                                     country=batch.country, source=batch.source, source_identity=entry.identity)
                self.db.add(row)
            seen.add(entry.identity)
            for field in ("symbol", "name", "exchange", "kind", "listed_on", "delisted_on", "aliases"):
                setattr(row, field, getattr(entry, field))
            row.status = ("pending" if entry.listed_on > batch.source_date else
                          "delisted" if entry.delisted_on and entry.delisted_on <= batch.source_date else "active")
            row.source_date, row.version = batch.source_date, version
        for row in old:
            if row.source_identity not in seen and row.status != "delisted":
                row.status, row.version = "unknown", version
        self.db.add(CatalogRevisionRecord(country=batch.country, version=version,
            source_date=batch.source_date, fetched_at=batch.fetched_at, evidence=batch.evidence,
            snapshot=batch.model_dump(mode="json")))
        self.db.execute(update(CatalogAttemptRecord).where(CatalogAttemptRecord.id == token).values(
            status="published", finished_at=now, version=version))
        self.db.commit()
        return version

    def verified(self, batch, token, report, interval):
        self.validate_batch(batch)
        now = self.clock()
        count = self.db.execute(update(CatalogStateRecord).where(
            CatalogStateRecord.country == batch.country, CatalogStateRecord.token == token,
            CatalogStateRecord.lease_until > now).values(token=None, lease_until=None,
                next_at=now + timedelta(minutes=interval)), execution_options={"synchronize_session": False}).rowcount
        if count != 1:
            self.db.rollback()
            raise CatalogConflict("catalog lease lost")
        self.db.execute(update(CatalogAttemptRecord).where(CatalogAttemptRecord.id == token).values(
            status="verified", finished_at=now, details=report))
        self.db.commit()

    def fail(self, country, token, reason):
        self.db.rollback()
        row = self.db.get(CatalogStateRecord, country, populate_existing=True)
        failures = row.failures + 1
        delay = (5, 15, 30)[min(failures - 1, 2)]
        if reason == "provider_rate_limit":
            delay = 24 * 60
        count = self.db.execute(update(CatalogStateRecord).where(CatalogStateRecord.country == country,
            CatalogStateRecord.token == token, CatalogStateRecord.lease_until > self.clock()).values(
                token=None, lease_until=None, failures=failures, last_error=reason,
                next_at=self.clock() + timedelta(minutes=delay)), execution_options={"synchronize_session": False}).rowcount
        if count == 1:
            self.db.execute(update(CatalogAttemptRecord).where(CatalogAttemptRecord.id == token).values(
                status="failed", finished_at=self.clock(), error=reason))
        self.db.commit()
