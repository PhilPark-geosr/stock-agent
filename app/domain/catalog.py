"""Catalog contracts. FR-U01..05; search consumes published data only."""
from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Date, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class CatalogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identity: str = Field(min_length=1, max_length=160)
    symbol: str = Field(min_length=1, max_length=24)
    name: str = Field(min_length=1, max_length=255)
    exchange: str
    kind: Literal["common", "preferred"]
    listed_on: date
    delisted_on: date | None = None
    aliases: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def dates(self):
        if self.delisted_on and self.delisted_on < self.listed_on:
            raise ValueError("delisting precedes listing")
        return self


class CatalogBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    country: Literal["KR", "US"]
    source: str
    source_date: date
    fetched_at: datetime
    entries: list[CatalogEntry] = Field(min_length=1)
    evidence: str


class SecurityRecord(Base):
    __tablename__ = "securities"
    __table_args__ = (UniqueConstraint("country", "source", "source_identity", name="uq_security_source"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    country: Mapped[str] = mapped_column(String(2), index=True)
    source: Mapped[str] = mapped_column(String(50))
    source_identity: Mapped[str] = mapped_column(String(160))
    symbol: Mapped[str] = mapped_column(String(24), index=True)
    name: Mapped[str] = mapped_column(String(255))
    exchange: Mapped[str] = mapped_column(String(30))
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    listed_on: Mapped[date] = mapped_column(Date)
    delisted_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    source_date: Mapped[date] = mapped_column(Date)
    version: Mapped[int] = mapped_column(Integer)


class CatalogStateRecord(Base):
    __tablename__ = "catalog_states"
    country: Mapped[str] = mapped_column(String(2), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(100), nullable=True)


class CatalogRevisionRecord(Base):
    __tablename__ = "catalog_revisions"
    __table_args__ = (UniqueConstraint("country", "version", name="uq_catalog_revision"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    country: Mapped[str] = mapped_column(String(2))
    version: Mapped[int] = mapped_column(Integer)
    source_date: Mapped[date] = mapped_column(Date)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    evidence: Mapped[str] = mapped_column(String(500))
    snapshot: Mapped[dict] = mapped_column(JSON)


class CatalogAttemptRecord(Base):
    __tablename__ = "catalog_attempts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    country: Mapped[str] = mapped_column(String(2), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    error: Mapped[str | None] = mapped_column(String(100), nullable=True)
    version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class BriefingSubjectRecord(Base):
    __tablename__ = "briefing_subjects"
    __table_args__ = (UniqueConstraint("run_id", "symbol", name="uq_briefing_subject"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("briefing_runs.id"), index=True)
    security_id: Mapped[str | None] = mapped_column(ForeignKey("securities.id"), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(24))
    name: Mapped[str] = mapped_column(String(255))


class CatalogDelistingRecord(Base):
    __tablename__ = "catalog_delisting_evidence"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    security_id: Mapped[str] = mapped_column(ForeignKey("securities.id"), index=True)
    effective_on: Mapped[date] = mapped_column(Date)
    source_url: Mapped[str] = mapped_column(String(1000))
    reviewed_by: Mapped[str] = mapped_column(String(120))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
