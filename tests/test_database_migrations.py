from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core import database
from app.repositories import WatchlistRepository


def test_legacy_sqlite_watchlist_unique_constraint_becomes_user_scoped(monkeypatch):
    legacy_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with legacy_engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE watchlist_items ("
                "id INTEGER PRIMARY KEY, symbol VARCHAR(24) NOT NULL UNIQUE, "
                "created_at DATETIME NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE custom_alert_conditions ("
                "id INTEGER PRIMARY KEY, symbol VARCHAR(24) NOT NULL, name VARCHAR(120) NOT NULL, "
                "user_rule TEXT NOT NULL, validation_summary TEXT NOT NULL, required_tools JSON NOT NULL, "
                "related_symbols JSON NOT NULL, news_symbols JSON NOT NULL, enabled BOOLEAN NOT NULL, "
                "created_at DATETIME NOT NULL, UNIQUE(symbol, user_rule))"
            )
        )

    monkeypatch.setattr(database, "engine", legacy_engine)
    database.init_db()

    constraints = inspect(legacy_engine).get_unique_constraints("watchlist_items")
    assert any(
        set(constraint.get("column_names") or []) == {"user_id", "symbol"}
        for constraint in constraints
    )
    with Session(legacy_engine) as session:
        repository = WatchlistRepository(session)
        repository.add("MSFT", "alice")
        repository.add("MSFT", "bob")
        assert repository.list_user_ids() == ["alice", "bob"]

    legacy_engine.dispose()
