"""Scope first, then shared matching/sorting/pagination (FR-C/W/A/B)."""
import base64
from dataclasses import asdict, dataclass
import hashlib
import json
import unicodedata
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select, update

from app.domain.briefing_records import BriefingRunRecord
from app.domain.catalog import BriefingSubjectRecord, SecurityRecord
from app.domain.models import WatchlistSubscription
from app.repositories.catalog import CatalogConflict, SecurityCatalogReader


def normalize(text):
    return "".join(unicodedata.normalize("NFKC", text).casefold().split())


@dataclass
class SearchCandidate:
    key: str
    symbol: str
    name: str
    country: str
    status: str
    security_id: str | None = None
    subscription_id: int | None = None
    aliases: tuple = ()
    selectable: bool = True
    note: str = ""
    source_date: str | None = None


class CatalogScope:
    def __init__(self, db, reader): self.db, self.reader = db, reader

    def candidates(self, owner):
        metadata = {c: self.reader.metadata(c) for c in ("KR", "US")}
        return [SearchCandidate(r.id, r.symbol, r.name, r.country, r.status, r.id,
                    aliases=tuple(r.aliases), selectable=r.status == "active" and metadata[r.country]["state"] == "READY",
                    note=r.exchange + " · " + ("우선주" if r.kind == "preferred" else "보통주"),
                    source_date=r.source_date.isoformat())
                for r in self.db.scalars(select(SecurityRecord))]


class WatchlistScope:
    def __init__(self, db, reader): self.db, self.reader = db, reader

    def candidates(self, owner):
        rows = self.db.execute(select(WatchlistSubscription, SecurityRecord).outerjoin(SecurityRecord,
            WatchlistSubscription.security_id == SecurityRecord.id).where(
                WatchlistSubscription.owner_id == owner, WatchlistSubscription.ended_at.is_(None)))
        result = []
        for subscription, security in rows:
            country = security.country if security else ("KR" if subscription.symbol.endswith((".KS", ".KQ")) else "US")
            result.append(SearchCandidate(str(subscription.id), subscription.symbol,
                security.name if security else subscription.symbol, country, security.status if security else "unknown",
                security.id if security else None, subscription.id, tuple(security.aliases) if security else (),
                bool(security and security.status == "active" and security.symbol == subscription.symbol and
                     self.reader.metadata(country)["state"] == "READY"),
                "내 관심종목" if security else "종목 연결 확인 필요 — 삭제 후 목록에서 다시 등록",
                security.source_date.isoformat() if security else None))
        return result


class BriefingScope:
    def __init__(self, db, reader): self.db, self.reader = db, reader

    def candidates(self, owner):
        rows = self.db.execute(select(BriefingSubjectRecord, BriefingRunRecord).join(BriefingRunRecord).where(
            BriefingRunRecord.owner_id == owner, BriefingRunRecord.status.in_(["completed", "partial"])))
        grouped = {}
        for subject, run in rows:
            key = subject.security_id or "snapshot:" + subject.id
            if key not in grouped:
                grouped[key] = SearchCandidate(key, subject.symbol, subject.name, run.market, "historical",
                    subject.security_id, note="과거 저장 기록" if subject.security_id else f"{run.trade_date} 기록 · 현재 종목과 연결 미확인")
        return list(grouped.values())


class SecuritySelectionService:
    def __init__(self, db, reader=None):
        self.db = db
        self.reader = reader or SecurityCatalogReader(db)
        self.scopes = {"catalog": CatalogScope(db, self.reader), "watchlist": WatchlistScope(db, self.reader),
                       "briefings": BriefingScope(db, self.reader)}

    def search(self, owner, scope, q="", sort="relevance", country=None, limit=30, cursor=None):
        candidates = self.scopes[scope].candidates(owner)
        query = normalize(q).lstrip("@")
        def rank(row):
            values = [normalize(v) for v in (row.symbol, row.symbol.split(".")[0], row.name, *row.aliases)]
            if not query: return 0
            if query in values: return 0
            if any(v.startswith(query) for v in values): return 1
            if any(query in v for v in values): return 2
            return 3
        rows = [r for r in candidates if (not country or r.country == country) and rank(r) < 3]
        rows.sort(key=lambda r: r.key)
        if sort == "name_desc":
            rows.sort(key=lambda r: (normalize(r.name), r.symbol), reverse=True)
        elif sort == "name_asc":
            rows.sort(key=lambda r: (normalize(r.name), r.symbol))
        elif sort == "code_asc":
            rows.sort(key=lambda r: (r.symbol, normalize(r.name)))
        else:
            rows.sort(key=lambda r: (rank(r), normalize(r.name), r.symbol))
        snapshot = hashlib.sha256(json.dumps([owner, scope, query, sort, country, limit,
            [asdict(r) for r in rows]], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        offset = 0
        if cursor:
            try:
                supplied, offset = json.loads(base64.urlsafe_b64decode(cursor.encode()))
                if supplied != snapshot or type(offset) is not int or not 0 <= offset <= len(rows):
                    raise ValueError()
            except Exception as exc:
                raise CatalogConflict("검색 결과가 바뀌었습니다. 처음부터 다시 조회하세요.") from exc
        end = offset + limit
        next_cursor = base64.urlsafe_b64encode(json.dumps([snapshot, end]).encode()).decode() if end < len(rows) else None
        return {"items": [asdict(r) for r in rows[offset:end]], "total": len(rows), "next_cursor": next_cursor,
                "catalog": [self.reader.metadata(c) for c in ([country] if country else ["KR", "US"])]}

    def subscription(self, owner, key, symbol, *, lock=False):
        query = select(WatchlistSubscription).where(WatchlistSubscription.owner_id == owner,
            WatchlistSubscription.ended_at.is_(None), WatchlistSubscription.symbol == symbol)
        if key is not None: query = query.where(WatchlistSubscription.id == key)
        row = self.db.scalar(query.execution_options(populate_existing=True))
        if not row:
            raise LookupError("선택한 관심종목이 삭제되거나 변경됐습니다.")
        if not row.security_id:
            raise CatalogConflict("기존 종목 연결을 확인해야 합니다. 목록에서 다시 등록하세요.")
        self.reader.require_active(row.security_id, symbol, lock=lock)
        return row


def index_briefing_subjects(db, run):
    """Historical unresolved symbols stay per-run snapshots; never map using today's ticker."""
    existing = set(db.scalars(select(BriefingSubjectRecord.symbol).where(BriefingSubjectRecord.run_id == run.id)))
    for symbol in run.context.get("symbols", []):
        if symbol in existing: continue
        ref = run.context.get("security_refs", {}).get(symbol, {})
        security_id = ref.get("id")
        if security_id and db.get(SecurityRecord, security_id) is None: security_id = None
        db.add(BriefingSubjectRecord(id=str(uuid5(NAMESPACE_URL, f"briefing-subject:{run.id}:{symbol}")),
            run_id=run.id, security_id=security_id, symbol=symbol, name=ref.get("name") or symbol))


def briefing_subject_query(db, owner, key):
    subjects = select(BriefingSubjectRecord.run_id).join(BriefingRunRecord).where(BriefingRunRecord.owner_id == owner)
    if key.startswith("snapshot:"):
        subjects = subjects.where(BriefingSubjectRecord.id == key.removeprefix("snapshot:"))
    else:
        subjects = subjects.where(BriefingSubjectRecord.security_id == key)
    return select(BriefingRunRecord).where(BriefingRunRecord.owner_id == owner,
        BriefingRunRecord.status.in_(["completed", "partial"]), BriefingRunRecord.id.in_(subjects)).order_by(
            BriefingRunRecord.created_at.desc(), BriefingRunRecord.id.desc())
