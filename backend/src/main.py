from __future__ import annotations

import logging
from collections.abc import Coroutine
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.router import api_router
from core.config import Settings, get_settings
from core.database import database
from core.exceptions import AppException
from core.scheduler import JOB_BACKUP, JOB_RISK_BATCH, get_scheduler
from features.analytics.batch import run_scheduled_risk_batch
from features.system.service import run_scheduled_backup

logger = logging.getLogger(__name__)

if get_settings().debug:
    _email_logger = logging.getLogger("shared.email")
    _email_logger.setLevel(logging.INFO)
    if not _email_logger.handlers:
        _email_handler = logging.StreamHandler()
        _email_handler.setFormatter(
            logging.Formatter("%(levelname)s:%(name)s:%(message)s")
        )
        _email_logger.addHandler(_email_handler)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    cfg = get_settings()
    async with database.engine.connect() as conn:
        await conn.execute(text("SELECT 1"))

    scheduler = get_scheduler()
    if cfg.scheduler_enabled:
        # Risk first: it is the cheaper of the two and its 02:00 slot clears
        # the 03:00 backup, so on a slow night the backup is what gets squeezed
        # rather than the scores.
        scheduler.register(
            JOB_RISK_BATCH, cfg.risk_batch_cron, run_scheduled_risk_batch
        )
        scheduler.register(JOB_BACKUP, cfg.backup_cron, run_scheduled_backup)
        scheduler.start()
    else:
        logger.info(
            "Background scheduler disabled (SCHEDULER_ENABLED=false); "
            "no cron jobs registered"
        )

    try:
        yield
    finally:
        # Before the engine is disposed: shutdown cancels whatever is still
        # running and waits for it to release its connection.
        await scheduler.shutdown()
        await database.dispose()


class UnhandledExceptionMiddleware:
    """Return a CORS-compatible JSON 500 for unhandled errors.

    Starlette's ServerErrorMiddleware sits outside CORSMiddleware, so its
    plain-text 500 carries no Access-Control-Allow-Origin header. The browser
    then hides the response and reports a transport failure. Catching inside
    CORS keeps the real status and a stable JSON envelope visible to clients.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            if response_started:
                raise
            logger.exception(
                "Unhandled error on %s %s",
                scope.get("method"),
                scope.get("path"),
            )
            response = JSONResponse(
                status_code=500,
                content={
                    "detail": {
                        "code": "internal_error",
                        "message": "Something went wrong. Please try again.",
                    }
                },
            )
            await response(scope, receive, send)


app = FastAPI(title="QR Based Attendance System")

settings: Settings = get_settings()

# Added first so CORSMiddleware wraps it: the 500 response must pass through
# CORS to carry Access-Control-Allow-Origin.
app.add_middleware(UnhandledExceptionMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.to_dict()})


app.include_router(api_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
