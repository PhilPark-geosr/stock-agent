from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("symbol", name="uq_watchlist_items_symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    symbol: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    symbol: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    data_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    overall_judgment: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    key_reasons: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    risk_factors: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    support_levels: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    should_alert: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    triggered_alerts: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    alert_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    alert_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class CustomAlertConditionRecord(Base):
    __tablename__ = "custom_alert_conditions"
    __table_args__ = (UniqueConstraint("symbol", "user_rule", name="uq_custom_alert_conditions_symbol_rule"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    symbol: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    user_rule: Mapped[str] = mapped_column(Text, nullable=False)
    validation_summary: Mapped[str] = mapped_column(Text, nullable=False)
    required_tools: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    related_symbols: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    news_symbols: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
