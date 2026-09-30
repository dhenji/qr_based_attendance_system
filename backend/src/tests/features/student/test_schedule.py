from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timezone
from typing import Any

import pytest

from features.student.exceptions import StudentNotFoundException
from features.student.model import Student
from features.student.model import Student as StudentEntity
from features.student.service import StudentService

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def one_or_none(self):
        assert len(self._rows) <= 1
        return self._rows[0] if self._rows else None


class _FakeSession:
    """Fake session for the schedule read path.

    `scalars()` serves the student lookup (BaseCRUD.get_by -> entity
    Student). `execute()` pops one queued row-set per call, in order:
    first call = offering rows, second call = professor rows. The
    empty-enrollments case queues a single entry because the helper
    early-returns without a second query.
    """

    def __init__(self, *, student=None, exec_queue=()):
        self.student = student
        self.exec_queue = list(exec_queue)

    async def scalars(self, stmt):
        entity = stmt.column_descriptions[0].get("entity")

        if entity is StudentEntity:
            return _FakeResult([self.student] if self.student else [])

        return _FakeResult([])

    async def execute(self, stmt):
        assert self.exec_queue, "unexpected execute() call"
        return _FakeResult(self.exec_queue.pop(0))

    async def flush(self):
        pass

    def add(self, obj):
        pass


def _student(**overrides):
    values: dict[str, Any] = {
        "id": 5,
        "user_id": 42,
        "student_id": "24-0001",
        "email": "student@example.com",
        "first_name": "Jose",
        "middle_name": None,
        "last_name": "Rizal",
        "year_level_id": 301,
        "section": "A",
        "is_active": True,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return Student(**values)


def _offering_row(**overrides):
    row = (
        11,  # offering_id
        101,  # course_id
        "CS101",  # course_code
        "Intro to CS",  # course_name
        "BSCS",  # program_code
        "1st Year",  # year_level_label
        "1st Sem",  # semester
        "MWF",  # schedule_days
        time(9, 0),  # schedule_start_time
        time(10, 0),  # schedule_end_time
        "Lab101",  # classroom_name
    )
    return overrides.get("row", row)


def _run(coro):
    return asyncio.run(coro)


def test_returns_enrolled_offerings_with_professor_names() -> None:
    offerings = [
        _offering_row(),
        (
            12,
            102,
            "MATH202",
            "Calculus 2",
            "BSCS",
            "1st Year",
            "1st Sem",
            "TTH",
            time(11, 0),
            time(12, 30),
            None,
        ),
    ]
    profs = [
        (11, "Grace", "Hopper", True, date(2025, 8, 4)),
        (12, "Ada", "Lovelace", True, date(2025, 8, 4)),
    ]
    service = StudentService(
        _FakeSession(student=_student(), exec_queue=[offerings, profs])
    )

    response = _run(service.get_schedule(user_id=42))

    assert [item.offering_id for item in response.offerings] == [11, 12]
    first, second = response.offerings
    assert (first.course_code, first.course_name) == ("CS101", "Intro to CS")
    assert first.program_code == "BSCS"
    assert first.year_level_label == "1st Year"
    assert first.semester == "1st Sem"
    assert first.schedule_days == "MWF"
    assert first.schedule_start_time == time(9, 0)
    assert first.schedule_end_time == time(10, 0)
    assert first.classroom_name == "Lab101"
    assert first.professor_name == "Grace Hopper"
    assert second.classroom_name is None
    assert second.professor_name == "Ada Lovelace"


def test_empty_enrollments_returns_empty() -> None:
    service = StudentService(_FakeSession(student=_student(), exec_queue=[[]]))

    response = _run(service.get_schedule(user_id=42))

    assert response.offerings == []


def test_unknown_user_raises_404() -> None:
    service = StudentService(_FakeSession(student=None, exec_queue=[]))

    with pytest.raises(StudentNotFoundException) as exc_info:
        _run(service.get_schedule(user_id=999))

    assert exc_info.value.code == "student_not_found"
    assert exc_info.value.status_code == 404


def test_unassigned_offering_has_null_professor() -> None:
    service = StudentService(
        _FakeSession(student=_student(), exec_queue=[[_offering_row()], []])
    )

    (item,) = _run(service.get_schedule(user_id=42)).offerings

    assert item.offering_id == 11
    assert item.professor_name is None


def test_primary_assignment_wins_over_secondary() -> None:
    profs = [
        (11, "Ada", "Lovelace", False, date(2025, 8, 4)),
        (11, "Grace", "Hopper", True, date(2025, 8, 1)),
    ]
    service = StudentService(
        _FakeSession(student=_student(), exec_queue=[[_offering_row()], profs])
    )

    (item,) = _run(service.get_schedule(user_id=42)).offerings

    assert item.professor_name == "Grace Hopper"
