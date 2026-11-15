"""The session-plan endpoint and the schedule exception over HTTP (D93).

The open form renders `GET /professor/offerings/{id}/session-plan` rather
than re-deriving the schedule, so the endpoint is part of the contract the
professor portal depends on. These cases pin its authorization (the same
rule the open itself uses), its 404, and the shape it answers with.
"""

from __future__ import annotations

from datetime import date, time, timedelta
from typing import Any, Callable, Coroutine

from sqlalchemy import select

from features.course.model import OfferingComponent
from features.system.model import AppSetting
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


# -- the read-only guarantee (same rule the dashboard pins) -------------------


async def test_the_plan_endpoint_does_not_write_settings(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    db_factory: Callable[..., Coroutine[Any, Any, Any]],
    test_db_session: Any,
) -> None:
    """`GET .../session-plan` must not create AppSetting rows.

    The plan's `attendance_attempt_limit_default` used to come from
    `SystemService._stored_settings`, which INSERTs every missing setting row
    and flushes — turning the open form's GET into a write. The read-only
    lookup pins that a GET leaves `app_settings` empty; the settings page
    (`GET /admin/system/settings`) stays the designated seeding workflow.
    """
    offering = await _seed(factories, db_factory)
    headers = await _professor_headers(auth_headers, factories, offering)
    await test_db_session.commit()

    response = await api_client.get(
        PLAN.format(offering_id=offering.id), headers=headers
    )

    assert response.status_code == 200, response.text
    # The env default (Settings.default_attendance_attempt_limit = 3), not a
    # seeded row.
    assert response.json()["attendance_attempt_limit_default"] == 3

    rows = (await test_db_session.scalars(select(AppSetting))).all()
    assert rows == []


async def test_the_plan_endpoint_reads_a_stored_setting_without_seeding(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    db_factory: Callable[..., Coroutine[Any, Any, Any]],
    test_db_session: Any,
) -> None:
    """A stored attempt default wins over the env default — and only it.

    The read-only lookup reads the single key it needs; the other seven
    setting keys must stay unseeded by a GET.
    """
    offering = await _seed(factories, db_factory)
    headers = await _professor_headers(auth_headers, factories, offering)
    await db_factory(
        AppSetting,
        key="attendance_attempt_limit_default",
        value="5",
    )
    await test_db_session.commit()

    response = await api_client.get(
        PLAN.format(offering_id=offering.id), headers=headers
    )

    assert response.status_code == 200, response.text
    assert response.json()["attendance_attempt_limit_default"] == 5

    rows = (await test_db_session.scalars(select(AppSetting))).all()
    assert [row.key for row in rows] == ["attendance_attempt_limit_default"]
