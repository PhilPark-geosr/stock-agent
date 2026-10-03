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
    assert {"alembic_version", "watchlist_items", "analysis_results", "custom_alert_conditions", "notification_connections", "notification_deliveries", "alert_evaluations"} <= tables
    delivery_columns = {
        column["name"] for column in inspect(create_engine(url)).get_columns("notification_deliveries")
    }
    assert "evaluation_id" in delivery_columns


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
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0010_beta_access_grants"
        columns = {column["name"] for column in inspect(engine).get_columns("watchlist_items")}
        assert {"user_account_id", "ended_at"} <= columns
        condition_columns = {
            column["name"] for column in inspect(engine).get_columns("custom_alert_conditions")
        }
        assert {"watchlist_subscription_id", "ended_at"} <= condition_columns
        analysis_columns = {
            column["name"] for column in inspect(engine).get_columns("analysis_results")
        }
        assert "shared_safe" in analysis_columns
        assert "alert_sent_at" not in analysis_columns
    assert "user_accounts" in inspect(engine).get_table_names()


def test_unknown_existing_schema_is_not_auto_stamped(tmp_path: Path) -> None:
    url = _url(tmp_path / "unknown.db")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)"))

    with pytest.raises(RuntimeError, match="unknown database schema"):
        migrate_database(url)


def test_previous_head_preserves_all_existing_rows(tmp_path: Path) -> None:
    from alembic import command
    from app.core.migrations import _config

    url = _url(tmp_path / 'previous.db')
    command.upgrade(_config(url), '0008_user_alert_evaluation')
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO user_accounts (id, login_provider, provider_subject_id, created_at) VALUES ('account', 'kakao', 'subject', '2026-09-21')"))
    from sqlalchemy.orm import Session
    from app.domain.models import AnalysisResult, NotificationConnectionRecord, NotificationDeliveryRecord

    with Session(engine) as db:
        db.add(AnalysisResult(id=1, symbol='AAPL', overall_judgment='neutral', summary='Preserve this analysis'))
        db.add(NotificationConnectionRecord(id='connection', owner_id='account', channel='kakao'))
        db.flush()
        db.add(NotificationDeliveryRecord(recipient_id='account', analysis_id=1,
                                         connection_id='connection', kind='default_alert',
                                         message='Preserve this notification', status='sent'))
        db.commit()
    with engine.connect() as connection:
        before = {name: connection.execute(text(f'SELECT * FROM {name}')).all() for name in inspect(engine).get_table_names() if name != 'alembic_version'}
    migrate_database(url)
    with engine.connect() as connection:
        for name, rows in before.items():
            assert connection.execute(text(f'SELECT * FROM {name}')).all() == rows
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == '0010_beta_access_grants'
    assert 'invitations' in inspect(engine).get_table_names()
    assert 'user_beta_access_grants' in inspect(engine).get_table_names()
    engine.dispose()
