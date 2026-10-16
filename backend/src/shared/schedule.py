"""Shared meeting-schedule math (D79).

Weekly Scheduled Hours for one meeting entry is its duration times its
distinct day-letter count ("MWF" -> 3): the single definition behind the
course weekly requirement, the session-open gate, and the professor
schedule-ok flag. Kept here — like `shared/rates.py` — so the three
features cannot diverge again.
"""

from __future__ import annotations

from datetime import time


def distinct_day_count(days: str) -> int:
    """Distinct day letters in a compact days string ("MWF" -> 3).

    Upper-cased and de-duplicated so legacy free text cannot inflate the
    count. Strings with no A-Z letter count zero.
    """
    return len({ch for ch in days.upper() if "A" <= ch <= "Z"})


def meeting_minutes(schedule_days: str, start: time, end: time) -> float:
    """Weekly minutes contributed by one meeting entry, second precision."""
    return (
        (
            end.hour * 60
            + end.minute
            + end.second / 60
            + end.microsecond / 60000000
        )
        - (
            start.hour * 60
            + start.minute
            + start.second / 60
            + start.microsecond / 60000000
        )
    ) * distinct_day_count(schedule_days)
