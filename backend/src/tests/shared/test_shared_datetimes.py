"""The shared datetime helpers.

`ensure_aware` and `end_of_day` are the single implementations behind every
feature's query-bound normalization, so their contracts are pinned here rather
than left to whichever service happens to exercise them. Pure functions, no DB.

Two behaviours are easy to break during a consolidation and produce a silently
wrong result instead of an error: expanding a bound that is not exactly
midnight, and dropping the caller's timezone.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from shared.datetimes import end_of_day, ensure_aware


def test_ensure_aware_attaches_utc_to_naive_values() -> None:
    naive = datetime(2026, 11, 19, 8, 30, 15, 123456)

    aware = ensure_aware(naive)

    assert aware.tzinfo is timezone.utc
    assert aware.replace(tzinfo=None) == naive


def test_ensure_aware_leaves_aware_values_untouched() -> None:
    aware = datetime(2026, 11, 19, 8, 30, tzinfo=timezone(timedelta(hours=8)))

    assert ensure_aware(aware) is aware


def test_end_of_day_keeps_none() -> None:
    assert end_of_day(None) is None


def test_end_of_day_expands_exact_midnight() -> None:
    midnight = datetime(2026, 11, 19, tzinfo=timezone.utc)

    assert end_of_day(midnight) == datetime(
        2026, 11, 19, 23, 59, 59, 999999, tzinfo=timezone.utc
    )


def test_end_of_day_preserves_the_timezone() -> None:
    tz = timezone(timedelta(hours=8))
    midnight = datetime(2026, 11, 19, tzinfo=tz)

    result = end_of_day(midnight)

    assert result is not None
    assert result.tzinfo is tz
    assert result.hour == 23


def test_end_of_day_expands_naive_midnight_without_adding_a_timezone() -> None:
    result = end_of_day(datetime(2026, 11, 19))

    assert result == datetime(2026, 11, 19, 23, 59, 59, 999999)
    assert result is not None
    assert result.tzinfo is None


def test_end_of_day_leaves_an_explicit_time_alone() -> None:
    explicit = datetime(2026, 11, 19, 12, 30, 15, 500, tzinfo=timezone.utc)

    assert end_of_day(explicit) is explicit


def test_end_of_day_only_expands_exact_midnight() -> None:
    """A microsecond past midnight is a precise bound, not a date-only one."""

    nearly_midnight = datetime(2026, 11, 19, 0, 0, 0, 1, tzinfo=timezone.utc)

    assert end_of_day(nearly_midnight) is nearly_midnight
