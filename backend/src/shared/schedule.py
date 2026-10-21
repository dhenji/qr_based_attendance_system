"""Shared meeting-schedule math (D79) and term-weeks resolution (D86).

Weekly Scheduled Hours for one meeting entry is its duration times its
distinct day-letter count ("MWF" -> 3): the single definition behind the
course weekly requirement, the session-open gate, and the professor
schedule-ok flag. Kept here — like `shared/rates.py` — so the three
features cannot diverge again.

`term_weeks` is the one definition of a term's session-week count. A term's
weeks live on the term entry in `year_levels.term_structure`; the risk batch
and the offering read DTO both resolve through here so an orphaned
`semester` value can never be counted two different ways.

`day_weekdays` is the one definition of what a `schedule_days` string means.
It used to live privately in `features/student/service.py`, but the session
plan resolver (D93) reads the same string to work out which calendar day a
meeting falls on, so the mapping lives here with the rest of the schedule
math rather than being re-derived per feature.
"""

from __future__ import annotations

from datetime import time

# Bounds and fallback for a term's session-week count. `DEFAULT_TERM_WEEKS`
# stands in for a term that has no `weeks` configured yet (the UI seeds the
# same value), and mirrors the pre-D86 hard-coded default.
TERM_WEEKS_MIN: int = 1
TERM_WEEKS_MAX: int = 52
DEFAULT_TERM_WEEKS: int = 18


def term_weeks(
    term_structure: dict | None,
    code: str,
    default: int = DEFAULT_TERM_WEEKS,
) -> int:
    """Session weeks for a term `code`, from a year level's term structure.

    Returns `default` when the structure, the term, or its `weeks` are
    absent — an orphaned `semester` (free text with no matching term entry)
    must resolve, never raise.
    """
    if not isinstance(term_structure, dict):
        return default

    terms = term_structure.get("terms")
    if not isinstance(terms, list):
        return default

    wanted = str(code).strip()
    for term in terms:
        if not isinstance(term, dict):
            continue
        if str(term.get("code", "")).strip() != wanted:
            continue

        weeks = term.get("weeks")
        # bool is an int subclass; a stray `True` must not count as 1 week.
        if isinstance(weeks, bool):
            return default
        if isinstance(weeks, int) and weeks > 0:
            return weeks
        return default

    return default


def distinct_day_count(days: str) -> int:
    """Distinct day letters in a compact days string ("MWF" -> 3).

    Upper-cased and de-duplicated so legacy free text cannot inflate the
    count. Strings with no A-Z letter count zero.
    """
    return len({ch for ch in days.upper() if "A" <= ch <= "Z"})


# Day initials for `schedule_days`, mapped to `date.weekday()` indices
# (Monday = 0).
#
# `T` is Tuesday and `H` is Thursday, because the conventional initials
# collide: the seed data writes "TF" for Tue/Fri, while wireframes.md:1387
# writes "TTH" where the trailing H stands in for Thursday precisely because
# T was already taken by Tuesday. `U` is Sunday for the same reason — `S` is
# Saturday.
#
# This is the mapping `features/student/service.py::_meets_on` used to own
# privately. It is unchanged, only relocated: an unrecognised letter still
# matches nothing rather than raising, so a typo in one offering's schedule
# hides that one class instead of breaking a whole dashboard.
DAY_WEEKDAYS: dict[str, int] = {
    "M": 0,
    "T": 1,
    "W": 2,
    "H": 3,
    "F": 4,
    "S": 5,
    "U": 6,
}


def day_weekdays(days: str | None) -> set[int]:
    """The weekday indices (`date.weekday()`) a days string names.

    "MWF" -> {0, 2, 4}. Case-insensitive; unrecognised letters are ignored
    rather than raising.
    """
    if not days:
        return set()

    return {
        DAY_WEEKDAYS[letter]
        for letter in days.strip().upper()
        if letter in DAY_WEEKDAYS
    }


def meeting_length_minutes(start: time, end: time) -> int:
    """Whole minutes from `start` to `end`; 0 when `end` is not after `start`.

    The meeting length as a duration, rounded to the minute — the unit every
    session duration, window and expiry in the system is stored in. Zero for
    an inverted pair, so a legacy row with a nonsensical end time contributes
    no length instead of a negative one.
    """
    if end <= start:
        return 0

    return int(
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
    )


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
