"""Session-open gate: no new sessions on mis-scheduled offerings (D82).

The merged active-component total must equal the course units requirement;
rows with no configured meetings are exempt (nothing to judge — legacy and
factory rows keep working). Close/status paths are untouched.
"""

from __future__ import annotations

from datetime import time
from typing import Any, Callable, Coroutine

from features.course.model import OfferingComponent
from shared.enums import UserRole
from tests.conftest import Factories

SESSIONS = "/api/professor/sessions"


async def _professor_headers(
    auth_headers: Any, factories: Factories, offering: Any
) -> dict[str, str]:
    professor_user = await factories.user(role=UserRole.PROFESSOR.value)
    professor = await factories.professor(professor_user)
    assigner = await factories.user(role=UserRole.ADMIN.value)
    await factories.assignment(offering, professor, assigner)
    return await auth_headers(professor_user)


async def _seed_offering_with(
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


async def _open(
    api_client: Any, headers: dict[str, str], offering_id: int
) -> Any:
    return await api_client.post(
        SESSIONS, json={"offering_id": offering_id}, headers=headers
    )


async def test_open_on_exact_schedule_is_201(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    db_factory: Callable[..., Coroutine[Any, Any, Any]],
    test_db_session: Any,
) -> None:
    offering = await _seed_offering_with(
        factories,
        db_factory,
        [("M", time(7, 0), time(8, 30)), ("T", time(13, 0), time(14, 30))],
    )
    headers = await _professor_headers(auth_headers, factories, offering)
    await test_db_session.commit()

    response = await _open(api_client, headers, offering.id)

    assert response.status_code == 201, response.text


async def test_open_on_mismatched_schedule_is_422(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    db_factory: Callable[..., Coroutine[Any, Any, Any]],
    test_db_session: Any,
) -> None:
    # A failing request rolls back the uncommitted seed — commit first.
    over = await _seed_offering_with(
        factories,
        db_factory,
        [("M", time(7, 0), time(8, 30)), ("T", time(13, 0), time(15, 0))],
    )
    over_headers = await _professor_headers(auth_headers, factories, over)
    under = await _seed_offering_with(
        factories, db_factory, [("M", time(7, 0), time(8, 30))]
    )
    under_headers = await _professor_headers(auth_headers, factories, under)
    await test_db_session.commit()
    # Copy ids now: each failing request rolls back, which expires every ORM
    # instance in the session.
    cases = [(over.id, over_headers), (under.id, under_headers)]
    for offering_id, headers in cases:
        response = await _open(api_client, headers, offering_id)
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "offering_schedule_mismatch"


async def test_open_without_configured_meetings_is_exempt(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: Any,
) -> None:
    program = await factories.program()
    year_level = await factories.year_level(program)
    course = await factories.course(units=3)
    offering = await factories.offering(course, program, year_level)
    headers = await _professor_headers(auth_headers, factories, offering)
    await test_db_session.commit()

    response = await _open(api_client, headers, offering.id)

    assert response.status_code == 201, response.text
