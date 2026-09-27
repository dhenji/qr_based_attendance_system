import asyncio
from datetime import datetime, timezone
from typing import Any

import pytest

from features.professor.exceptions import (
    ProfessorHasRecordsException,
    ProfessorNotArchivedException,
)
from features.professor.model import Professor
from features.professor.service import ProfessorService, parse_professor_roster_csv

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

    async def execute(self, stmt):
        return _FakeResult([])

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


def _professor(**overrides):
    values: dict[str, Any] = {
        "id": 7,
        "user_id": None,
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


HEADER = "first_name,middle_name,last_name,email,department"


def test_parse_professor_roster_csv_normalizes() -> None:
    rows, errors = parse_professor_roster_csv(
        f"{HEADER}\n Grace,,Hopper, GRACE@EXAMPLE.COM ,CS\n".encode()
    )

    assert errors == []
    assert len(rows) == 1
    assert rows[0].email == "grace@example.com"


def test_parse_professor_roster_csv_bad_header_reports_line_1() -> None:
    rows, errors = parse_professor_roster_csv(b"first_name,last_name\nGrace,Hopper\n")

    assert rows == []
    assert len(errors) == 1
    assert errors[0].line == 1


def test_import_roster_creates_duplicates_and_errors() -> None:
    session = _FakeSession(rows=[[]])
    content = (
        f"{HEADER}\n"
        "Alan,,Turing,alan@example.com,CS\n"
        "Alan,,Turing,alan@example.com,CS\n"
        "Bob,,Cruz,not-an-email,CS\n"
    ).encode()

    result = _run(ProfessorService(session).import_roster(content=content))

    assert result.imported == 1
    assert result.duplicates == 1
    assert [e.line for e in result.errors] == [4]
    assert len(session.added) == 1
    assert session.added[0].email == "alan@example.com"


def test_hard_delete_active_raises_not_archived() -> None:
    session = _FakeSession(objs=(_professor(is_active=True),))

    with pytest.raises(ProfessorNotArchivedException) as exc_info:
        _run(ProfessorService(session).hard_delete(professor_id=7))

    assert exc_info.value.code == "not_archived"
    assert session.deleted == []


def test_hard_delete_with_sessions_raises_has_records() -> None:
    session = _FakeSession(objs=(_professor(is_active=False),), counts=[2])

    with pytest.raises(ProfessorHasRecordsException) as exc_info:
        _run(ProfessorService(session).hard_delete(professor_id=7))

    assert exc_info.value.code == "professor_has_records"
    assert session.deleted == []


def test_hard_delete_clean_archived_deletes() -> None:
    professor = _professor(is_active=False)
    session = _FakeSession(objs=(professor,), counts=[0])

    _run(ProfessorService(session).hard_delete(professor_id=7))

    assert session.deleted == [professor]


def test_list_carries_claim_status() -> None:
    session = _FakeSession(
        objs=(_professor(),),
        rows={Professor: [_professor()]},
        counts=[1],
    )

    page = _run(
        ProfessorService(session).list(
            search=None,
            department=None,
            is_active=None,
            sort_by=None,
            sort_dir=None,
            page=1,
            size=20,
        )
    )

    assert page.total == 1
    assert page.items[0].claim_status == "Unclaimed"
    assert page.items[0].assigned_courses == []
    assert page.items[0].created_at == NOW
