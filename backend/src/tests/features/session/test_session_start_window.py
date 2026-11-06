"""The open window: a session may only be opened while its class runs (D94).

The rules these cases pin:

* an open inside the window succeeds, and one outside it does not;
* the window is *today's* occurrence of the meeting, extended by the
  early-open and late-open grace;
* an offering with no meeting for that session type is never gated;
* an explicit override is the way past the window, and it carries its own
  validation;
* the row records what actually happened: when the session was opened, the
  start it would have carried, and why it moved.

The clock is the package's pinned one (a Wednesday 08:30 UTC), and the tests
that need another moment pass it to the service.
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
    SessionOutsideScheduledTimeException,
)
from features.session.model import Session
from features.session.schema import SessionCreate
from features.session.service import SessionService
from features.system.model import AppSetting
from shared.enums import UserRole
from tests.conftest import Factories
from tests.features.session.conftest import SESSION_NOW

SESSIONS = "/api/professor/sessions"
PLAN = "/api/professor/offerings/{offering_id}/session-plan"

# The class the default offering meets: MWF 08:00-09:00. The pinned clock is
# a Wednesday 08:30 UTC, so it is inside that window.
CLASS_START = time(8, 0)
CLASS_END = time(9, 0)


async def _offering(
    factories: Factories, settings: Settings, **overrides: Any
) -> tuple[dict[str, Any], SessionService]:
    program = await factories.program()
    year_level = await factories.year_level(program)
    student = await factories.student(year_level)
    professor = await factories.professor()
    admin = await factories.user(role="admin")
    course = await factories.course(session_duration_hours=1.0)
    values: dict[str, Any] = {
        "schedule_days": "MWF",
        "schedule_start_time": CLASS_START,
        "schedule_end_time": CLASS_END,
    }
    values.update(overrides)
    offering = await factories.offering(course, program, year_level, **values)
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


# --- the window ------------------------------------------------------------


async def test_an_open_inside_the_window_succeeds(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack, service = await _offering(factories, settings)

    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(offering_id=stack["offering"].id),
        now=SESSION_NOW,
    )

    assert read.id
    assert read.schedule_overridden is False


async def test_an_open_before_the_class_is_refused(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """Too early: the class has not started and the grace does not reach."""

    stack, service = await _offering(factories, settings)

    with pytest.raises(SessionOutsideScheduledTimeException) as exc_info:
        await service.create_session(
            professor_id=stack["professor"].id,
            payload=SessionCreate(offering_id=stack["offering"].id),
            now=SESSION_NOW.replace(hour=6),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "session_outside_scheduled_time"
    assert "outside its scheduled time" in exc_info.value.message


async def test_an_open_after_the_class_ended_is_refused(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack, service = await _offering(factories, settings)

    with pytest.raises(SessionOutsideScheduledTimeException):
        await service.create_session(
            professor_id=stack["professor"].id,
            payload=SessionCreate(offering_id=stack["offering"].id),
            now=SESSION_NOW.replace(hour=10),
        )


async def test_an_open_on_a_day_without_a_class_is_refused(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """Tuesday is not one of the offering's meeting days."""

    stack, service = await _offering(factories, settings)
    tuesday = SESSION_NOW - timedelta(days=1)

    with pytest.raises(SessionOutsideScheduledTimeException) as exc_info:
        await service.create_session(
            professor_id=stack["professor"].id,
            payload=SessionCreate(offering_id=stack["offering"].id),
            now=tuesday,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "session_outside_scheduled_time"
    assert "no class today" in exc_info.value.message


async def test_the_early_open_grace_admits_an_early_arrival(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """Fifteen minutes before the class is still the class."""

    stack, service = await _offering(factories, settings)

    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(offering_id=stack["offering"].id),
        now=SESSION_NOW - timedelta(minutes=15),
    )

    assert read.id


async def test_the_late_open_grace_admits_a_class_still_running(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
    db_factory: Callable[..., Coroutine[Any, Any, Any]],
) -> None:
    """The late grace is an app setting, so an administrator can widen it."""

    stack, service = await _offering(factories, settings)
    await db_factory(AppSetting, key="session_late_open_minutes", value="15")

    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(
            offering_id=stack["offering"].id, duration_minutes=15
        ),
        now=SESSION_NOW + timedelta(minutes=40),
    )

    assert read.id


async def test_a_zero_late_grace_row_is_honoured(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
    db_factory: Callable[..., Coroutine[Any, Any, Any]],
) -> None:
    """Zero is a legal value: it means "no late opening"."""

    stack, service = await _offering(factories, settings)
    await db_factory(AppSetting, key="session_late_open_minutes", value="0")

    with pytest.raises(SessionOutsideScheduledTimeException):
        await service.create_session(
            professor_id=stack["professor"].id,
            payload=SessionCreate(offering_id=stack["offering"].id),
            now=SESSION_NOW + timedelta(minutes=70),
        )


async def test_an_offering_with_no_meeting_is_not_gated(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """Nothing to be outside of: the session starts now, as it always did."""

    stack, service = await _offering(
        factories, settings, schedule_days=""
    )

    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(offering_id=stack["offering"].id),
        now=SESSION_NOW.replace(hour=3),
    )

    assert read.id


async def test_the_window_follows_the_institution_timezone(
    test_db_session: AsyncSession,
    factories: Factories,
) -> None:
    """A class at 08:00 in Manila is at 00:00 UTC the same day."""

    manila = Settings(
        debug=True,
        jwt_secret="test-secret-0123456789abcdef",
        institution_timezone="Asia/Manila",
    )
    stack, service = await _offering(factories, manila)

    # 08:30 in Manila is 00:30 UTC.
    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(offering_id=stack["offering"].id),
        now=datetime(2026, 10, 21, 0, 0, tzinfo=timezone.utc),
    )

    assert read.id


# --- the override ----------------------------------------------------------


async def test_an_override_is_the_way_past_the_window(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack, service = await _offering(factories, settings)

    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(
            offering_id=stack["offering"].id,
            session_date=SESSION_NOW.date(),
            start_time=time(10, 30),
            override_reason="The class was moved to the afternoon.",
        ),
        now=SESSION_NOW.replace(hour=10),
    )

    assert read.schedule_overridden is True
    assert read.scheduled_start_time == datetime(
        2026, 10, 21, 10, 30, tzinfo=timezone.utc
    )
    assert read.override_reason == "The class was moved to the afternoon."


async def test_the_row_records_what_actually_happened(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """The open, the start it would have carried, and the account behind it."""

    stack, service = await _offering(factories, settings)
    professor_user = await factories.user(role=UserRole.PROFESSOR.value)

    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(
            offering_id=stack["offering"].id,
            session_date=SESSION_NOW.date(),
            start_time=time(10, 30),
            override_reason="Late start.",
        ),
        actor_id=professor_user.id,
        now=SESSION_NOW.replace(hour=10),
    )

    row: Session = (
        await test_db_session.scalars(select(Session).where(Session.id == read.id))
    ).one()

    assert row.actual_start_time == SESSION_NOW.replace(hour=10)
    # The plan's own start, kept because the professor moved the class.
    assert row.original_scheduled_start_time == datetime(
        2026, 10, 21, 8, 0, tzinfo=timezone.utc
    )
    assert row.created_by == professor_user.id
    assert row.override_reason == "Late start."


async def test_a_session_without_an_override_keeps_the_original_start_empty(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack, service = await _offering(factories, settings)

    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(offering_id=stack["offering"].id),
        now=SESSION_NOW,
    )

    row: Session = (
        await test_db_session.scalars(select(Session).where(Session.id == read.id))
    ).one()

    assert row.original_scheduled_start_time is None
    assert row.override_reason is None
    assert row.actual_start_time == SESSION_NOW


async def test_an_override_in_the_past_is_still_refused(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """The window is not the only rule: the override keeps its own."""

    stack, service = await _offering(factories, settings)

    with pytest.raises(SessionDateInPastException):
        await service.create_session(
            professor_id=stack["professor"].id,
            payload=SessionCreate(
                offering_id=stack["offering"].id,
                session_date=SESSION_NOW.date() - timedelta(days=1),
            ),
            now=SESSION_NOW,
        )

    with pytest.raises(ScheduledStartInPastException):
        await service.create_session(
            professor_id=stack["professor"].id,
            payload=SessionCreate(
                offering_id=stack["offering"].id,
                session_date=SESSION_NOW.date(),
                start_time=(SESSION_NOW - timedelta(hours=3)).time(),
            ),
            now=SESSION_NOW,
        )


# --- over HTTP -------------------------------------------------------------


async def _headers(
    auth_headers: Any, factories: Factories, offering: Any
) -> dict[str, str]:
    professor_user = await factories.user(role=UserRole.PROFESSOR.value)
    professor = await factories.professor(professor_user)
    assigner = await factories.user(role=UserRole.ADMIN.value)
    await factories.assignment(offering, professor, assigner)
    return await auth_headers(professor_user)


async def test_the_plan_endpoint_carries_the_window(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: Any,
) -> None:
    program = await factories.program()
    year_level = await factories.year_level(program)
    course = await factories.course()
    offering = await factories.offering(
        course,
        program,
        year_level,
        schedule_days="MWF",
        schedule_start_time=CLASS_START,
        schedule_end_time=CLASS_END,
    )
    headers = await _headers(auth_headers, factories, offering)
    await test_db_session.commit()

    response = await api_client.get(
        PLAN.format(offering_id=offering.id), headers=headers
    )

    assert response.status_code == 200, response.text
    window = response.json()["start_window"]
    assert window["permitted"] is True
    assert window["reason"] is None
    assert window["start_time"] == "08:00:00"
    assert window["end_time"] == "09:00:00"
    assert window["timezone"] == "UTC"
    assert window["current_time"] is not None


async def test_an_open_outside_the_window_is_422_over_http(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: Any,
) -> None:
    """A class in the evening is not the class of a Wednesday morning."""

    program = await factories.program()
    year_level = await factories.year_level(program)
    course = await factories.course()
    offering = await factories.offering(
        course,
        program,
        year_level,
        schedule_days="MWF",
        schedule_start_time=time(20, 0),
        schedule_end_time=time(21, 0),
    )
    headers = await _headers(auth_headers, factories, offering)
    await test_db_session.commit()

    response = await api_client.post(
        SESSIONS, json={"offering_id": offering.id}, headers=headers
    )

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "session_outside_scheduled_time"
    assert "outside its scheduled time" in detail["message"]


async def test_a_second_open_is_still_refused(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: Any,
) -> None:
    """The double submit is refused by the active-session guard (D94)."""

    program = await factories.program()
    year_level = await factories.year_level(program)
    course = await factories.course()
    offering = await factories.offering(
        course,
        program,
        year_level,
        schedule_days="MWF",
        schedule_start_time=CLASS_START,
        schedule_end_time=CLASS_END,
    )
    headers = await _headers(auth_headers, factories, offering)
    await test_db_session.commit()

    first = await api_client.post(
        SESSIONS, json={"offering_id": offering.id}, headers=headers
    )
    second = await api_client.post(
        SESSIONS, json={"offering_id": offering.id}, headers=headers
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 409, second.text
    assert second.json()["detail"]["code"] == "session_already_active"


async def test_an_override_opens_over_http(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: Any,
) -> None:
    program = await factories.program()
    year_level = await factories.year_level(program)
    course = await factories.course()
    offering = await factories.offering(
        course,
        program,
        year_level,
        schedule_days="MWF",
        schedule_start_time=time(20, 0),
        schedule_end_time=time(21, 0),
    )
    headers = await _headers(auth_headers, factories, offering)
    await test_db_session.commit()

    response = await api_client.post(
        SESSIONS,
        json={
            "offering_id": offering.id,
            "session_date": SESSION_NOW.date().isoformat(),
            "start_time": "10:30:00",
            "override_reason": "Ran late.",
        },
        headers=headers,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["schedule_overridden"] is True
    assert body["override_reason"] == "Ran late."
    assert body["actual_start_time"] is not None
    assert body["original_scheduled_start_time"] is not None
