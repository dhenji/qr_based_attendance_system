from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from httpx import ASGITransport, AsyncClient

from main import UnhandledExceptionMiddleware


async def test_unhandled_error_returns_json_with_cors_headers() -> None:
    """A 500 must stay visible to the browser, not become a network failure."""
    app = FastAPI()
    app.add_middleware(UnhandledExceptionMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("boom")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/boom", headers={"Origin": "http://localhost:5173"}
        )

    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    body: Any = response.json()
    assert body["detail"]["code"] == "internal_error"
    assert body["detail"]["message"] == "Something went wrong. Please try again."
