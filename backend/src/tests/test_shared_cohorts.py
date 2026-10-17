"""Unit cover for the shared cohort definition.

`cohort_key` is the single grouping the admin comparison slice and professor
reports share (regression for #277: both grouped by course id alone). Pure
functions, so no DB.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared.cohorts import cohort_key, group_by_cohort


@dataclass
class _Offering:
    id: int
    course_id: int
    program_id: int
    year_level_id: int


def test_key_is_course_program_year() -> None:
    offering = _Offering(id=1, course_id=10, program_id=2, year_level_id=3)

    assert cohort_key(offering) == (10, 2, 3)


def test_same_course_different_program_is_a_different_cohort() -> None:
    a = _Offering(id=1, course_id=10, program_id=2, year_level_id=3)
    b = _Offering(id=2, course_id=10, program_id=9, year_level_id=3)

    assert cohort_key(a) != cohort_key(b)


def test_same_course_different_year_level_is_a_different_cohort() -> None:
    a = _Offering(id=1, course_id=10, program_id=2, year_level_id=3)
    b = _Offering(id=2, course_id=10, program_id=2, year_level_id=4)

    assert cohort_key(a) != cohort_key(b)


def test_group_keeps_cohorts_apart_and_orders_by_id() -> None:
    offerings = [
        _Offering(id=5, course_id=10, program_id=2, year_level_id=3),
        _Offering(id=3, course_id=10, program_id=2, year_level_id=3),
        _Offering(id=4, course_id=10, program_id=9, year_level_id=3),
    ]

    grouped = group_by_cohort(offerings)

    assert set(grouped) == {(10, 2, 3), (10, 9, 3)}
    assert [row.id for row in grouped[(10, 2, 3)]] == [3, 5]
    assert [row.id for row in grouped[(10, 9, 3)]] == [4]
