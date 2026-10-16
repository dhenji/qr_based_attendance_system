"""schedule_ok flag on the professor assigned-offerings read (D82).

Exact totals read True; over/under read False; rows with no configured
meetings stay True (the open gate's legacy exemption).
"""

from __future__ import annotations

from datetime import time
from typing import Any, Callable, Coroutine

from features.course.model import OfferingComponent
from shared.enums import UserRole
from tests.conftest import Factories

COURSES = "/api/professor/courses"


async def _assigned_headers(
    auth_headers: Any, factories: Factories, offering: Any
) -> dict[str, str]:
    professor_user = await factories.user(role=UserRole.PROFESSOR.value)
    professor = await factories.professor(professor_user)
    assigner = await factories.user(role=UserRole.ADMIN.value)
    await factories.assignment(offering, professor, assigner)
    return await auth_headers(professor_user)


async def _seed_with(
    factories: Factories,
    db_factory: Callable[..., Coroutine[Any, Any, Any]],
    meetings: list[tuple[str, time, time]],
) -> Any:
    program = await factories.program()
    year_level = await factories.year_level(program)
    course = await factories.course(units=3)
    offering = await factories.offering(course, program, year_level)
    for days, start, end in meetings:
        await db_factory(
            OfferingComponent,
            offering_id=offering.id,
            session_type="lecture",
            schedule_days=days,
            schedule_start_time=start,
            schedule_end_time=end,
            is_active=True,
        )
    return offering


async def _flag_for(
    api_client: Any, headers: dict[str, str], offering_id: int
) -> bool | None:
    response = await api_client.get(COURSES, headers=headers)
    assert response.status_code == 200, response.text
    rows = [item for item in response.json()["items"] if item["offering_id"] == offering_id]
    assert len(rows) == 1
    return rows[0].get("schedule_ok", True)


async def test_schedule_ok_matrix(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    db_factory: Callable[..., Coroutine[Any, Any, Any]],
    test_db_session: Any,
) -> None:
    exact = await _seed_with(
        factories,
        db_factory,
        [("M", time(7, 0), time(8, 30)), ("T", time(13, 0), time(14, 30))],
    )
    exact_headers = await _assigned_headers(auth_headers, factories, exact)
    over = await _seed_with(
        factories,
        db_factory,
        [("M", time(7, 0), time(8, 30)), ("T", time(13, 0), time(15, 0))],
    )
    over_headers = await _assigned_headers(auth_headers, factories, over)
    under = await _seed_with(
        factories, db_factory, [("M", time(7, 0), time(8, 30))]
    )
    under_headers = await _assigned_headers(auth_headers, factories, under)
    bare = await _seed_with(factories, db_factory, [])
    bare_headers = await _assigned_headers(auth_headers, factories, bare)
    await test_db_session.commit()

    assert await _flag_for(api_client, exact_headers, exact.id) is True
    assert await _flag_for(api_client, over_headers, over.id) is False
    assert await _flag_for(api_client, under_headers, under.id) is False
    assert await _flag_for(api_client, bare_headers, bare.id) is True
