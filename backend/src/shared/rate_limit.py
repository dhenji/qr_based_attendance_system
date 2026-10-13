from __future__ import annotations

"""In-memory, per-key fixed-window rate limiter (process-local).

WARNING: this limiter lives in process memory only. When the API runs as
multiple instances behind a load balancer, the buckets are not shared - swap
the backing store for a shared one (Redis, etc.) using the same composite key ``"{path}|{source}"``. Also reused later by the attendance-scan and analytics
risk-refresh endpoints to dampen abuse.
"""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from fastapi import Request

from core.exceptions import AppException

RequestKey = Literal["ip", "email"]


class RateLimitedException(AppException):
    """429 - client exceeded the allowed request rate."""

    status_code: int = 429
    code: str = "rate_limited"

    def __init__(self) -> None:
        super().__init__(message="Too many requests, please try again later")


class FixedWindowLimiter:
    """Async-safe per-key fixed-window limiter

    Each key tracks ``("start", "window", "count")`` using a monotonic clock. A key's window is reset lazily once it expires; the dictioniary is trimmed whenever it grows pass ``_MAX_ENTRIES`` so memory stays bounded.
    """

    _MAX_ENTRIES: int = 10_000

    def __init__(self) -> None:
        self._windows: dict[str, tuple[float, int, int]] = {}
        self._lock = asyncio.Lock()

    def _trim(self, now: float) -> None:
        """Drop fully-expired buckets once the map grows large (lock held)."""

        if len(self._windows) <= self._MAX_ENTRIES:
            return

        stale: list[str] = [
            key
            for key, (start, window, _) in self._windows.items()
            if now - start >= window
        ]

        for key in stale:
            del self._windows[key]

    async def exhausted(self, key: str, max_calls: int, window_seconds: int) -> bool:
        """Whether ``key`` has already spent its budget in the current window.

        Read-only: unlike `hit` this records nothing, so a caller can gate a
        *failure* counter on it. Calling `hit` up front would count successes
        too, which is wrong for a limiter that is meant to cap failures.
        """

        now: float = time.monotonic()
        entry: tuple[float, int, int] | None = self._windows.get(key)

        if entry is None or now - entry[0] >= entry[1]:
            return False

        return entry[2] >= max_calls

    async def hit(self, key: str, max_calls: int, window_seconds: int) -> bool:
        """Record a call for ``key``.

        Returns True when the call is allowed, False when the current window's ``max_calls`` budget is already spent.
        """

        now: float = time.monotonic()

        async with self._lock:
            entry: tuple[float, int, int] | None = self._windows.get(key)

            if entry is not None and now - entry[0] < entry[1]:
                start, window, count = entry

                if count >= max_calls:
                    return False

                self._windows[key] = (start, window, count + 1)
                return True

            self._windows[key] = (now, window_seconds, 1)
            self._trim(now)

            return True

    async def reset(self, key: str) -> None:
        """Forget ``key``'s budget entirely.

        Used when the guarded credential itself is replaced (a resend mints a
        fresh OTP): guesses spent against the burned code must not haunt the
        new one. Lock-protected like `hit`, for the same races.
        """

        async with self._lock:
            self._windows.pop(key, None)


_limiter = FixedWindowLimiter()


async def _email_from(request: Request) -> str | None:
    """Pull a normalized email out of the JSON body, or None if there isn't one.

    None rather than a placeholder: the caller resolves it to the client IP.
    A shared sentinel would put every request whose body carries no email -
    including ones an attacker sends deliberately - into one bucket, so a
    single hostile client could spend the budget belonging to all of them.
    """

    try:
        body: dict[str, Any] = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return None

    email: Any = body.get("email")

    if not isinstance(email, str) or not email.strip():
        return None

    return email.strip().lower()


def rate_limit(
    max_calls: int,
    window_seconds: int,
    key: RequestKey = "ip",
) -> Callable[..., Awaitable[None]]:
    """FastAPI dependency factory enforcing a per-key fixed-window limit.

    - ``key="ip"``: bucket by ``request.client.host``, ``X-Forwarded-For`` is intentionally NOT trusted - use it only behind a configured trusted proxy.
    - ``key="email"``: bucket by the normalized ``email`` in the JSON body, falling back to the client IP when the body can't be parsed or has none.

    Raises ``RateLimitedException`` (HTTP 429, ``{detail: {code: "rate_limited", message}}``) once the window budget is spent.
    """

    limiter: FixedWindowLimiter = _limiter

    async def dependency(request: Request) -> None:
        ip: str = "unknown"

        if request.client is not None:
            ip = request.client.host

        source: str
        email: str | None = await _email_from(request) if key == "email" else None

        source = email if email is not None else (ip or "unknown")
        bucket_key: str = f"{request.url.path}|{source.lower()}"

        if not await limiter.hit(bucket_key, max_calls, window_seconds):
            raise RateLimitedException()

    return dependency
