from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timezone
from typing import Any

import pytest

from features.professor.exceptions import ProfessorNotFoundException
from features.professor.model import Professor
from features.professor.model import Professor as ProfessorEntity
from features.professor.service import ProfessorService

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)

# The assignment projection carries the offering's own configuration as well
# as its identity (D93) — the schedule, the classroom and the default
# windows a session inherits.
ROWS = [
    (
        11,
        101,
        "CS101",
        "Intro to CS",
        201,
        "BSCS",
        301,
        "1st Year",
        "1st Sem",
        "2025-2026",
        True,
        date(2025, 8, 4),
        None,
        3,
        "MWF",
        time(9, 0),
        time(10, 0),
        "Room 101",
        14.5,
        121.0,
        5,
        10,
        60,
    ),
    (
        12,
        102,
        "CS102",
        "Data Structures",
        201,
        "BSCS",
        302,
        "2nd Year",
        "1st Sem",
        "2025-2026",
        False,
        date(2025, 8, 4),
        None,
        4,
        "TTH",
        time(13, 0),
        time(14, 30),
        "Lab 2",
        1.5,
        2.5,
        5,
        10,
        None,
    ),
]

COUNTS = [(11, 30), (12, 35)]

SECTIONS = [(11, "A"), (11, "B"), (12, "A")]


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def one_or_none(self):
        assert len(self._rows) <= 1
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(
        self,
        *,
        professor=None,
        assignments=(),
        counts=(),
        sections=(),
        scalar_counts=None,
    ):
        self.professor = professor
        self.assignments = list(assignments)
        self.count_rows = list(counts)
        self.section_rows = list(sections)
        self.scalar_counts = list(scalar_counts or [])

    async def get(self, model, ident):
        return None

    async def scalars(self, stmt):
        entity = stmt.column_descriptions[0].get("entity")

        if entity is ProfessorEntity:
            return _FakeResult([self.professor] if self.professor else [])

        return _FakeResult([])

    async def scalar(self, stmt):
        return self.scalar_counts.pop(0) if self.scalar_counts else 0

    async def execute(self, stmt):
        compiled = str(stmt)

        if "students" in compiled:
            return _FakeResult(list(self.section_rows))

        if "count" in compiled:
            return _FakeResult(list(self.count_rows))

        return _FakeResult(list(self.assignments))

    async def flush(self):
        pass

    def add(self, obj):
        pass


def _professor(**overrides):
    values: dict[str, Any] = {
        "id": 7,
        "user_id": 42,
        "email": "prof@example.com",
        "first_name": "Grace",
        "middle_name": None,
        "last_name": "Hopper",
        "department": "CS",
        "is_active": True,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return Professor(**values)


def _run(coro):
    return asyncio.run(coro)


def test_resolve_professor_id_returns_claimed_row() -> None:
    session = _FakeSession(professor=_professor())

    assert _run(ProfessorService(session).resolve_professor_id(user_id=42)) == 7


def test_resolve_professor_id_unclaimed_raises_404() -> None:
    session = _FakeSession(professor=None)

    with pytest.raises(ProfessorNotFoundException) as exc_info:
        _run(ProfessorService(session).resolve_professor_id(user_id=99))

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "professor_not_found"


def test_list_assigned_offerings_shape_and_pagination() -> None:
    session = _FakeSession(
        professor=_professor(), assignments=ROWS, counts=COUNTS, sections=SECTIONS
    )

    page = _run(
        ProfessorService(session).list_assigned_offerings(user_id=42, page=1, size=1)
    )

    assert page.total == 2 and page.page == 1 and page.size == 1
    assert len(page.items) == 1
    first = page.items[0]
    assert first.offering_id == 11 and first.course_code == "CS101"
    assert first.course_name == "Intro to CS"
    assert first.course_id == 101
    assert first.program_id == 201
    assert first.program_code == "BSCS"
    assert first.year_level_id == 301
    assert first.year_level_label == "1st Year"
    assert first.semester == "1st Sem" and first.academic_year == "2025-2026"
    assert first.is_primary is True
    assert first.effective_from == date(2025, 8, 4)
    assert first.effective_to is None
    assert first.units == 3
    assert first.enrolled_count == 30
    assert first.section == ["A", "B"]

    session = _FakeSession(
        professor=_professor(), assignments=ROWS, counts=COUNTS, sections=SECTIONS
    )

    second = _run(
        ProfessorService(session).list_assigned_offerings(user_id=42, page=2, size=1)
    )

    assert len(second.items) == 1 and second.items[0].offering_id == 12
    assert second.items[0].is_primary is False
    assert second.items[0].units == 4
    assert second.items[0].enrolled_count == 35
    assert second.items[0].section == ["A"]


DUPLICATE_OFFERING_ROWS = [
    *ROWS,
    (
        11,
        101,
        "CS101",
        "Intro to CS",
        201,
        "BSCS",
        301,
        "1st Year",
        "1st Sem",
        "2025-2026",
        False,
        date(2026, 1, 1),
        date(2026, 10, 19),
        3,
        "MWF",
        time(9, 0),
        time(10, 0),
        "Room 101",
        14.5,
        121.0,
        5,
        10,
        60,
    ),
]


def test_assigned_offerings_dedupe_by_offering() -> None:
    session = _FakeSession(
        professor=_professor(),
        assignments=DUPLICATE_OFFERING_ROWS,
        counts=COUNTS,
        sections=SECTIONS,
    )

    page = _run(
        ProfessorService(session).list_assigned_offerings(user_id=42, page=1, size=10)
    )

    assert page.total == 2
    assert [item.offering_id for item in page.items] == [11, 12]
    assert page.items[0].effective_to is None


def test_get_self_profile_enrichment() -> None:
    session = _FakeSession(
        professor=_professor(),
        assignments=ROWS,
        counts=COUNTS,
        sections=SECTIONS,
        scalar_counts=[87],
    )

    profile = _run(ProfessorService(session).get_self_profile(user_id=42))

    assert profile.id == 7 and profile.email == "prof@example.com"
    assert profile.claim_status == "Claimed"
    assert profile.created_at == NOW
    assert profile.session_count == 87
    assert len(profile.assigned_courses) == 2
    assert profile.assigned_courses[0].units == 3
    assert profile.assigned_courses[0].enrolled_count == 30
    assert profile.assigned_courses[0].section == ["A", "B"]
