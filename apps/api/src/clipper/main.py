import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from clipper.api.dependencies import run_automation_cycle
from clipper.api.routes import router
from clipper.config import settings
from clipper.persistence import create_schema

logger = structlog.get_logger()


async def automation_scheduler() -> None:
    while True:
        try:
            await asyncio.to_thread(run_automation_cycle)
        except Exception as error:
            logger.exception("automation_scheduler_failed", error_category=type(error).__name__)
        await asyncio.sleep(15)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    create_schema()
    scheduler = asyncio.create_task(automation_scheduler())
    try:
        yield
    finally:
        scheduler.cancel()
        with suppress(asyncio.CancelledError):
            await scheduler


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
