from __future__ import annotations

"""The one definition of an attendance cohort.

A *cohort* is a course offered to one program at one year level — the unit the
admin Comparison tab and the professor per-course report compare side by side.
A course is **not** a cohort: the same subject (e.g. "CS101") is routinely
offered to several programs/year levels, and those offerings must be compared
against each other rather than merged. D6 makes that sharing explicit and D34
requires comparison to "slice by program and year level (same subject across
cohorts)".

`cohort_key` is that definition. Before it, `analytics` and `reports` each
grouped comparison rows by `course_id` alone, so every cohort of a course
collapsed into one blended row labelled with whichever offering happened to
come first. Those two copies had already diverged once in this codebase (see
`shared/rates.py`); this keeps a third from starting.

The key is the (course, program, year level) triple. Semester and dates are
*filter* axes, not identity: D34 slices comparison "within term durations", so
callers narrow by semester and the key stays cohort-shaped.
"""

from collections.abc import Iterable
from typing import Protocol, TypeVar

CohortKey = tuple[int, int, int]


class OfferingLike(Protocol):
    """The slice of a course offering a cohort key reads."""

    id: int
    course_id: int
    program_id: int
    year_level_id: int


OfferingT = TypeVar("OfferingT", bound=OfferingLike)


def cohort_key(offering: OfferingLike) -> CohortKey:
    """Identity of the cohort an offering belongs to."""
    return (offering.course_id, offering.program_id, offering.year_level_id)


def group_by_cohort(
    offerings: Iterable[OfferingT],
) -> dict[CohortKey, list[OfferingT]]:
    """Group offerings by cohort, each group ordered by offering id.

    Stable ordering matters: the caller renders these groups as the chart/table
    rows, so a re-read must not shuffle them.
    """
    grouped: dict[CohortKey, list[OfferingT]] = {}

    for row in sorted(offerings, key=lambda item: item.id):
        grouped.setdefault(cohort_key(row), []).append(row)

    return grouped
