"""Timezone helpers shared by more than one feature slice."""

from __future__ import annotations

from datetime import datetime, timezone


def ensure_aware(value: datetime) -> datetime:
    """Return `value` with UTC attached when it is naive, else unchanged."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value
