from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from features.program.service import ProgramService, parse_program_csv
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


HEADER = "code,name,description,total_years"


def test_parse_program_csv_normalizes() -> None:
    rows, errors = parse_program_csv(
        f"{HEADER}\n bscs , BS Computer Science,,4\n".encode()
    )

    assert errors == []
    assert len(rows) == 1
    assert rows[0].code == "BSCS"
    assert rows[0].total_years == "4"


def test_parse_program_csv_bad_header_reports_line_1() -> None:
    rows, errors = parse_program_csv(b"code,name\nBSCS,BS CS\n")

    assert rows == []
    assert len(errors) == 1
    assert errors[0].line == 1


def test_import_roster_creates_duplicates_and_errors() -> None:
    session = _FakeSession(rows=[[], [], [], []])
    content = (
        f"{HEADER}\n"
        "BSCS,BS Computer Science,,4\n"
        "BSCS,BS Computer Science,,4\n"
        "BSIT,,Some desc,4\n"
        "BSECE,BS ECE,,99\n"
    ).encode()

    result = _run(ProgramService(session).import_roster(content=content, actor_id=None))

    assert result.imported == 1
    assert result.duplicates == 1
    assert [e.line for e in result.errors] == [4, 5]
    assert len(session.added) == 2
    assert session.added[0].code == "BSCS"
    assert session.added[0].total_years == 4
    audit = session.added[1]
    assert isinstance(audit, AuditLog)
    assert audit.action == AuditAction.IMPORT
    assert audit.entity_type == AuditEntity.PROGRAM
    assert audit.entity_id is None
    assert audit.new_value == {"imported": 1, "duplicates": 1, "errors": 2}


def test_import_roster_duplicate_against_database() -> None:
    from features.program.model import Program

    existing = Program(
        id=1,
        code="BSCS",
        name="BS Computer Science",
        description=None,
        total_years=4,
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
    )
    session = _FakeSession(rows=[[existing]])
    content = (f"{HEADER}\nBSCS,BS Computer Science,,4\n").encode()

    result = _run(ProgramService(session).import_roster(content=content, actor_id=None))

    assert result.imported == 0
    assert result.duplicates == 1
    assert result.errors == []
    assert len(session.added) == 1  # audit row only
    assert isinstance(session.added[0], AuditLog)


def test_import_roster_empty_description_becomes_none() -> None:
    session = _FakeSession(rows=[[]])
    content = (f"{HEADER}\nBSIT,BS IT,   ,4\n").encode()

    result = _run(ProgramService(session).import_roster(content=content, actor_id=None))

    assert result.imported == 1
    assert session.added[0].description is None
