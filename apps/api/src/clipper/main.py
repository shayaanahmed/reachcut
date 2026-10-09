import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from clipper.api.routes import router
from clipper.config import settings
from clipper.persistence import create_schema


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    create_schema()
    yield


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
        settings.web_base_url.rstrip("/"),
    ],
    allow_credentials=False,
    allow_methods=["DELETE", "GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def require_local_agent(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Reject direct API access when the supervised local agent is active."""

    expected = settings.local_agent_token
    supplied = request.headers.get("x-reachcut-agent-token", "")
    if expected and not secrets.compare_digest(supplied, expected):
        return JSONResponse(
            status_code=403,
            content={"detail": "local agent authorization required"},
        )
    return await call_next(request)


app.include_router(router)
