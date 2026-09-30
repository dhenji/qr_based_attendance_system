from __future__ import annotations

import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from features.student.model import Student

DEFAULT_TTL_SECONDS: int = 300


class TTLCache:
    """Process-local, async-safe in-memory TTL cache."""

    def __init__(self, default_ttl: int = DEFAULT_TTL_SECONDS) -> None:
        self._default_ttl = default_ttl
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        item: tuple[float, Any] | None = self._store.get(key)

        if item is None:
            return None

        expires_at, value = item

        if expires_at < time.monotonic():
            del self._store[key]
            return None

        return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        ttl = ttl or self._default_ttl
        self._store[key] = (time.monotonic() + ttl, value)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)


_cache = TTLCache()


def _face_key(student_id: int) -> str:
    return f"face_embedding:{student_id}"


async def get_face_embedding_cached(
    session: AsyncSession, student_id: int
) -> bytes | None:
    """Return the cached face embedding, or load it from the DB and cache it."""

    cached: Any | None = _cache.get(_face_key(student_id))

    if cached is not None:
        return cached

    embedding = (
        await session.scalars(
            select(Student.face_embedding).where(Student.id == student_id)
        )
    ).one_or_none()

    if embedding is not None:
        _cache.set(_face_key(student_id), embedding)

    return embedding


def invalidate_face_embedding(student_id: int) -> None:
    """Evict a student's cached embedding (call on archive/revoke/enroll)."""
    _cache.invalidate(_face_key(student_id))
