"""Session-specific location handling.

A professor may open a session in a room different from the offering's, or
clear that room entirely. The session's own classroom columns are the source
of truth: a cleared room stays null instead of falling back to the offering.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from features.course.model import CourseOffering
from features.session.model import Session
from features.session.schema import SessionCreate
from features.session.service import SessionService
from tests.conftest import Factories
from tests.features.session.conftest import SESSION_NOW


async def _offering(
    factories: Factories, settings: Settings, **overrides: Any
) -> tuple[dict[str, Any], SessionService]:
    program = await factories.program()
    year_level = await factories.year_level(program)
    student = await factories.student(year_level)
    professor = await factories.professor()
    admin = await factories.user(role="admin")
    course = await factories.course(session_duration_hours=1.0)
    offering = await factories.offering(
        course,
        program,
        year_level,
        classroom_name="Room 101",
        classroom_lat=14.5,
        classroom_lng=121.0,
        **overrides,
    )
    await factories.assignment(offering, professor, admin)
    await factories.enrollment(student, offering)

    stack = {
        "program": program,
        "year_level": year_level,
        "student": student,
        "professor": professor,
        "admin": admin,
        "course": course,
        "offering": offering,
    }
    return stack, SessionService(factories.db, settings)


async def test_session_with_explicit_physical_location_persists(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack, service = await _offering(factories, settings)

    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(
            offering_id=stack["offering"].id,
            classroom_override=True,
            classroom_name="Lab 2",
            classroom_lat=1.5,
            classroom_lng=2.5,
        ),
    )

    row = (
        await test_db_session.scalars(
            select(Session).where(Session.id == read.id)
        )
    ).one()
    assert row.classroom_name == "Lab 2"
    assert row.classroom_lat == 1.5
    assert row.classroom_lng == 2.5

    verified = await service.verify_code(code=read.session_code)
    assert verified.classroom_name == "Lab 2"
    assert verified.geofence.lat == 1.5
    assert verified.geofence.lng == 2.5


async def test_session_with_cleared_location_stays_null(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack, service = await _offering(factories, settings)

    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(
            offering_id=stack["offering"].id,
            classroom_override=True,
            classroom_name=None,
            classroom_lat=None,
            classroom_lng=None,
        ),
    )

    row = (
        await test_db_session.scalars(
            select(Session).where(Session.id == read.id)
        )
    ).one()
    assert row.classroom_name is None
    assert row.classroom_lat is None
    assert row.classroom_lng is None

    verified = await service.verify_code(code=read.session_code)
    assert verified.classroom_name is None
    assert verified.geofence.lat is None
    assert verified.geofence.lng is None


async def test_session_inherits_offering_location_by_default(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack, service = await _offering(factories, settings)

    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(offering_id=stack["offering"].id),
    )

    row = (
        await test_db_session.scalars(
            select(Session).where(Session.id == read.id)
        )
    ).one()
    assert row.classroom_name == "Room 101"
    assert row.classroom_lat == 14.5
    assert row.classroom_lng == 121.0


async def test_remote_session_has_no_coordinates(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack, service = await _offering(factories, settings)

    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(
            offering_id=stack["offering"].id,
            is_remote=True,
        ),
    )

    row = (
        await test_db_session.scalars(
            select(Session).where(Session.id == read.id)
        )
    ).one()
    assert row.is_remote is True
    assert row.classroom_lat is None
    assert row.classroom_lng is None


async def test_cleared_session_with_offering_coordinates_stays_null(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    # Offering keeps valid coordinates; the session must not inherit them.
    stack, service = await _offering(factories, settings)

    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(
            offering_id=stack["offering"].id,
            classroom_override=True,
        ),
    )

    row = (
        await test_db_session.scalars(
            select(Session).where(Session.id == read.id)
        )
    ).one()
    assert row.classroom_lat is None
    assert row.classroom_lng is None


async def test_omitted_fields_with_override_stay_null(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack, service = await _offering(factories, settings)

    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(
            offering_id=stack["offering"].id,
            classroom_override=True,
        ),
    )

    row = (
        await test_db_session.scalars(
            select(Session).where(Session.id == read.id)
        )
    ).one()
    assert row.classroom_name is None
    assert row.classroom_lat is None
    assert row.classroom_lng is None


async def test_attendance_geofence_disabled_for_cleared_session(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    from features.attendance.service import AttendanceService

    stack, service = await _offering(factories, settings)
    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(
            offering_id=stack["offering"].id,
            classroom_override=True,
            classroom_lat=None,
            classroom_lng=None,
        ),
    )

    # _validate_geofence returns early when coords are None.
    att_service = AttendanceService(test_db_session, settings)
    # Should not raise.
    att_service._validate_geofence(
        (
            await test_db_session.scalars(
                select(Session).where(Session.id == read.id)
            )
        ).one(),
        type("G", (), {"lat": 0.0, "lng": 0.0})(),
    )
