from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from core.config import Settings

from shared.captcha import CaptchaInvalidException, verify_turnstile_token


def _settings(secret: str = "") -> Settings:
    return Settings(turnstile_secret_key=secret, debug=True)


class _FakeResponse(SimpleNamespace):
    def json(self) -> dict:
        return self.data


class _FakeClient:
    def __init__(self, result: dict) -> None:
        self._result = result

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def post(self, url: str, data: dict) -> _FakeResponse:
        return _FakeResponse(data=self._result)


def _patch_http(monkeypatch: pytest.MonkeyPatch, success: bool) -> None:
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda *a, **k: _FakeClient({"success": success})
    )


def test_passthrough_when_key_disabled() -> None:
    assert (
        asyncio.run(verify_turnstile_token("any-token", settings=_settings())) is True
    )


def test_missing_token_raises_when_enabled() -> None:
    with pytest.raises(CaptchaInvalidException):
        asyncio.run(verify_turnstile_token(None, settings=_settings("secret")))


def test_invalid_token_raises_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_http(monkeypatch, success=False)

    with pytest.raises(CaptchaInvalidException):
        asyncio.run(
            verify_turnstile_token(
                "bad-token", client_ip="1.2.3.4", settings=_settings("secret")
            )
        )


def test_valid_token_returns_true_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_http(monkeypatch, success=True)

    assert (
        asyncio.run(verify_turnstile_token("good-token", settings=_settings("secret")))
        is True
    )
