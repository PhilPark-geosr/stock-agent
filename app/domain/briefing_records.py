"""Persistence for immutable briefing inputs/results and independent deliveries."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BriefingPreferenceRecord(Base):
    __tablename__ = "briefing_preferences"
    __table_args__ = (UniqueConstraint("owner_id", "market"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    market: Mapped[str] = mapped_column(String(8))
    n: Mapped[int | None] = mapped_column(Integer, nullable=True)
    symbols: Mapped[list | None] = mapped_column(JSON, nullable=True)
    pre_market_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    post_market_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    kakao_enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class PromptVersionRecord(Base):
    __tablename__ = "briefing_prompt_versions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PromptActivationRecord(Base):
    __tablename__ = "briefing_prompt_activations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("briefing_prompt_versions.id"))
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BriefingRunRecord(Base):
    __tablename__ = "briefing_runs"
    __table_args__ = (UniqueConstraint("owner_id", "request_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    request_key: Mapped[str] = mapped_column(String(180))
    request_data: Mapped[dict] = mapped_column(JSON)
    market: Mapped[str] = mapped_column(String(8))
    purpose: Mapped[str] = mapped_column(String(24))
    trade_date: Mapped[str] = mapped_column(String(10), index=True)
    context: Mapped[dict] = mapped_column(JSON)
    prompt_id: Mapped[str] = mapped_column(ForeignKey("briefing_prompt_versions.id"))
    previous_id: Mapped[str | None] = mapped_column(ForeignKey("briefing_runs.id"), nullable=True)
    original_id: Mapped[str | None] = mapped_column(ForeignKey("briefing_runs.id"), nullable=True)
    snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="preparing")
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BriefingDeliveryRecord(Base):
    __tablename__ = "briefing_deliveries"
    __table_args__ = (UniqueConstraint("run_id", "channel"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("briefing_runs.id"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    channel: Mapped[str] = mapped_column(String(20), default="kakao")
    connection_id: Mapped[str | None] = mapped_column(ForeignKey("notification_connections.id"), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[list] = mapped_column(JSON, default=list)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    claim_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
