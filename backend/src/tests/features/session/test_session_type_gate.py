"""The type gate: an offering declares what it meets (D95).

An offering's active meeting components are what it meets (D77), so a
session of a type it does not configure is refused. The rules these cases
pin:

* a laboratory session needs a laboratory meeting, and a lecture session
  needs a lecture one;
* an offering with no configured meeting meets a lecture — D77's migration
  gave every existing offering a lecture component, and the lone active
  meeting is what the offering's legacy schedule columns mirror;
* the list of openable types is the same everywhere it is reported: the
  admin offering read, the professor's course list, the session plan and the
  session open.

The clock is the package's pinned one (a Wednesday 08:30 UTC), so a meeting
scheduled for that hour is inside its window (D94).
"""

from __future__ import annotations

from datetime import time
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings

from shared.enums import UserRole

from features.course.model import OfferingComponent
from features.session.exceptions import SessionTypeNotConfiguredException
from features.session.schema import SessionCreate
from features.session.service import SessionService
from tests.conftest import Factories
from tests.features.session.conftest import SESSION_NOW

SESSIONS = "/api/professor/sessions"
PLAN = "/api/professor/offerings/{offering_id}/session-plan"
COURSES = "/api/professor/courses"

# The suite's pinned clock is Wednesday 08:30 UTC, so a meeting scheduled
# for 08:00-09:00 on "W" is inside its window.
MEETING_START = time(8, 0)
MEETING_END = time(9, 0)


async def _offering(
    factories: Factories,
    settings: Settings,
    *,
    components: list[str] | None = None,
    units: int | None = None,
) -> tuple[dict[str, Any], SessionService]:
    """An assigned offering, with the given meeting components.

    `components` lists the session types the offering meets; each one is a
    single hour, so the course's units are the number of them (D82).
    """
    program = await factories.program()
    year_level = await factories.year_level(program)
    student = await factories.student(year_level)
    professor = await factories.professor()
    admin = await factories.user(role="admin")
    course = await factories.course(session_duration_hours=1.0)
    offering = await factories.offering(course, program, year_level)
    await factories.assignment(offering, professor, admin)
    await factories.enrollment(student, offering)

    meetings = components or []
    course.units = units if units is not None else len(meetings)
    await factories.db.flush()

    for session_type in meetings:
        factories.db.add(
            OfferingComponent(
                offering_id=offering.id,
                session_type=session_type,
                schedule_days="W",
                schedule_start_time=MEETING_START,
                schedule_end_time=MEETING_END,
                classroom_name="Room 101",
                classroom_lat=14.5,
                classroom_lng=121.0,
                is_active=True,
            )
        )

    await factories.db.flush()

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


async def _headers(
    auth_headers: Any, factories: Factories, offering: Any
) -> dict[str, str]:
    professor_user = await factories.user(role=UserRole.PROFESSOR.value)
    professor = await factories.professor(professor_user)
    assigner = await factories.user(role=UserRole.ADMIN.value)
    await factories.assignment(offering, professor, assigner)
    return await auth_headers(professor_user)


# --- the gate --------------------------------------------------------------


async def test_a_lab_session_needs_a_lab_meeting(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """A lecture-only offering refuses a laboratory session."""

    stack, service = await _offering(factories, settings, components=["lecture"])

    with pytest.raises(SessionTypeNotConfiguredException) as exc_info:
        await service.create_session(
            professor_id=stack["professor"].id,
            payload=SessionCreate(offering_id=stack["offering"].id, session_type="lab"),
            now=SESSION_NOW,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "session_type_not_configured"
    assert exc_info.value.field == "session_type"
    assert "no laboratory session" in exc_info.value.message
    assert "meets a lecture" in exc_info.value.message


async def test_a_lecture_session_needs_a_lecture_meeting(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """A laboratory-only offering refuses a lecture session."""

    stack, service = await _offering(factories, settings, components=["lab"])

    with pytest.raises(SessionTypeNotConfiguredException) as exc_info:
        await service.create_session(
            professor_id=stack["professor"].id,
            payload=SessionCreate(offering_id=stack["offering"].id),
            now=SESSION_NOW,
        )

    assert exc_info.value.code == "session_type_not_configured"
    assert "meets a laboratory" in exc_info.value.message


async def test_a_configured_type_opens(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """A laboratory session on an offering that meets one is unaffected."""

    stack, service = await _offering(factories, settings, components=["lecture", "lab"])

    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(offering_id=stack["offering"].id, session_type="lab"),
        now=SESSION_NOW,
    )

    assert read.session_type.value == "lab"


async def test_an_offering_without_a_meeting_meets_a_lecture(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """No configured meeting: the lecture opens, the laboratory does not."""

    stack, service = await _offering(factories, settings)

    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(offering_id=stack["offering"].id),
        now=SESSION_NOW,
    )

    assert read.session_type.value == "lecture"

    # The lecture session is closed first: an offering with a live session
    # refuses a second open before the type is even looked at.
    await service.close_session(session_id=read.id, professor_id=stack["professor"].id)

    with pytest.raises(SessionTypeNotConfiguredException):
        await service.create_session(
            professor_id=stack["professor"].id,
            payload=SessionCreate(offering_id=stack["offering"].id, session_type="lab"),
            now=SESSION_NOW,
        )


async def test_an_inactive_meeting_does_not_count(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """Only the *active* meetings are what the offering meets."""

    stack, service = await _offering(factories, settings, components=["lecture"])
    factories.db.add(
        OfferingComponent(
            offering_id=stack["offering"].id,
            session_type="lab",
            schedule_days="W",
            schedule_start_time=MEETING_START,
            schedule_end_time=MEETING_END,
            is_active=False,
        )
    )
    await factories.db.flush()

    with pytest.raises(SessionTypeNotConfiguredException):
        await service.create_session(
            professor_id=stack["professor"].id,
            payload=SessionCreate(offering_id=stack["offering"].id, session_type="lab"),
            now=SESSION_NOW,
        )


# --- over HTTP -------------------------------------------------------------


async def test_the_plan_endpoint_refuses_a_closed_type(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: Any,
) -> None:
    """A plan for a type the offering does not meet is not a plan."""

    stack, _service = await _offering(factories, Settings())
    headers = await _headers(auth_headers, factories, stack["offering"])
    await test_db_session.commit()

    response = await api_client.get(
        PLAN.format(offering_id=stack["offering"].id) + "?session_type=lab",
        headers=headers,
    )

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "session_type_not_configured"
    assert detail["field"] == "session_type"


async def test_an_open_of_a_closed_type_is_422_over_http(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: Any,
) -> None:
    stack, _service = await _offering(factories, Settings())
    headers = await _headers(auth_headers, factories, stack["offering"])
    await test_db_session.commit()

    response = await api_client.post(
        SESSIONS,
        json={"offering_id": stack["offering"].id, "session_type": "lab"},
        headers=headers,
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "session_type_not_configured"


async def test_the_course_list_reports_the_openable_types(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: Any,
) -> None:
    """The form renders these, so they are what the server reports."""

    stack, _service = await _offering(factories, Settings())
    headers = await _headers(auth_headers, factories, stack["offering"])
    await test_db_session.commit()

    response = await api_client.get(COURSES, headers=headers)

    assert response.status_code == 200, response.text
    item = next(
        row
        for row in response.json()["items"]
        if row["offering_id"] == stack["offering"].id
    )
    assert item["session_types"] == ["lecture"]


async def test_the_course_list_reports_a_mixed_offering(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: Any,
) -> None:
    stack, _service = await _offering(
        factories, Settings(), components=["lecture", "lab"]
    )
    headers = await _headers(auth_headers, factories, stack["offering"])
    await test_db_session.commit()

    response = await api_client.get(COURSES, headers=headers)

    assert response.status_code == 200, response.text
    item = next(
        row
        for row in response.json()["items"]
        if row["offering_id"] == stack["offering"].id
    )
    assert item["session_types"] == ["lab", "lecture"]


# --- the shared rule -------------------------------------------------------


def test_the_shared_rule_ignores_unknown_types() -> None:
    """A type nobody reads cannot widen the list."""

    from shared.schedule import openable_session_types

    assert openable_session_types(["lecture"]) == ["lecture"]
    assert openable_session_types(["lab"]) == ["lab"]
    assert openable_session_types(["lab", "lecture"]) == ["lab", "lecture"]
    assert openable_session_types(["nonsense"]) == ["lecture"]
    assert openable_session_types([]) == ["lecture"]
