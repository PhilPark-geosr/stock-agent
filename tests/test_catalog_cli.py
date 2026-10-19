import json
import sys
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from app.cli import catalog
from app.domain.catalog import CatalogAttemptRecord, CatalogStateRecord


def file_engine(path):
    return create_engine(URL.create("sqlite", database=str(path)))


def run_status(monkeypatch, bind):
    def forbidden(*args, **kwargs):
        pytest.fail("status must not migrate the DB or contact catalog providers")
    monkeypatch.setattr(catalog, "engine", bind)
    monkeypatch.setattr(catalog, "init_db", forbidden)
    monkeypatch.setattr(catalog, "run_catalog_tick", forbidden)
    monkeypatch.setattr(sys, "argv", ["catalog", "--status"])
    catalog.main()


def test_status_does_not_create_missing_database(tmp_path, monkeypatch, capsys):
    path = tmp_path / "missing.db"
    bind = file_engine(path)
    try:
        with pytest.raises(SystemExit) as exc:
            run_status(monkeypatch, bind)
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().out)["error"] == "catalog_status_unavailable"
        assert not path.exists()
    finally:
        bind.dispose()


def test_status_does_not_migrate_existing_database(tmp_path, monkeypatch, capsys):
    path = tmp_path / "legacy.db"
    bind = file_engine(path)
    with bind.begin() as connection:
        connection.execute(text("CREATE TABLE legacy_record (value TEXT)"))
        connection.execute(text("INSERT INTO legacy_record VALUES ('keep me')"))
    bind.dispose()
    before = path.read_bytes()
    try:
        with pytest.raises(SystemExit) as exc:
            run_status(monkeypatch, bind)
        assert exc.value.code == 1
        result = json.loads(capsys.readouterr().out)
        assert result["error"] == "catalog_schema_missing"
        assert result["missing_tables"] == ["catalog_attempts", "catalog_states"]
        assert path.read_bytes() == before
    finally:
        bind.dispose()


def test_status_reads_published_state_and_attempts_without_writing(tmp_path, monkeypatch, capsys):
    # Spaces, Unicode and URI-significant characters must survive SQLite URI conversion.
    path = tmp_path / "종목 상태 #1%.db"
    bind = file_engine(path)
    CatalogStateRecord.__table__.create(bind)
    CatalogAttemptRecord.__table__.create(bind)
    now = datetime.now(timezone.utc)
    with bind.begin() as connection:
        connection.execute(CatalogStateRecord.__table__.insert(), {
            "country": "KR", "version": 3, "source": "TEST", "source_date": now.date(),
            "fetched_at": now, "next_at": now, "failures": 0,
        })
        connection.execute(CatalogAttemptRecord.__table__.insert(), {
            "id": "attempt", "country": "KR", "started_at": now,
            "finished_at": now, "status": "success", "version": 3,
        })
    bind.dispose()
    before = path.read_bytes()
    try:
        run_status(monkeypatch, bind)
        result = json.loads(capsys.readouterr().out)
        assert [(r["country"], r["state"], r["version"]) for r in result["catalog"]] == [
            ("KR", "READY", 3), ("US", "UNAVAILABLE", 0)]
        assert result["attempts"][0]["version"] == 3
        assert path.read_bytes() == before
    finally:
        bind.dispose()
