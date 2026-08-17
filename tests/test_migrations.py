from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from app.core.migrations import migrate_database


def _url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def test_empty_database_is_upgraded_to_baseline(tmp_path: Path) -> None:
    url = _url(tmp_path / "empty.db")

    migrate_database(url)

    tables = set(inspect(create_engine(url)).get_table_names())
    assert {"alembic_version", "watchlist_items", "analysis_results", "custom_alert_conditions"} <= tables


def test_known_legacy_database_is_stamped_without_losing_rows(tmp_path: Path) -> None:
    url = _url(tmp_path / "legacy.db")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE watchlist_items (id INTEGER PRIMARY KEY, symbol VARCHAR(24) NOT NULL, created_at DATETIME NOT NULL)"))
        connection.execute(text("CREATE UNIQUE INDEX uq_watchlist_items_symbol ON watchlist_items(symbol)"))
        connection.execute(text("CREATE TABLE analysis_results (id INTEGER PRIMARY KEY, symbol VARCHAR(24) NOT NULL, analyzed_at DATETIME NOT NULL, data_timestamp DATETIME, overall_judgment VARCHAR(64) NOT NULL, summary TEXT NOT NULL, key_reasons JSON NOT NULL, risk_factors JSON NOT NULL, support_levels JSON NOT NULL, should_alert BOOLEAN NOT NULL, triggered_alerts JSON NOT NULL, alert_reason TEXT, alert_sent_at DATETIME, raw_result JSON)"))
        connection.execute(text("CREATE TABLE custom_alert_conditions (id INTEGER PRIMARY KEY, symbol VARCHAR(24) NOT NULL, name VARCHAR(120) NOT NULL, user_rule TEXT NOT NULL, normalized_rule TEXT, validation_summary TEXT NOT NULL, required_tools JSON NOT NULL, related_symbols JSON NOT NULL, news_symbols JSON NOT NULL, enabled BOOLEAN NOT NULL, created_at DATETIME NOT NULL)"))
        connection.execute(text("INSERT INTO watchlist_items(id, symbol, created_at) VALUES (1, 'AAPL', '2026-01-01')"))

    migrate_database(url)

    with engine.connect() as connection:
        assert connection.scalar(text("SELECT symbol FROM watchlist_items WHERE id=1")) == "AAPL"
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0004_watchlist_subscriptions"
        columns = {column["name"] for column in inspect(engine).get_columns("watchlist_items")}
        assert {"user_account_id", "ended_at"} <= columns
    assert "user_accounts" in inspect(engine).get_table_names()


def test_unknown_existing_schema_is_not_auto_stamped(tmp_path: Path) -> None:
    url = _url(tmp_path / "unknown.db")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)"))

    with pytest.raises(RuntimeError, match="unknown database schema"):
        migrate_database(url)
