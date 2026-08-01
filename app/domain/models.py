from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("user_id", "symbol", name="uq_watchlist_items_user_symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(64), default="default", nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(64), default="default", nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    normalized_judgment: Mapped[str] = mapped_column(String(24), default="UNKNOWN", nullable=False, index=True)
    briefing_type: Mapped[str | None] = mapped_column(String(24), nullable=True, index=True)
    trading_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
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
    __table_args__ = (
        UniqueConstraint(
            "user_id", "symbol", "user_rule", name="uq_custom_alert_conditions_user_symbol_rule"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(64), default="default", nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    user_rule: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_rule: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_summary: Mapped[str] = mapped_column(Text, nullable=False)
    required_tools: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    related_symbols: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    news_symbols: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class InvestmentBriefing(Base):
    __tablename__ = "investment_briefings"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "exchange",
            "briefing_type",
            "trading_date",
            name="uq_investment_briefing_run",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    briefing_type: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    trading_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), default="GENERATING", nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    generation_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    resolved_symbols: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class BriefingScope(Base):
    __tablename__ = "briefing_scopes"
    __table_args__ = (
        UniqueConstraint("briefing_id", "source_type", name="uq_briefing_scope_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    briefing_id: Mapped[int] = mapped_column(
        ForeignKey("investment_briefings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(String(24), nullable=False)
    source_value: Mapped[str | None] = mapped_column(String(120), nullable=True)
    resolved_symbols: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)


class BriefingItem(Base):
    __tablename__ = "briefing_items"
    __table_args__ = (
        UniqueConstraint("briefing_id", "symbol", name="uq_briefing_item_symbol"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    briefing_id: Mapped[int] = mapped_column(
        ForeignKey("investment_briefings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    current_analysis_id: Mapped[int] = mapped_column(ForeignKey("analysis_results.id"), nullable=False)
    previous_analysis_id: Mapped[int | None] = mapped_column(ForeignKey("analysis_results.id"), nullable=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    current_judgment: Mapped[str] = mapped_column(String(24), nullable=False)
    previous_judgment: Mapped[str | None] = mapped_column(String(24), nullable=True)
    judgment_changed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    comparison_status: Mapped[str] = mapped_column(String(24), nullable=False)
    judgment_distance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    data_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class BriefingDelivery(Base):
    __tablename__ = "briefing_deliveries"
    __table_args__ = (
        UniqueConstraint("briefing_id", "channel", name="uq_briefing_delivery_channel"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    briefing_id: Mapped[int] = mapped_column(
        ForeignKey("investment_briefings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="PENDING", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class BriefingFailure(Base):
    __tablename__ = "briefing_failures"
    __table_args__ = (
        UniqueConstraint("briefing_id", "symbol", name="uq_briefing_failure_symbol"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    briefing_id: Mapped[int] = mapped_column(
        ForeignKey("investment_briefings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    error_code: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    retryable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
