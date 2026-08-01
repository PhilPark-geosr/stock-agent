import os
import logging
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.settings import load_environment

logger = logging.getLogger(__name__)

load_environment()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./stock_agent.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from sqlalchemy import inspect, text

    from app.domain import models  # noqa: F401

    logger.info("Database init url=%s", _safe_database_url(DATABASE_URL))
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    if inspector.has_table("analysis_results"):
        columns = {column["name"] for column in inspector.get_columns("analysis_results")}
        if "alert_sent_at" not in columns:
            with engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE analysis_results ADD COLUMN alert_sent_at DATETIME")
                )
        additions = {
            "user_id": "VARCHAR(64) NOT NULL DEFAULT 'default'",
            "normalized_judgment": "VARCHAR(24) NOT NULL DEFAULT 'UNKNOWN'",
            "briefing_type": "VARCHAR(24)",
            "trading_date": "DATE",
        }
        for column_name, definition in additions.items():
            if column_name not in columns:
                with engine.begin() as connection:
                    connection.execute(
                        text(f"ALTER TABLE analysis_results ADD COLUMN {column_name} {definition}")
                    )
    if inspector.has_table("watchlist_items"):
        columns = {column["name"] for column in inspector.get_columns("watchlist_items")}
        if "user_id" not in columns:
            with engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE watchlist_items ADD COLUMN user_id VARCHAR(64) NOT NULL DEFAULT 'default'")
                )
    if inspector.has_table("custom_alert_conditions"):
        columns = {column["name"] for column in inspector.get_columns("custom_alert_conditions")}
        if "normalized_rule" not in columns:
            with engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE custom_alert_conditions ADD COLUMN normalized_rule TEXT")
                )
        if "user_id" not in columns:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE custom_alert_conditions "
                        "ADD COLUMN user_id VARCHAR(64) NOT NULL DEFAULT 'default'"
                    )
                )
    inspector = inspect(engine)
    if inspector.has_table("investment_briefings"):
        columns = {column["name"] for column in inspector.get_columns("investment_briefings")}
        if "generation_started_at" not in columns:
            with engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE investment_briefings ADD COLUMN generation_started_at DATETIME")
                )

    if engine.dialect.name == "sqlite":
        _upgrade_sqlite_user_unique_constraints()


def _upgrade_sqlite_user_unique_constraints() -> None:
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    watchlist_constraints = inspector.get_unique_constraints("watchlist_items")
    if not any(set(item.get("column_names") or []) == {"user_id", "symbol"} for item in watchlist_constraints):
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS watchlist_items_new"))
            connection.execute(
                text(
                    "CREATE TABLE watchlist_items_new ("
                    "id INTEGER PRIMARY KEY, "
                    "user_id VARCHAR(64) NOT NULL DEFAULT 'default', "
                    "symbol VARCHAR(24) NOT NULL, "
                    "created_at DATETIME NOT NULL, "
                    "CONSTRAINT uq_watchlist_items_user_symbol UNIQUE (user_id, symbol))"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO watchlist_items_new (id, user_id, symbol, created_at) "
                    "SELECT id, user_id, symbol, created_at FROM watchlist_items"
                )
            )
            connection.execute(text("DROP TABLE watchlist_items"))
            connection.execute(text("ALTER TABLE watchlist_items_new RENAME TO watchlist_items"))
            connection.execute(text("CREATE INDEX ix_watchlist_items_id ON watchlist_items (id)"))
            connection.execute(text("CREATE INDEX ix_watchlist_items_user_id ON watchlist_items (user_id)"))
            connection.execute(text("CREATE INDEX ix_watchlist_items_symbol ON watchlist_items (symbol)"))

    inspector = inspect(engine)
    alert_constraints = inspector.get_unique_constraints("custom_alert_conditions")
    expected = {"user_id", "symbol", "user_rule"}
    if not any(set(item.get("column_names") or []) == expected for item in alert_constraints):
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS custom_alert_conditions_new"))
            connection.execute(
                text(
                    "CREATE TABLE custom_alert_conditions_new ("
                    "id INTEGER PRIMARY KEY, "
                    "user_id VARCHAR(64) NOT NULL DEFAULT 'default', "
                    "symbol VARCHAR(24) NOT NULL, "
                    "name VARCHAR(120) NOT NULL, "
                    "user_rule TEXT NOT NULL, "
                    "normalized_rule TEXT, "
                    "validation_summary TEXT NOT NULL, "
                    "required_tools JSON NOT NULL, "
                    "related_symbols JSON NOT NULL, "
                    "news_symbols JSON NOT NULL, "
                    "enabled BOOLEAN NOT NULL, "
                    "created_at DATETIME NOT NULL, "
                    "CONSTRAINT uq_custom_alert_conditions_user_symbol_rule "
                    "UNIQUE (user_id, symbol, user_rule))"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO custom_alert_conditions_new "
                    "(id, user_id, symbol, name, user_rule, normalized_rule, validation_summary, "
                    "required_tools, related_symbols, news_symbols, enabled, created_at) "
                    "SELECT id, user_id, symbol, name, user_rule, normalized_rule, validation_summary, "
                    "required_tools, related_symbols, news_symbols, enabled, created_at "
                    "FROM custom_alert_conditions"
                )
            )
            connection.execute(text("DROP TABLE custom_alert_conditions"))
            connection.execute(
                text("ALTER TABLE custom_alert_conditions_new RENAME TO custom_alert_conditions")
            )
            connection.execute(
                text("CREATE INDEX ix_custom_alert_conditions_id ON custom_alert_conditions (id)")
            )
            connection.execute(
                text(
                    "CREATE INDEX ix_custom_alert_conditions_user_id "
                    "ON custom_alert_conditions (user_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX ix_custom_alert_conditions_symbol "
                    "ON custom_alert_conditions (symbol)"
                )
            )


def _safe_database_url(url: str) -> str:
    if "@" not in url:
        return url
    scheme, rest = url.split("://", 1) if "://" in url else ("", url)
    credentials, host = rest.rsplit("@", 1)
    user = credentials.split(":", 1)[0]
    prefix = f"{scheme}://" if scheme else ""
    return f"{prefix}{user}:***@{host}"
