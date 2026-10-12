from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
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
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0007_investment_briefings"
        columns = {column["name"] for column in inspect(engine).get_columns("watchlist_items")}
        assert {"user_account_id", "ended_at"} <= columns
        condition_columns = {
            column["name"] for column in inspect(engine).get_columns("custom_alert_conditions")
        }
        assert {"watchlist_subscription_id", "ended_at"} <= condition_columns
        analysis_columns = {
            column["name"] for column in inspect(engine).get_columns("analysis_results")
        }
        assert {"shared_safe", "normalized_judgment", "briefing_type", "trading_date"} <= analysis_columns
        assert "alert_sent_at" in analysis_columns
    tables = set(inspect(engine).get_table_names())
    assert {"user_accounts", "investment_briefings", "briefing_items", "briefing_scopes"} <= tables


def test_unknown_existing_schema_is_not_auto_stamped(tmp_path: Path) -> None:
    url = _url(tmp_path / "unknown.db")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)"))

    with pytest.raises(RuntimeError, match="unknown database schema"):
        migrate_database(url)


def test_briefing_schema_can_be_rolled_back_and_reapplied(tmp_path: Path) -> None:
    url = _url(tmp_path / "round-trip.db")
    migrate_database(url)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)

    command.downgrade(config, "0006_shared_analysis")
    downgraded_tables = set(inspect(create_engine(url)).get_table_names())
    assert "investment_briefings" not in downgraded_tables

    command.upgrade(config, "head")
    upgraded_tables = set(inspect(create_engine(url)).get_table_names())
    assert {"investment_briefings", "briefing_items", "briefing_failures"} <= upgraded_tables
