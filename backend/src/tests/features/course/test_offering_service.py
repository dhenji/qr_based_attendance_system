from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from features.course.exceptions import (
    CourseNotFoundException,
    OfferingAssignmentNotFoundException,
    OfferingExistsException,
    OfferingNotFoundException,
    OfferingScheduleWindowException,
    WindowsExceedDurationException,
)
from features.course.model import Course, CourseOffering
from features.course.schema import OfferingCreate, OfferingUpdate, ProfessorAssignment
from features.course.service import CourseService, parse_enrollment_csv
from features.course_professor.exceptions import OverlappingAssignmentException
from features.course_professor.model import CourseProfessor
from features.enrollment.model import Enrollment
from features.professor.model import Professor
from features.program.exceptions import YearLevelNotFoundException
from features.program.model import Program, YearLevel
from features.student.model import Student

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
    """Dispatches on the queried entity; counts are consumed in call order.

    `rows` is either {entity: fixed list | fn(stmt) -> list} or a plain list
    consumed in scalars() call order (for multi-lookup methods like bulk).
    """

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
        # Server defaults are applied by the real DB on flush; fill them so
        # the response schemas can validate (same trick as test_roster_link).
        if getattr(obj, "id", None) is None:
            obj.id = len(self.added) + 100
        for field in ("created_at", "assigned_at", "updated_at"):
            if hasattr(obj, field) and getattr(obj, field) is None:
                setattr(obj, field, NOW)
        if hasattr(obj, "is_active") and getattr(obj, "is_active") is None:
            obj.is_active = True
        self.added.append(obj)


def _offering(**overrides):
    values: dict[str, Any] = {
        "id": 10,
        "course_id": 1,
        "program_id": 1,
        "year_level_id": 1,
        "semester": "1ST",
        "academic_year": "2026-2027",
        "sessions_per_week": 3,
        "semester_weeks": 18,
        "schedule_days": "MWF",
        "schedule_start_time": time(9, 0),
        "schedule_end_time": time(10, 0),
        "classroom_name": "Room 101",
        "classroom_lat": None,
        "classroom_lng": None,
        "default_present_window_minutes": 5,
        "default_late_window_minutes": 10,
        "is_active": True,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return CourseOffering(**values)


def _course(**overrides):
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


def _program(**overrides):
    values: dict[str, Any] = {
        "id": 1,
        "code": "BSIT",
        "name": "IT",
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
        "section": "B",
        "is_active": True,
        "face_embedding": None,
        "face_enrolled_at": None,
        "face_embedding_version": 0,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return Student(**values)


def _professor(**overrides):
    values: dict[str, Any] = {
        "id": 7,
        "user_id": None,
        "email": "prof@example.com",
        "first_name": "Grace",
        "middle_name": None,
        "last_name": "Hopper",
        "department": None,
        "is_active": True,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return Professor(**values)


def _assignment(**overrides):
    values: dict[str, Any] = {
        "offering_id": 10,
        "professor_id": 7,
        "effective_from": date(2026, 8, 1),
        "is_primary": True,
        "effective_to": None,
        "semester": "1ST",
        "assigned_by": 99,
        "assigned_at": NOW,
    }
    values.update(overrides)
    return CourseProfessor(**values)


def _enrollment(**overrides):
    values: dict[str, Any] = {
        "id": 1,
        "student_id": 1,
        "offering_id": 10,
        "semester": "1ST",
        "academic_year": "2026-2027",
        "created_at": NOW,
    }
    values.update(overrides)
    return Enrollment(**values)


def _payload(**overrides):
    values: dict[str, Any] = {
        "course_id": 1,
        "program_id": 1,
        "year_level_id": 1,
        "semester": "1ST",
        "academic_year": "2026-2027",
        "sessions_per_week": 3,
        "semester_weeks": 18,
        "schedule_days": "MWF",
        "schedule_start_time": time(9, 0),
        "schedule_end_time": time(10, 0),
    }
    values.update(overrides)
    return OfferingCreate(**values)


def _run(coro):
    return asyncio.run(coro)


# -- create ---------------------------------------------------------------


def test_create_offering_ok() -> None:
    session = _FakeSession(objs=(_course(), _program(), _year()), counts=[0])

    read = _run(CourseService(session).create_offering(payload=_payload()))

    assert read.enrolled_count == 0
    assert read.semester == "1ST"
    assert len(session.added) == 1


def test_create_offering_duplicate_409() -> None:
    session = _FakeSession(
        objs=(_course(), _program(), _year()),
        rows={CourseOffering: [_offering()]},
    )

    try:
        _run(CourseService(session).create_offering(payload=_payload()))
    except OfferingExistsException as exc:
        assert exc.code == "offering_exists"
    else:
        raise AssertionError("expected OfferingExistsException")


def test_create_offering_unknown_course_404() -> None:
    session = _FakeSession(objs=(_program(), _year()))

    try:
        _run(CourseService(session).create_offering(payload=_payload()))
    except CourseNotFoundException as exc:
        assert exc.code == "course_not_found"
    else:
        raise AssertionError("expected CourseNotFoundException")


def test_create_offering_year_program_mismatch_422() -> None:
    session = _FakeSession(
        objs=(_course(), _program(), _year(id=1, program_id=2)),
    )

    try:
        _run(CourseService(session).create_offering(payload=_payload()))
    except YearLevelNotFoundException as exc:
        assert exc.code == "year_level_not_found"
    else:
        raise AssertionError("expected YearLevelNotFoundException")


def test_create_offering_windows_exceed_422() -> None:
    session = _FakeSession(
        objs=(_course(session_duration_hours=0.5), _program(), _year()),
    )
    payload = _payload(
        default_present_window_minutes=20, default_late_window_minutes=20
    )

    try:
        _run(CourseService(session).create_offering(payload=payload))
    except WindowsExceedDurationException as exc:
        assert exc.code == "windows_exceed_duration"
    else:
        raise AssertionError("expected WindowsExceedDurationException")


# -- get / archive / update ------------------------------------------------


def test_get_offering_not_found_404() -> None:
    session = _FakeSession()

    try:
        _run(CourseService(session).get_offering(offering_id=999))
    except OfferingNotFoundException as exc:
        assert exc.code == "offering_not_found"
    else:
        raise AssertionError("expected OfferingNotFoundException")


def test_archive_offering_flips_flag() -> None:
    offering = _offering()
    session = _FakeSession(objs=(offering,))

    _run(CourseService(session).archive_offering(offering_id=10))

    assert offering.is_active is False


def test_update_offering_rejects_bad_times_at_the_schema() -> None:
    """Both times in the body and inverted: rejected before the service.

    `OfferingUpdate`'s validator sees both halves, so this never reaches the
    service. Kept as a 422 (Pydantic's) rather than the bare `ValueError`
    the service used to raise for the case it could actually see.
    """

    with pytest.raises(ValidationError):
        OfferingUpdate(
            schedule_start_time=time(11, 0), schedule_end_time=time(10, 0)
        )


def test_update_offering_rejects_a_start_moved_past_the_stored_end() -> None:
    """Only the start is sent, and it lands after the *stored* end.

    This is the case the schema validator cannot see - it only knows the
    fields in the request body. It used to fall through to the service,
    which raised a bare `ValueError` that nothing caught, so the route
    returned a 500 instead of the contract's 422.
    """

    offering = _offering()
    session = _FakeSession(objs=(offering, _course()))

    with pytest.raises(OfferingScheduleWindowException) as excinfo:
        _run(
            CourseService(session).update_offering(
                offering_id=10,
                payload=OfferingUpdate(schedule_start_time=time(18, 0)),
            )
        )

    assert excinfo.value.status_code == 422
    assert excinfo.value.code == "invalid_schedule_window"
    # And the rejection must not have dirtied the row.
    assert offering.schedule_start_time == time(9, 0)


# -- assignments -------------------------------------------------------------


def test_assign_professor_ok() -> None:
    session = _FakeSession(objs=(_offering(), _professor()))
    payload = ProfessorAssignment(
        professor_id=7,
        is_primary=True,
        effective_from=date(2026, 8, 1),
        semester="1ST",
    )

    read = _run(
        CourseService(session).assign_professor(
            offering_id=10, payload=payload, assigned_by=99
        )
    )

    assert read.offering_id == 10
    assert read.assigned_by == 99


def test_assign_professor_overlap_raises() -> None:
    session = _FakeSession(
        objs=(_offering(), _professor()),
        rows={CourseProfessor: [_assignment()]},
    )
    payload = ProfessorAssignment(
        professor_id=7,
        is_primary=False,
        effective_from=date(2026, 9, 1),
        semester="1ST",
    )

    try:
        _run(
            CourseService(session).assign_professor(
                offering_id=10, payload=payload, assigned_by=99
            )
        )
    except OverlappingAssignmentException as exc:
        assert exc.code == "overlapping_assignment"
    else:
        raise AssertionError("expected OverlappingAssignmentException")


def test_remove_professor_sets_today() -> None:
    session = _FakeSession(objs=(_offering(),), rows={CourseProfessor: [_assignment()]})

    effective_to = _run(
        CourseService(session).remove_professor(offering_id=10, professor_id=7)
    )

    assert effective_to == date.today()


def test_remove_professor_missing_404() -> None:
    session = _FakeSession(objs=(_offering(),))

    try:
        _run(CourseService(session).remove_professor(offering_id=10, professor_id=7))
    except OfferingAssignmentNotFoundException as exc:
        assert exc.code == "assignment_not_found"
    else:
        raise AssertionError("expected OfferingAssignmentNotFoundException")


# -- bulk enroll ---------------------------------------------------------------


BULK_CSV = """student_id,first_name,middle_name,last_name,email,program_code,year_level,section
S001,Ada,,Lovelace,ada@example.com,BSIT,1,A
S002,Grace,,Hopper,grace@example.com,BSIT,1,A
S999,Alan,,Turing,alan@example.com,BSIT,1,B
S001,Ada,,Lovelace,wrong@example.com,BSIT,1,A
"""


def test_bulk_enroll_summary_counts() -> None:
    ada = _student()
    grace = _student(
        id=2,
        student_id="S002",
        email="grace@example.com",
        first_name="Grace",
        last_name="Hopper",
    )
    session = _FakeSession(
        objs=(_offering(), _program(), ada, grace),
        # scalars() calls in order: Student, Enrollment per CSV row.
        rows=[[ada], [], [grace], [_enrollment(id=9, student_id=2)], [], [ada]],
    )

    result = _run(
        CourseService(session).bulk_enroll(offering_id=10, content=BULK_CSV.encode())
    )

    assert result.enrolled == 1
    assert result.skipped == 1
    assert [e.line for e in result.errors] == [4, 5]
    assert ada.section == "A"


def test_bulk_enroll_bad_header_reports_line_1() -> None:
    session = _FakeSession(objs=(_offering(), _program()))

    result = _run(
        CourseService(session).bulk_enroll(
            offering_id=10, content=b"student_id,first_name\nS001,Ada\n"
        )
    )

    assert result.enrolled == 0
    assert result.errors and result.errors[0].line == 1


def test_parse_csv_empty_file() -> None:
    rows, errors = parse_enrollment_csv(b"")

    assert rows == []
    assert len(errors) == 1


# -- roster ----------------------------------------------------------------------


def test_roster_maps_items() -> None:
    ada = _student()
    session = _FakeSession(
        objs=(_offering(), ada),
        rows={Enrollment: [_enrollment()]},
        counts=[1],
    )

    page = _run(
        CourseService(session).get_roster(offering_id=10, section="B", page=1, size=20)
    )

    assert page.total == 1
    assert len(page.items) == 1
    assert page.items[0].student_id == "S001"
    assert page.items[0].name == "Ada Lovelace"
    assert page.items[0].section == "B"
    assert page.items[0].enrolled_at == NOW
