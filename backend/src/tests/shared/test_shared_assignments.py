"""The shared active-assignment predicate.

The predicate is the single definition behind seven service slices, so its
boundaries are pinned here: both effective dates are inclusive, an open end
matches, and `today` is supplied by the caller rather than read from a clock.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.dialects import sqlite

from shared.assignments import active_assignment_clause


def _compiled(today: date) -> str:
    return str(
        active_assignment_clause(today).compile(
            dialect=sqlite.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_window_is_inclusive_at_both_ends() -> None:
    sql = _compiled(date(2026, 11, 19))

    assert "course_professors.effective_from <= '2026-11-19'" in sql
    assert "course_professors.effective_to >= '2026-11-19'" in sql


def test_open_ended_assignment_matches() -> None:
    assert "course_professors.effective_to IS NULL" in _compiled(date(2026, 11, 19))


def test_caller_supplies_the_date() -> None:
    sql = _compiled(date(2026, 1, 1))

    assert "'2026-01-01'" in sql
    assert "'2026-11-19'" not in sql
