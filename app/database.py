import os
import logging
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.settings import load_environment

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

    from app import models  # noqa: F401

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
    if inspector.has_table("custom_alert_conditions"):
        columns = {column["name"] for column in inspector.get_columns("custom_alert_conditions")}
        if "normalized_rule" not in columns:
            with engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE custom_alert_conditions ADD COLUMN normalized_rule TEXT")
                )


def _safe_database_url(url: str) -> str:
    if "@" not in url:
        return url
    scheme, rest = url.split("://", 1) if "://" in url else ("", url)
    credentials, host = rest.rsplit("@", 1)
    user = credentials.split(":", 1)[0]
    prefix = f"{scheme}://" if scheme else ""
    return f"{prefix}{user}:***@{host}"
