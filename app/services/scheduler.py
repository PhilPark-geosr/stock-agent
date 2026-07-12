"""Background scheduler for hourly watchlist analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.core.scheduler_config import scheduler_settings
from app.core.trading_window import is_market_hours
from app.services import AnalysisProvider, ScheduledBatchResult


@dataclass
class SchedulerRunSummary:
    ran: bool
    symbols_analyzed: list[str] = field(default_factory=list)
    symbols_failed: list[str] = field(default_factory=list)
    skipped_reason: str | None = None


def run_scheduled_batch(
    analysis_service: AnalysisProvider,
    *,
    ignore_market_hours: bool = False,
    now: datetime | None = None,
) -> ScheduledBatchResult:
    settings = scheduler_settings()
    current = now or datetime.now(timezone.utc)
    if not ignore_market_hours and not is_market_hours(
        current,
        start_hour=int(settings["market_start_hour"]),
        end_hour=int(settings["market_end_hour"]),
        tz_name=str(settings["timezone"]),
    ):
        return ScheduledBatchResult(
            ran=False,
            skipped_reason="outside_market_hours",
        )

    return analysis_service.run_scheduled_batch(now=current)
