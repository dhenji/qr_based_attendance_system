from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import pytest

from features.program.model import Program, YearLevel
from features.student.exceptions import (
    StudentHasRecordsException,
    StudentNotArchivedException,
)
from features.student.model import Student
from features.student.service import StudentService, parse_roster_csv
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
    def __init__(
        self,
        *,
        objs: tuple = (),
        rows: dict | list | None = None,
        counts: list[int] | None = None,
    ):
        self.store = {(type(o), o.id): o for o in objs}
        self.rows = rows if rows is not None else {}
        self.counts = list(counts or [])
        self.added = []
        self.deleted = []

    async def get(self, model, ident):
        return self.store.get((model, ident))

    async def scalars(self, stmt):
        if isinstance(self.rows, list):
            return _FakeResult(self.rows.pop(0))
        entity = stmt.column_descriptions[0].get("entity")
        found = self.rows.get(entity, [])
        rows = found(stmt) if callable(found) else found
        return _FakeResult(list(rows))

    async def scalar(self, stmt):
        return self.counts.pop(0) if self.counts else 0

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

    async def delete(self, obj):
        self.deleted.append(obj)


def _program(**overrides):
    values: dict[str, Any] = {
        "id": 1,
        "code": "BSCS",
        "name": "Computer Science",
        "description": None,
        "total_years": 4,
        "is_active": True,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return Program(**values)


def _year(**overrides):
    values: dict[str, Any] = {
        "id": 1,
        "program_id": 1,
        "year_number": 1,
        "label": "1st Year",
        "term_structure": {"terms": [{"code": "1ST", "label": "First"}]},
        "sort_order": 1,
    }
    values.update(overrides)
    return YearLevel(**values)


def _student(**overrides):
    values: dict[str, Any] = {
        "id": 1,
        "user_id": None,
        "student_id": "S001",
        "email": "ada@example.com",
        "first_name": "Ada",
        "middle_name": None,
        "last_name": "Lovelace",
        "year_level_id": 1,
        "section": "A",
        "is_active": True,
        "face_embedding": None,
        "face_enrolled_at": None,
        "face_embedding_version": 0,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return Student(**values)


def _run(coro):
    return asyncio.run(coro)


HEADER = (
    "student_id,first_name,middle_name,last_name,email,program_code,section,year_level"
)


def test_parse_roster_csv_normalizes() -> None:
    rows, errors = parse_roster_csv(
        f"{HEADER}\n s001 , Ada,,Lovelace, ADA@EXAMPLE.COM ,bscs,A,1\n".encode()
    )

    assert errors == []
    assert len(rows) == 1
    assert rows[0].student_id == "S001"
    assert rows[0].email == "ada@example.com"
    assert rows[0].program_code == "BSCS"


def test_parse_roster_csv_bad_header_reports_line_1() -> None:
    rows, errors = parse_roster_csv(b"student_id,first_name\nS001,Ada\n")

    assert rows == []
    assert len(errors) == 1
    assert errors[0].line == 1


def test_import_roster_creates_duplicates_and_errors() -> None:
    existing = _student()
    prog = _program()
    year = _year()
    session = _FakeSession(
        objs=(existing, prog, year),
        # Per-row scalars() calls in order:
        # row 2 (new): Student x2, Program, YearLevel;
        # row 3 is an in-file duplicate (no DB calls);
        # row 4 is a parse error (no DB calls);
        # row 5 (unknown program): Student x2, Program.
        rows=[[], [], [prog], [year], [], [], []],
    )
    content = (
        f"{HEADER}\n"
        "S002,Ada,,Lovelace,ada2@example.com,BSCS,A,1\n"
        "S002,Ada,,Lovelace,ada2@example.com,BSCS,A,1\n"
        "S003,Bob,,Cruz,not-an-email,BSCS,B,1\n"
        "S004,Carol,,Tan,carol@example.com,UNKNOWN,C,1\n"
    ).encode()

    result = _run(
        StudentService(session).import_roster(content=content, actor_id=None)
    )

    assert result.imported == 1
    assert result.duplicates == 1
    assert [e.line for e in result.errors] == [4, 5]
    assert len(session.added) == 2
    assert session.added[0].student_id == "S002"
    assert session.added[0].year_level_id == 1
    # One aggregate row for the upload, not one per imported student.
    audit = session.added[1]
    assert isinstance(audit, AuditLog)
    assert audit.action == AuditAction.IMPORT
    assert audit.entity_type == AuditEntity.STUDENT
    assert audit.entity_id is None
    assert audit.new_value == {"imported": 1, "duplicates": 1, "errors": 2}


def test_import_roster_resolves_year_label() -> None:
    prog = _program()
    year = _year()
    session = _FakeSession(
        objs=(prog, year),
        rows=[[], [], [prog], [year]],
    )
    content = (f"{HEADER}\nS009,Zed,,Roe,zed@example.com,BSCS,Z,1st year\n").encode()

    result = _run(
        StudentService(session).import_roster(content=content, actor_id=None)
    )

    assert result.imported == 1
    assert result.duplicates == 0
    assert result.errors == []


def test_hard_delete_active_raises_not_archived() -> None:
    session = _FakeSession(objs=(_student(is_active=True),))

    with pytest.raises(StudentNotArchivedException) as exc_info:
        _run(StudentService(session).hard_delete(student_id=1, actor_id=None))

    assert exc_info.value.code == "not_archived"
    assert session.deleted == []
    # The guard rejects the delete, so it must not leave a trail row either:
    # `record_audit` rides the caller's transaction and would roll back with it.
    assert session.added == []


def test_hard_delete_with_enrollments_raises_has_records() -> None:
    session = _FakeSession(objs=(_student(is_active=False),), counts=[1])

    with pytest.raises(StudentHasRecordsException) as exc_info:
        _run(StudentService(session).hard_delete(student_id=1, actor_id=None))

    assert exc_info.value.code == "student_has_records"
    assert session.deleted == []
    assert session.added == []


def test_hard_delete_clean_archived_deletes() -> None:
    student = _student(is_active=False)
    session = _FakeSession(objs=(student,), counts=[0, 0, 0])

    _run(StudentService(session).hard_delete(student_id=1, actor_id=None))

    assert session.deleted == [student]
    audit = session.added[-1]
    assert isinstance(audit, AuditLog)
    assert audit.action == AuditAction.DELETE
    assert audit.entity_type == AuditEntity.STUDENT
    assert audit.entity_id == student.id
    assert audit.old_value["student_id"] == student.student_id
    assert audit.new_value is None


def test_list_carries_profile_enrichments() -> None:
    student = _student(face_embedding=b"emb")
    session = _FakeSession(
        objs=(student, _year(), _program()),
        rows={Student: [student]},
        counts=[1, 3],
    )

    page = _run(
        StudentService(session).list(
            search=None,
            program_id=None,
            year_level_id=None,
            section=None,
            is_active=None,
            sort_by=None,
            sort_dir=None,
            page=1,
            size=20,
        )
    )

    assert page.total == 1
    assert page.items[0].face_enrolled is True
    assert page.items[0].scan_count == 3
    assert page.items[0].created_at == NOW
