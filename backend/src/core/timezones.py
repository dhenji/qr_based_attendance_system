"""Timezone resolution shared by the scheduler and the session plan (D93).

A single rule for "what does this zone name mean": resolve it, or fall back to
UTC with a warning rather than failing. A slim container image may ship
without the tz database, and both consumers of this helper — the cron
scheduler and the session-time resolver — must keep running when the zone
cannot be resolved.

`core.scheduler` keeps exporting `resolve_timezone` under its own name; this
module is where the rule now lives so the session slice can use it without
importing APScheduler.
"""

from __future__ import annotations

import logging
from datetime import tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

UTC = ZoneInfo("UTC")


def resolve_timezone(name: str, *, label: str = "timezone") -> tzinfo:
    """ZoneInfo for `name`, falling back to UTC when it cannot be resolved.

    An unknown zone is a warning, not a failure: the caller still runs, on
    UTC. `label` names the setting in the warning so the operator knows which
    one to fix ("scheduler timezone" vs "institution timezone").
    """
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        logger.warning("Unknown %s %r; falling back to UTC", label, name)
        return UTC
