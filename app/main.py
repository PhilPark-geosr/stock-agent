import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import SessionLocal, init_db
from app.kakao_auth import kakao_settings
from app.routes import router
from app.scheduler import start_scheduler
from app.scheduler_config import scheduler_settings
from app.settings import load_environment

logging.basicConfig(level=logging.INFO)

load_environment()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    token = kakao_settings()["access_token"]
    if token:
        logger.info("Kakao alerts enabled (access token loaded)")
    else:
        logger.warning("Kakao alerts disabled: KAKAO_ACCESS_TOKEN missing in .env")

    scheduler_task: asyncio.Task[None] | None = None
    stop_event: asyncio.Event | None = None
    if scheduler_settings()["enabled"]:
        scheduler_task, stop_event = start_scheduler(SessionLocal)

    yield

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
    return api


app = create_app()
