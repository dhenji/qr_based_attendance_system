"""Schedule exceptions on a session open (D93).

A professor may open a session for a time other than the offering's plan —
a class that starts early, a class that moves to another day. The override
lives on the session alone: the offering's recurring schedule is never
touched, and the session records that it was overridden so nothing
downstream mistakes it for the plan.

The rules these cases pin:

* an overridden date and time are stored as the session's scheduled window;
* the offering's schedule, classroom and windows are unchanged afterwards;
* a date in the past is refused, and so is a start time that has already
  gone by;
* everything the plan supplies (windows, classroom, radius) is inherited
  rather than retyped.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from features.course.model import CourseOffering
from features.session.exceptions import (
    ScheduledStartInPastException,
    SessionDateInPastException,
)
from features.session.model import Session
from features.system.model import AppSetting
from features.session.schema import SessionCreate
from features.session.service import SessionService
from tests.conftest import Factories


async def _offering(
    factories: Factories, settings: Settings, **overrides: Any
) -> tuple[dict[str, Any], SessionService]:
    program = await factories.program()
    year_level = await factories.year_level(program)
    student = await factories.student(year_level)
    professor = await factories.professor()
    admin = await factories.user(role="admin")
    course = await factories.course(session_duration_hours=1.0)
    offering = await factories.offering(course, program, year_level, **overrides)
    await factories.assignment(offering, professor, admin)
    await factories.enrollment(student, offering)

    stack: dict[str, Any] = {
        "program": program,
        "year_level": year_level,
        "student": student,
        "professor": professor,
        "admin": admin,
        "course": course,
        "offering": offering,
    }

    return stack, SessionService(factories.db, settings)


def _tomorrow() -> date:
    return datetime.now(timezone.utc).date() + timedelta(days=1)


async def test_an_override_is_stored_on_the_session(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack, service = await _offering(factories, settings)
    day = _tomorrow()

    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(
            offering_id=stack["offering"].id,
            session_date=day,
            start_time=time(10, 30),
        ),
    )

    assert read.schedule_overridden is True
    assert read.scheduled_start_time == datetime(
        day.year, day.month, day.day, 10, 30, tzinfo=timezone.utc
    )
    # The meeting keeps its length: the offering's MWF 08:00-09:00 is 60
    # minutes, so the override runs 10:30-11:30.
    assert read.scheduled_end_time == datetime(
        day.year, day.month, day.day, 11, 30, tzinfo=timezone.utc
    )


async def test_an_override_leaves_the_offering_untouched(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """The offering's recurring schedule is never written by an open."""
    stack, service = await _offering(
        factories,
        settings,
        schedule_days="MWF",
        schedule_start_time=time(8, 0),
        schedule_end_time=time(9, 0),
        classroom_name="Room 101",
        classroom_lat=14.5,
        classroom_lng=121.0,
    )
    offering_id = stack["offering"].id

    await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(
            offering_id=offering_id,
            session_date=_tomorrow(),
            start_time=time(10, 30),
        ),
    )

    offering: CourseOffering = (
        await test_db_session.scalars(
            select(CourseOffering).where(CourseOffering.id == offering_id)
        )
    ).one()

    assert offering.schedule_days == "MWF"
    assert offering.schedule_start_time == time(8, 0)
    assert offering.schedule_end_time == time(9, 0)
    assert offering.classroom_name == "Room 101"
    assert offering.classroom_lat == 14.5
    assert offering.classroom_lng == 121.0


async def test_a_date_in_the_past_is_refused(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack, service = await _offering(factories, settings)

    with pytest.raises(SessionDateInPastException) as exc_info:
        await service.create_session(
            professor_id=stack["professor"].id,
            payload=SessionCreate(
                offering_id=stack["offering"].id,
                session_date=datetime.now(timezone.utc).date() - timedelta(days=1),
            ),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "session_date_in_past"


async def test_a_start_time_already_gone_by_is_refused(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack, service = await _offering(factories, settings)
    now = datetime.now(timezone.utc)
    # Three hours ago, on today's date: past the grace window.
    gone = (now - timedelta(hours=3)).time()

    with pytest.raises(ScheduledStartInPastException) as exc_info:
        await service.create_session(
            professor_id=stack["professor"].id,
            payload=SessionCreate(
                offering_id=stack["offering"].id,
                session_date=now.date(),
                start_time=gone,
            ),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "scheduled_start_in_past"


async def test_the_plan_is_inherited_rather_than_retyped(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack, service = await _offering(
        factories,
        settings,
        default_present_window_minutes=12,
        default_late_window_minutes=8,
        classroom_name="Room 101",
        classroom_lat=14.5,
        classroom_lng=121.0,
    )

    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(offering_id=stack["offering"].id),
    )

    assert read.qr_payload.pw == 12
    assert read.qr_payload.lw == 8
    assert read.schedule_overridden is False

    row: Session = (
        await test_db_session.scalars(
            select(Session).where(Session.id == read.id)
        )
    ).one()
    assert row.classroom_name == "Room 101"
    assert row.classroom_lat == 14.5
    assert row.classroom_lng == 121.0


async def test_a_session_inherits_the_system_default_windows(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
    db_factory: Callable[..., Coroutine[Any, Any, Any]],
) -> None:
    """D93: an offering with no window of its own follows the system default.

    The `app_settings` row an administrator edits in Admin -> System
    Settings used to be dead for the windows; it is what an offering that
    never had an explicit value follows.
    """
    stack, service = await _offering(factories, settings)
    await db_factory(
        AppSetting,
        key="present_window_default",
        value="12",
    )

    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(offering_id=stack["offering"].id),
    )

    assert read.qr_payload.pw == 12
    assert read.qr_payload.lw == settings.default_late_window_minutes


async def test_a_lab_session_without_coordinates_is_refused(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    from features.session.exceptions import LabCoordinatesRequiredException

    stack, service = await _offering(factories, settings)

    with pytest.raises(LabCoordinatesRequiredException):
        await service.create_session(
            professor_id=stack["professor"].id,
            payload=SessionCreate(
                offering_id=stack["offering"].id, session_type="lab"
            ),
        )
