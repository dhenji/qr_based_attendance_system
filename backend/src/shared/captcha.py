from __future__ import annotations

import httpx

from core.config import Settings, get_settings
from core.exceptions import AppException

TURNSTILE_SITEVERIFY_URL: str = (
    "https://challenges.cloudflare.com/turnstile/v0/siteverify"
)

TURNSTILE_TIMEOUT_SECONDS: int = 10


class CaptchaInvalidException(AppException):
    """400 - CAPTCHA token missing or failed server-side verification."""

    status_code: int = 400
    code: str = "invalid_captcha"

    def __init__(self) -> None:
        super().__init__(message="Captcha verification failed, please try again")


async def verify_turnstile_token(
    token: str | None, client_ip: str | None = None, settings: Settings | None = None
) -> bool:
    """Verify a Cloudflare Turnstile token with Cloudflare's siteverify API.

    When ``settings.turnstile_secret_key`` is empty (dev/test default) this is a
    no-op that returns True (captcha disabled). Otherwise it enforces the check,
    raising ``CaptchaInvalidException`` (HTTP 400) on failure.
    """

    current_settings: Settings = settings or get_settings()

    if not current_settings.turnstile_secret_key:
        return True

    if token is None or not token.strip():
        raise CaptchaInvalidException()

    payload: dict[str, str] = {
        "secret": current_settings.turnstile_secret_key,
        "response": token.strip(),
    }

    if client_ip is not None:
        payload["remoteip"] = client_ip

    result: dict

    try:
        async with httpx.AsyncClient(timeout=TURNSTILE_TIMEOUT_SECONDS) as client:
            response: httpx.Response = await client.post(
                TURNSTILE_SITEVERIFY_URL, data=payload
            )
            result = response.json()
    except httpx.HTTPError:
        raise CaptchaInvalidException()

    if not result.get("success"):
        raise CaptchaInvalidException()

    return True
