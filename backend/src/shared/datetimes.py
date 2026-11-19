"""Datetime helpers shared by more than one feature slice."""

from __future__ import annotations

from datetime import datetime, timezone


def ensure_aware(value: datetime) -> datetime:
    """Return `value` with UTC attached when it is naive, else unchanged."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value


def end_of_day(value: datetime | None) -> datetime | None:
    """Treat an exact-midnight bound as the end of that day.

    Date-only query parameters parse to midnight, which would otherwise
    exclude every record after 00:00. An explicit non-midnight value is
    preserved so callers can still bound a precise instant.
    """
    if value is None:
        return None
    if (value.hour, value.minute, value.second, value.microsecond) == (0, 0, 0, 0):
        return value.replace(hour=23, minute=59, second=59, microsecond=999999)

    return value
