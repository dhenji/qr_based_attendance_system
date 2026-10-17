from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from features.course.service import CourseService, parse_course_csv
from features.system.model import AuditLog
from shared.enums import AuditAction, AuditEntity

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
    def __init__(self, *, rows: list | None = None):
        self.rows = list(rows or [])
        self.added = []

    async def scalars(self, stmt):
        return _FakeResult(self.rows.pop(0) if self.rows else [])

    async def flush(self):
        pass

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = len(self.added) + 100
        for field in ("created_at", "updated_at"):
            if hasattr(obj, field) and getattr(obj, field) is None:
                setattr(obj, field, NOW)
        if hasattr(obj, "is_active") and getattr(obj, "is_active") is None:
            obj.is_active = True
        self.added.append(obj)


def _run(coro):
    return asyncio.run(coro)


HEADER = "course_code,course_name,units,session_duration_hours"


def test_parse_course_csv_normalizes() -> None:
    rows, errors = parse_course_csv(
        f"{HEADER}\n cs101 , Software Engineering 1,3,1.5\n".encode()
    )

    assert errors == []
    assert len(rows) == 1
    assert rows[0].course_code == "CS101"


def test_parse_course_csv_bad_header_reports_line_1() -> None:
    rows, errors = parse_course_csv(b"course_code,course_name\nCS101,SE1\n")

    assert rows == []
    assert len(errors) == 1
    assert errors[0].line == 1


def test_import_roster_creates_duplicates_and_errors() -> None:
    session = _FakeSession(rows=[[], [], [], []])
    content = (
        f"{HEADER}\n"
        "CS101,Software Engineering 1,3,1.5\n"
        "CS101,Software Engineering 1,3,1.5\n"
        "CS102,,3,1.5\n"
        "CS103,Bad Units,99,1.5\n"
    ).encode()

    result = _run(CourseService(session).import_roster(content=content, actor_id=None))

    assert result.imported == 1
    assert result.duplicates == 1
    assert [e.line for e in result.errors] == [4, 5]
    assert len(session.added) == 2
    assert session.added[0].course_code == "CS101"
    assert session.added[0].units == 3
    audit = session.added[1]
    assert isinstance(audit, AuditLog)
    assert audit.action == AuditAction.IMPORT
    assert audit.entity_type == AuditEntity.COURSE
    assert audit.entity_id is None
    assert audit.new_value == {"imported": 1, "duplicates": 1, "errors": 2}


def test_import_roster_duplicate_against_database() -> None:
    from features.course.model import Course

    existing = Course(
        id=1,
        course_code="CS101",
        course_name="Software Engineering 1",
        units=3,
        session_duration_hours=1.5,
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
    )
    session = _FakeSession(rows=[[existing]])
    content = (f"{HEADER}\nCS101,Software Engineering 1,3,1.5\n").encode()

    result = _run(CourseService(session).import_roster(content=content, actor_id=None))

    assert result.imported == 0
    assert result.duplicates == 1
    assert result.errors == []
    assert len(session.added) == 1  # audit row only
    assert isinstance(session.added[0], AuditLog)


def test_import_roster_rejects_bad_duration() -> None:
    session = _FakeSession(rows=[[], []])
    content = (
        f"{HEADER}\n"
        "CS104,Bad Duration,3,99\n"
        "CS105,Also Bad,3,abc\n"
    ).encode()

    result = _run(CourseService(session).import_roster(content=content, actor_id=None))

    assert result.imported == 0
    assert result.duplicates == 0
    assert [e.line for e in result.errors] == [2, 3]
