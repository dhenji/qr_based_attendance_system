"""The session-plan endpoint and the schedule exception over HTTP (D93).

The open form renders `GET /professor/offerings/{id}/session-plan` rather
than re-deriving the schedule, so the endpoint is part of the contract the
professor portal depends on. These cases pin its authorization (the same
rule the open itself uses), its 404, and the shape it answers with.
"""

from __future__ import annotations

from datetime import date, time, timedelta
from typing import Any, Callable, Coroutine

from features.course.model import OfferingComponent
from shared.enums import UserRole
from tests.conftest import Factories
from tests.features.session.conftest import SESSION_NOW

PLAN = "/api/professor/offerings/{offering_id}/session-plan"
SESSIONS = "/api/professor/sessions"


async def _professor_headers(
    auth_headers: Any, factories: Factories, offering: Any
) -> dict[str, str]:
    professor_user = await factories.user(role=UserRole.PROFESSOR.value)
    professor = await factories.professor(professor_user)
    assigner = await factories.user(role=UserRole.ADMIN.value)
    await factories.assignment(offering, professor, assigner)
    return await auth_headers(professor_user)


async def _seed(
    factories: Factories,
    db_factory: Callable[..., Coroutine[Any, Any, Any]],
) -> Any:
    program = await factories.program()
    year_level = await factories.year_level(program)
    course = await factories.course(units=3)
    offering = await factories.offering(course, program, year_level)
    await db_factory(
        OfferingComponent,
        offering_id=offering.id,
        session_type="lecture",
        schedule_days="MWF",
        schedule_start_time=time(9, 0),
        schedule_end_time=time(10, 0),
        classroom_name="Room 101",
        classroom_lat=14.5,
        classroom_lng=121.0,
        is_active=True,
    )
    return offering


async def test_the_plan_endpoint_answers_the_resolved_plan(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    db_factory: Callable[..., Coroutine[Any, Any, Any]],
    test_db_session: Any,
) -> None:
    offering = await _seed(factories, db_factory)
    headers = await _professor_headers(auth_headers, factories, offering)
    await test_db_session.commit()

    response = await api_client.get(
        PLAN.format(offering_id=offering.id), headers=headers
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["offering_id"] == offering.id
    assert body["source"] == "component"
    assert body["start_time"].startswith("09:00")
    assert body["end_time"].startswith("10:00")
    assert body["duration_minutes"] == 60
    assert body["classroom_name"] == "Room 101"
    assert body["override_capable"] is True
    # The next occurrence is a real date, not null.
    assert date.fromisoformat(body["session_date"]) is not None


async def test_the_plan_endpoint_refuses_a_professor_outside_the_team(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    db_factory: Callable[..., Coroutine[Any, Any, Any]],
    test_db_session: Any,
) -> None:
    offering = await _seed(factories, db_factory)
    outsider = await factories.user(role=UserRole.PROFESSOR.value)
    # A claimed professor with no assignment on the offering: the plan is
    # forbidden, not missing.
    await factories.professor(outsider)
    headers = await auth_headers(outsider)
    await test_db_session.commit()

    response = await api_client.get(
        PLAN.format(offering_id=offering.id), headers=headers
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "not_assigned"


async def test_the_plan_endpoint_is_404_for_an_unknown_offering(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: Any,
) -> None:
    professor_user = await factories.user(role=UserRole.PROFESSOR.value)
    await factories.professor(professor_user)
    headers = await auth_headers(professor_user)
    await test_db_session.commit()

    response = await api_client.get(PLAN.format(offering_id=987654), headers=headers)

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "offering_not_found"


async def test_opening_with_a_schedule_exception_is_201(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    db_factory: Callable[..., Coroutine[Any, Any, Any]],
    test_db_session: Any,
) -> None:
    offering = await _seed(factories, db_factory)
    headers = await _professor_headers(auth_headers, factories, offering)
    await test_db_session.commit()

    day = (SESSION_NOW.date() + timedelta(days=1)).isoformat()
    response = await api_client.post(
        SESSIONS,
        json={
            "offering_id": offering.id,
            "session_date": day,
            "start_time": "10:30:00",
        },
        headers=headers,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["schedule_overridden"] is True
    assert body["scheduled_start_time"].startswith(day)


async def test_opening_with_a_date_in_the_past_is_422(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    db_factory: Callable[..., Coroutine[Any, Any, Any]],
    test_db_session: Any,
) -> None:
    offering = await _seed(factories, db_factory)
    headers = await _professor_headers(auth_headers, factories, offering)
    await test_db_session.commit()

    # The pinned clock, not `date.today()`: the server compares the date
    # against its own UTC day, and the machine's local date can be a day
    # ahead of it.
    day = (SESSION_NOW.date() - timedelta(days=1)).isoformat()
    response = await api_client.post(
        SESSIONS,
        json={"offering_id": offering.id, "session_date": day},
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "session_date_in_past"
