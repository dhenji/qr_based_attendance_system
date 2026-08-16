from collections.abc import Coroutine
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from core.config import Settings, get_settings
from core.database import database


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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
