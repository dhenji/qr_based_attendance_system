from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import pytest

from core.config import Settings
from features.attendance.model import Attendance
from features.course.exceptions import (
    OfferingNotFoundException,
    WindowsExceedDurationException,
)
from features.excuse.exceptions import ProfessorNotAssignedException
from features.course.model import Course, CourseOffering
from features.course_professor.model import CourseProfessor
from features.session.exceptions import (
    SessionAlreadyActiveException,
    SessionNotFoundException,
)
from features.session.model import Session
from features.session.schema import SessionCreate
from features.session.service import SessionService
from features.student.model import Student
from features.sync.model import SyncQueue

NOW = datetime.now(timezone.utc)
SETTINGS = Settings(debug=True, jwt_secret="test-secret-0123456789abcdef")


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def one_or_none(self):
        assert len(self._rows) <= 1
        return self._rows[0] if self._rows else None


class _FakeSession:
    """Dispatches on the queried entity; counts consumed in call order."""

    def __init__(
        self,
        *,
        objs: tuple = (),
        rows: dict | list | None = None,
        counts: list[int | None] | None = None,
    ):
        self.store = {(type(o), getattr(o, "id", None)): o for o in objs}
        self.rows = rows if rows is not None else {}
        self.counts = list(counts or [])
        self.added = []

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
        for field in ("created_at", "assigned_at", "updated_at"):
            if hasattr(obj, field) and getattr(obj, field) is None:
                setattr(obj, field, datetime.now(timezone.utc))
        self.added.append(obj)


def _run(coro):
    return asyncio.run(coro)


def _offering(**overrides: Any) -> CourseOffering:
    values: dict[str, Any] = {
        "id": 10,
        "course_id": 1,
        "program_id": 1,
        "year_level_id": 1,
        "semester": "1ST",
        "academic_year": "2026-2027",
        "sessions_per_week": 3,
        "schedule_days": "MWF",
        # The same window the factory offering uses, so the pinned clock of
        # this package falls inside it (D94).
        "schedule_start_time": time(8, 0),
        "schedule_end_time": time(9, 0),
        "classroom_name": "Room 101",
        "classroom_lat": 14.5,
        "classroom_lng": 121.0,
        "default_present_window_minutes": 5,
        "default_late_window_minutes": 10,
        "is_active": True,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return CourseOffering(**values)


def _course(**overrides: Any) -> Course:
    values: dict[str, Any] = {
        "id": 1,
        "course_code": "CS101",
        "course_name": "Intro",
        "units": 3,
        "session_duration_hours": 2.0,
        "is_active": True,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return Course(**values)


def _assignment(**overrides: Any) -> CourseProfessor:
    values: dict[str, Any] = {
        "offering_id": 10,
        "professor_id": 3,
        "effective_from": date.today() - timedelta(days=1),
        "effective_to": None,
        "is_primary": True,
        "assigned_by": 1,
        "created_at": NOW,
    }
    values.update(overrides)
    return CourseProfessor(**values)


def _session(**overrides: Any) -> Session:
    values: dict[str, Any] = {
        "id": 50,
        "offering_id": 10,
        "professor_id": 3,
        "session_code": "ABCDEFGH",
        "duration_minutes": 120,
        "present_window_minutes": 5,
        "late_window_minutes": 10,
        "scheduled_start_time": NOW,
        "scheduled_end_time": NOW + timedelta(minutes=120),
        "expires_at": NOW + timedelta(minutes=120),
        "classroom_radius_meters": 50,
        "classroom_name": "Room 101",
        "classroom_lat": 14.5,
        "classroom_lng": 121.0,
        "created_at": NOW,
    }
    values.update(overrides)
    return Session(**values)


def _student(id: int, number: str, **overrides: Any) -> Student:
    values: dict[str, Any] = {
        "id": id,
        "student_id": number,
        "email": f"{number.lower()}@example.com",
        "first_name": "Test",
        "last_name": f"Student{id}",
        "section": "A",
        "is_active": True,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return Student(**values)


def _attendance(id: int, student_id: int, status: str, **overrides: Any) -> Attendance:
    values: dict[str, Any] = {
        "id": id,
        "student_id": student_id,
        "session_id": 50,
        "timestamp": NOW,
        "validation_status": status,
        "sync_status": "synced",
        "created_at": NOW,
    }
    values.update(overrides)
    return Attendance(**values)


def test_create_session_copies_offering_defaults() -> None:
    offering = _offering()
    session = _FakeSession(
        objs=(offering, _course()),
        rows={CourseProfessor: [_assignment()]},
        counts=[None],
    )
    service = SessionService(session, SETTINGS)  # type: ignore[arg-type]
    before = datetime.now(timezone.utc)

    read = _run(
        service.create_session(professor_id=3, payload=SessionCreate(offering_id=10))
    )

    assert read.offering_id == 10
    assert len(read.session_code) == 8
    assert read.qr_payload.offering == 10
    assert read.qr_payload.radius == 50
    assert read.qr_payload.pw == 5
    assert read.qr_payload.lw == 10
    # D93: the offering's own meeting (09:00-10:00) is the plan, so the
    # session carries that window rather than "now" and "now + duration".
    assert read.plan_source == "offering_legacy"
    assert read.scheduled_end_time - read.scheduled_start_time == timedelta(minutes=60)
    assert not read.schedule_overridden
    # The fake stamps created_at at insert time (~service now, never stale).
    expected = read.created_at + timedelta(minutes=60)

    if read.scheduled_end_time > read.created_at:
        expected = min(expected, read.scheduled_end_time)

    assert abs(read.expires_at - expected) < timedelta(seconds=1)


def _active_session(**overrides: Any) -> Session:
    values: dict[str, Any] = {
        "id": 100,
        "offering_id": 10,
        "professor_id": 3,
        "session_code": "A7X-9K2M",
        "duration_minutes": 60,
        "present_window_minutes": 5,
        "late_window_minutes": 10,
        "scheduled_start_time": NOW - timedelta(minutes=10),
        "scheduled_end_time": NOW + timedelta(minutes=50),
        "expires_at": NOW + timedelta(minutes=50),
        "classroom_radius_meters": 50,
        "classroom_name": "Room 101",
        "classroom_lat": 14.5,
        "classroom_lng": 121.0,
        "session_type": "lecture",
        "is_remote": False,
        "geofence_enabled": True,
        "created_at": NOW,
    }
    values.update(overrides)
    return Session(**values)


def test_create_session_rejects_second_active() -> None:
    session = _FakeSession(
        objs=(_offering(), _course()),
        rows={CourseProfessor: [_assignment()]},
        counts=[_active_session()],
    )
    service = SessionService(session, SETTINGS)  # type: ignore[arg-type]

    with pytest.raises(SessionAlreadyActiveException) as excinfo:
        _run(
            service.create_session(
                professor_id=3, payload=SessionCreate(offering_id=10)
            )
        )

    # D96: the message names the course and the active session's window
    # rather than the offering id, so a professor sees why instead of
    # decoding a number.
    assert "CS101" in excinfo.value.message
    assert "08:" in excinfo.value.message
    assert "–" in excinfo.value.message


def test_create_session_rejects_windows_exceeding_duration() -> None:
    # The schema validator only fires when all three fields are provided, so
    # drive the service-level guard through the offering defaults instead.
    session = _FakeSession(
        objs=(
            _offering(
                default_present_window_minutes=40,
                default_late_window_minutes=30,
            ),
            _course(),
        ),
        rows={CourseProfessor: [_assignment()]},
        counts=[None],
    )
    service = SessionService(session, SETTINGS)  # type: ignore[arg-type]

    with pytest.raises(WindowsExceedDurationException):
        _run(
            service.create_session(
                professor_id=3,
                payload=SessionCreate(offering_id=10, duration_minutes=60),
            )
        )


def test_create_session_requires_assignment() -> None:
    session = _FakeSession(objs=(_offering(), _course()), rows={}, counts=[None])
    service = SessionService(session, SETTINGS)  # type: ignore[arg-type]

    with pytest.raises(ProfessorNotAssignedException):
        _run(
            service.create_session(
                professor_id=9, payload=SessionCreate(offering_id=10)
            )
        )


def test_create_session_missing_offering() -> None:
    session = _FakeSession(objs=(), rows={}, counts=[None])
    service = SessionService(session, SETTINGS)  # type: ignore[arg-type]

    with pytest.raises(OfferingNotFoundException):
        _run(
            service.create_session(
                professor_id=3, payload=SessionCreate(offering_id=404)
            )
        )


def test_get_active_session_counts_tiles_and_banner() -> None:
    row = _session()
    students = [_student(1, "S001"), _student(2, "S002"), _student(3, "S003")]
    records = [
        _attendance(1, 1, "present"),
        _attendance(2, 2, "rejected"),
    ]
    queued = [
        SyncQueue(id=1, record_data={"session_id": 50}, status="pending"),
        SyncQueue(id=2, record_data={"session_id": 99}, status="pending"),
        SyncQueue(id=3, record_data={}, status="pending"),
    ]
    session = _FakeSession(
        objs=(row,),
        rows={Student: students, Attendance: records, SyncQueue: queued},
    )
    service = SessionService(session, SETTINGS)  # type: ignore[arg-type]

    active = _run(service.get_active_session(session_id=50, professor_id=3))

    assert active.status == "active"
    assert active.enrolled_count == 3
    assert active.remaining == 1
    assert active.counts.present == 1
    assert active.pending_sync_count == 1
    assert active.scan_window_remaining > 3500
    by_number = {s.student_number: s for s in active.students}
    assert by_number["S001"].status == "present"
    assert by_number["S002"].status == "rejected"
    assert by_number["S003"].status == "absent"


def test_get_active_session_rejects_a_professor_outside_the_team() -> None:
    """No ownership and no assignment: the session is not theirs to project."""
    session = _FakeSession(objs=(_session(),), rows={CourseProfessor: []})
    service = SessionService(session, SETTINGS)  # type: ignore[arg-type]

    with pytest.raises(ProfessorNotAssignedException):
        _run(service.get_active_session(session_id=50, professor_id=999))


def test_get_active_session_admits_a_coteacher() -> None:
    """Someone else opened it, but the offering is assigned to this professor."""
    session = _FakeSession(
        objs=(_session(),),
        rows={CourseProfessor: [_assignment(offering_id=10, professor_id=999)]},
    )
    service = SessionService(session, SETTINGS)  # type: ignore[arg-type]

    active = _run(service.get_active_session(session_id=50, professor_id=999))

    assert active.id == 50


def test_a_missing_session_is_not_reported_as_a_missing_assignment() -> None:
    """A wrong id must stay a 404 on the session, whatever the professor holds."""
    session = _FakeSession(objs=(), rows={CourseProfessor: [_assignment()]})
    service = SessionService(session, SETTINGS)  # type: ignore[arg-type]

    with pytest.raises(SessionNotFoundException):
        _run(service.get_active_session(session_id=50, professor_id=999))


def test_close_session_is_idempotent() -> None:
    row = _session()
    session = _FakeSession(
        objs=(row,),
        rows={Attendance: [_attendance(1, 1, "present")]},
    )
    service = SessionService(session, SETTINGS)  # type: ignore[arg-type]

    first = _run(service.close_session(session_id=50, professor_id=3))
    second = _run(service.close_session(session_id=50, professor_id=3))

    assert first.status == "closed"
    assert first.final_counts.present == 1
    assert second.status == "closed"
    assert second.final_counts.present == 1
    assert row.expires_at is not None
    assert row.expires_at <= datetime.now(timezone.utc)


def test_session_history_computes_both_rates() -> None:
    first = _session(id=50, session_code="AAAA", created_at=NOW - timedelta(days=2))
    second = _session(id=51, session_code="BBBB", created_at=NOW - timedelta(days=1))
    session = _FakeSession(
        objs=(),
        rows=[
            [first, second],
            [_attendance(1, 1, "present")],
            [_attendance(2, 1, "late"), _attendance(3, 2, "excused")],
        ],
        counts=[2, 2],
    )
    service = SessionService(session, SETTINGS)  # type: ignore[arg-type]

    history = _run(service.get_session_history(professor_id=3))

    assert history.total == 2
    older, newer = history.items[1], history.items[0]
    assert older.compliance_rate == 0.5
    assert older.participation_rate == 0.5
    assert newer.compliance_rate == 0.0
    assert newer.participation_rate == 1.0


def test_professor_attendance_maps_student_columns() -> None:
    record = _attendance(
        7, 1, "present", original_status="late", scanned_via="qr_camera"
    )
    session = _FakeSession(
        objs=(),
        rows={Attendance: [record], Student: [_student(1, "S001")]},
        counts=[1],
    )
    service = SessionService(session, SETTINGS)  # type: ignore[arg-type]

    page = _run(service.get_professor_attendance(professor_id=3))

    assert page.total == 1
    item = page.items[0]
    assert item.student_number == "S001"
    assert item.student_name == "Test Student1"
    assert item.session_id == 50
    assert item.status == "present"
    assert item.original_status == "late"
    assert item.scanned_via == "qr_camera"
