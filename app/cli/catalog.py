"""One due refresh without starting analysis or notification jobs."""
import json
import argparse
from sqlalchemy import select
from app.core.database import SessionLocal, init_db
from app.core.catalog_runtime import run_catalog_tick
from app.domain.catalog import CatalogAttemptRecord
from app.repositories.catalog import SecurityCatalogReader


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true", help="현재 게시 상태와 최근 실행 이력만 조회")
    args = parser.parse_args()
    init_db()
    if args.status:
        with SessionLocal() as db:
            reader = SecurityCatalogReader(db)
            attempts = db.scalars(select(CatalogAttemptRecord).order_by(CatalogAttemptRecord.started_at.desc()).limit(20))
            print(json.dumps({"catalog": [reader.metadata(c) for c in ("KR", "US")],
                "attempts": [{"country": r.country, "started_at": r.started_at, "finished_at": r.finished_at,
                              "status": r.status, "error": r.error, "version": r.version} for r in attempts]},
                default=str, ensure_ascii=False))
        return
    result = run_catalog_tick(SessionLocal)
    print(json.dumps(result, ensure_ascii=False))
    if any(value not in ("not_due",) and not isinstance(value, int) for value in result.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
