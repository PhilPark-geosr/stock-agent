from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

BASELINE_REVISION = "0001_baseline"
LEGACY_TABLES = {"watchlist_items", "analysis_results", "custom_alert_conditions"}
LEGACY_REQUIRED_COLUMNS = {
    "watchlist_items": {"id", "symbol", "created_at"},
    "analysis_results": {"id", "symbol", "analyzed_at", "alert_sent_at", "raw_result"},
    "custom_alert_conditions": {"id", "symbol", "user_rule", "normalized_rule", "created_at"},
}


def _config(database_url: str) -> Config:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def migrate_database(database_url: str) -> None:
    engine = create_engine(database_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    config = _config(database_url)

    if not tables:
        command.upgrade(config, "head")
        return
    if "alembic_version" in tables:
        command.upgrade(config, "head")
        return
    if tables != LEGACY_TABLES:
        raise RuntimeError("unknown database schema; refusing to stamp it")
    for table, required in LEGACY_REQUIRED_COLUMNS.items():
        actual = {column["name"] for column in inspector.get_columns(table)}
        if not required <= actual:
            raise RuntimeError("unknown database schema; refusing to stamp it")
    command.stamp(config, BASELINE_REVISION)
    command.upgrade(config, "head")
