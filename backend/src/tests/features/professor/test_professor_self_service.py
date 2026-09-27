import asyncio
from datetime import datetime, timezone
from typing import Any

import pytest

from features.professor.exceptions import ProfessorNotFoundException
from features.professor.model import Professor
from features.professor.model import Professor as ProfessorEntity
from features.professor.service import ProfessorService

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)

ROWS = [
    (11, "CS101", "Intro to CS", "BSCS", "1st Year", True),
    (12, "CS102", "Data Structures", "BSCS", "2nd Year", False),
]


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def one_or_none(self):
        assert len(self._rows) <= 1
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, *, professor=None, assignments=(), counts=None):
        self.professor = professor
        self.assignments = list(assignments)
        self.counts = list(counts or [])

    async def get(self, model, ident):
        return None

    async def scalars(self, stmt):
        entity = stmt.column_descriptions[0].get("entity")

        if entity is ProfessorEntity:
            return _FakeResult([self.professor] if self.professor else [])

        return _FakeResult([])

    async def scalar(self, stmt):
        return self.counts.pop(0) if self.counts else 0

    async def execute(self, stmt):
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
    session = _FakeSession(professor=_professor(), assignments=ROWS)

    page = _run(
        ProfessorService(session).list_assigned_offerings(
            user_id=42, page=1, size=1
        )
    )

    assert page.total == 2 and page.page == 1 and page.size == 1
    assert len(page.items) == 1
    first = page.items[0]
    assert first.offering_id == 11 and first.course_code == "CS101"
    assert first.course_name == "Intro to CS"
    assert first.program_code == "BSCS" and first.year_level_label == "1st Year"
    assert first.is_primary is True

    session = _FakeSession(professor=_professor(), assignments=ROWS)

    second = _run(
        ProfessorService(session).list_assigned_offerings(
            user_id=42, page=2, size=1
        )
    )

    assert len(second.items) == 1 and second.items[0].offering_id == 12
    assert second.items[0].is_primary is False


def test_get_self_profile_enrichment() -> None:
    session = _FakeSession(
        professor=_professor(), assignments=ROWS, counts=[87]
    )

    profile = _run(ProfessorService(session).get_self_profile(user_id=42))

    assert profile.id == 7 and profile.email == "prof@example.com"
    assert profile.claim_status == "Claimed"
    assert profile.created_at == NOW
    assert profile.session_count == 87
    assert len(profile.assigned_courses) == 2
