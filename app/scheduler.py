"""Background scheduler for hourly watchlist analysis."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session, sessionmaker

from app.scheduler_config import scheduler_settings
from app.services import AnalysisService, ScheduledBatchResult, build_analysis_service
from app.trading_window import is_market_hours

logger = logging.getLogger(__name__)


@dataclass
class SchedulerRunSummary:
    ran: bool
    symbols_analyzed: list[str] = field(default_factory=list)
    symbols_failed: list[str] = field(default_factory=list)
    skipped_reason: str | None = None


def run_scheduled_batch(
    db: Session,
    *,
    analysis_service: AnalysisService | None = None,
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

    service = analysis_service or build_analysis_service(db)
    return service.run_scheduled_batch(now=current)


async def scheduler_loop(
    session_factory: sessionmaker[Session],
    *,
    stop_event: asyncio.Event,
    sleep: Callable[[float], asyncio.Future[None]] = asyncio.sleep,
) -> None:
    settings = scheduler_settings()
    if not settings["enabled"]:
        logger.info("Scheduler disabled (SCHEDULER_ENABLED=false)")
        return

    interval_seconds = int(settings["interval_minutes"]) * 60
    logger.info(
        "Scheduler started: every %s min, market %s:00-%s:00 %s",
        settings["interval_minutes"],
        settings["market_start_hour"],
        settings["market_end_hour"],
        settings["timezone"],
    )

    while not stop_event.is_set():
        try:
            await sleep(interval_seconds)
            if stop_event.is_set():
                break

            db = session_factory()
            try:
                result = run_scheduled_batch(db)
                if result.ran:
                    logger.info(
                        "Scheduled batch done: analyzed=%s failed=%s",
                        result.symbols_analyzed,
                        result.symbols_failed,
                    )
                elif result.skipped_reason:
                    logger.debug("Scheduled batch skipped: %s", result.skipped_reason)
            finally:
                db.close()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Scheduled batch failed")

    logger.info("Scheduler stopped")


def start_scheduler(
    session_factory: sessionmaker[Session],
) -> tuple[asyncio.Task[None], asyncio.Event]:
    stop_event = asyncio.Event()
    task = asyncio.create_task(scheduler_loop(session_factory, stop_event=stop_event))
    return task, stop_event
