import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.api.briefings import router as briefing_router
from app.core.briefing_runtime import briefing_loop
from app.core.database import SessionLocal, init_db
from app.core.scheduler_config import scheduler_settings
from app.core.scheduler_runtime import start_scheduler
from app.core.settings import load_environment

logging.basicConfig(level=logging.INFO)

load_environment()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    logger.info("Runtime user alert evaluation and delivery initialized")

    scheduler_task: asyncio.Task[None] | None = None
    stop_event: asyncio.Event | None = None
    if scheduler_settings()["enabled"]:
        scheduler_task, stop_event = start_scheduler(SessionLocal)

    briefing_task = None
    if os.getenv("BRIEFING_SCHEDULER_ENABLED", "true").lower() == "true":
        briefing_task = asyncio.create_task(briefing_loop(SessionLocal))

    yield

    if briefing_task is not None:
        briefing_task.cancel()
        try:
            await briefing_task
        except asyncio.CancelledError:
            pass

    if stop_event is not None:
        stop_event.set()
    if scheduler_task is not None:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass


def create_app() -> FastAPI:
    api = FastAPI(title="Stock Analysis API", version="0.1.0", lifespan=lifespan)
    api.include_router(router)
    api.include_router(briefing_router)
    return api


app = create_app()
