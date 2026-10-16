import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from clipper.api.dependencies import (
    publishing_connections,
    run_automation_cycle,
    run_project_cycle,
    run_story_video_cycle,
)
from clipper.api.routes import router
from clipper.config import settings
from clipper.persistence import SessionLocal, create_schema

logger = structlog.get_logger()


async def automation_scheduler() -> None:
    while True:
        try:
            await asyncio.to_thread(run_automation_cycle)
        except Exception as error:
            logger.exception("automation_scheduler_failed", error_category=type(error).__name__)
        await asyncio.sleep(15)


async def story_video_scheduler() -> None:
    while True:
        try:
            await asyncio.to_thread(run_story_video_cycle)
        except Exception as error:
            logger.exception("story_video_scheduler_failed", error_category=type(error).__name__)
        # Also back off after an engine reservation conflict instead of spinning on 409.
        await asyncio.sleep(2)


async def project_scheduler() -> None:
    while True:
        try:
            processed = await asyncio.to_thread(run_project_cycle)
        except Exception as error:
            logger.exception("project_scheduler_failed", error_category=type(error).__name__)
            processed = None
        await asyncio.sleep(0 if processed else 1)


def initialize_account_identities() -> None:
    with SessionLocal() as session:
        publishing_connections.backfill_identities(session)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    create_schema()
    await asyncio.to_thread(initialize_account_identities)
    await asyncio.to_thread(run_project_cycle, recover=True)
    project_worker = asyncio.create_task(project_scheduler())
    scheduler = asyncio.create_task(automation_scheduler())
    video_scheduler = asyncio.create_task(story_video_scheduler())
    try:
        yield
    finally:
        project_worker.cancel()
        scheduler.cancel()
        video_scheduler.cancel()
        with suppress(asyncio.CancelledError):
            await project_worker
        with suppress(asyncio.CancelledError):
            await scheduler
        with suppress(asyncio.CancelledError):
            await video_scheduler


app = FastAPI(
    title="ReachCut Local API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://127.0.0.1:{settings.web_port}",
        f"http://localhost:{settings.web_port}",
    ],
    allow_credentials=False,
    allow_methods=["DELETE", "GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
)
app.include_router(router)
