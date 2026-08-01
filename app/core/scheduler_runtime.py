"""Background scheduler runtime wiring."""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

from sqlalchemy.orm import Session, sessionmaker

from app.core.container import build_analysis_service, build_briefing_schedule_service
from app.core.scheduler_config import scheduler_settings
from app.services.scheduler import run_scheduled_batch

logger = logging.getLogger(__name__)


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
                result = run_scheduled_batch(build_analysis_service(db))
                if result.ran:
                    logger.info(
                        "Scheduled batch done: analyzed=%s failed=%s",
                        result.symbols_analyzed,
                        result.symbols_failed,
                    )
                elif result.skipped_reason:
                    logger.debug("Scheduled batch skipped: %s", result.skipped_reason)

                briefing_result = build_briefing_schedule_service(db).run_due()
                if briefing_result.generated_ids:
                    logger.info(
                        "Scheduled briefings done: ids=%s",
                        briefing_result.generated_ids,
                    )
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
