"""The one definition of a currently effective professor assignment.

An assignment's effective window is inclusive at both ends: it starts on
`effective_from` and, when `effective_to` is set, remains active through that
day. The session, attendance, professor, reports, excuse, student, and course
slices all read that window, so it lives here rather than being re-derived per
feature.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import ColumnElement, and_, or_

from features.course_professor.model import CourseProfessor


def active_assignment_clause(today: date) -> ColumnElement[bool]:
    """Assignments whose inclusive effective window covers `today`."""
    return and_(
        CourseProfessor.effective_from <= today,
        or_(
            CourseProfessor.effective_to.is_(None),
            CourseProfessor.effective_to >= today,
        ),
    )
