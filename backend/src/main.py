from collections.abc import Coroutine
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from api.router import api_router
from core.config import Settings, get_settings
from core.database import database
from core.exceptions import AppException


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with database.engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    yield
    await database.dispose()


app = FastAPI(title="QR Based Attendance System")

settings: Settings = get_settings()

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
