"""Inspect catalog status or run one due refresh without notification jobs."""
import argparse
import json
from pathlib import Path

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, engine, init_db
from app.core.catalog_runtime import run_catalog_tick
from app.domain.catalog import CatalogAttemptRecord, CatalogStateRecord
from app.repositories.catalog import SecurityCatalogReader


def read_status(bind):
    """Read published state without migrations, refreshes, or creating a SQLite file."""
    status_bind = bind
    url = bind.url
    if url.get_backend_name() == "sqlite" and url.database not in (None, "", ":memory:"):
        database = url.database
        if not database.startswith("file:"):
            database = Path(database).resolve().as_uri()
        status_bind = create_engine(url.set(database=database, query={**url.query, "mode": "ro", "uri": "true"}))
    try:
        required = {CatalogStateRecord.__tablename__, CatalogAttemptRecord.__tablename__}
        missing = sorted(required - set(inspect(status_bind).get_table_names()))
        if missing:
            return {"error": "catalog_schema_missing", "missing_tables": missing,
                    "message": "스키마를 변경하지 않았습니다. DB 백업과 이관 계획을 확인하세요."}
        with Session(status_bind) as db:
            reader = SecurityCatalogReader(db)
            attempts = db.scalars(select(CatalogAttemptRecord).order_by(CatalogAttemptRecord.started_at.desc()).limit(20))
            return {"catalog": [reader.metadata(c) for c in ("KR", "US")],
                    "attempts": [{"country": r.country, "started_at": r.started_at, "finished_at": r.finished_at,
                                  "status": r.status, "error": r.error, "version": r.version} for r in attempts]}
    except SQLAlchemyError:
        # Do not print connection URLs, credentials, or driver exception details.
        return {"error": "catalog_status_unavailable",
                "message": "DB 연결·파일 존재 여부와 스키마를 확인하세요. 갱신과 이관은 실행하지 않았습니다."}
    finally:
        if status_bind is not bind:
            status_bind.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true", help="DB 변경 없이 현재 게시 상태와 최근 실행 이력만 조회")
    args = parser.parse_args()
    if args.status:
        result = read_status(engine)
        print(json.dumps(result, default=str, ensure_ascii=False))
        if "error" in result:
            raise SystemExit(1)
        return
    init_db()
    result = run_catalog_tick(SessionLocal)
    print(json.dumps(result, ensure_ascii=False))
    if any(value not in ("not_due",) and not isinstance(value, int) for value in result.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
