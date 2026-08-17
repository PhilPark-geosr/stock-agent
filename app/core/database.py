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
    logger.info("Database init url=%s", _safe_database_url(DATABASE_URL))
    from app.core.migrations import migrate_database

    migrate_database(DATABASE_URL)


def _safe_database_url(url: str) -> str:
    if "@" not in url:
        return url
    scheme, rest = url.split("://", 1) if "://" in url else ("", url)
    credentials, host = rest.rsplit("@", 1)
    user = credentials.split(":", 1)[0]
    prefix = f"{scheme}://" if scheme else ""
    return f"{prefix}{user}:***@{host}"
