"""HTTP-level cover for the professor reports routes.

The union scope (sessions opened plus current assignments) is the behavior
these tests pin down: an unassigned professor sees nothing, an owned session
shows without any assignment row, and a co-teacher's offering stays out of
another professor's aggregates.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from shared.enums import UserRole, ValidationStatus
from tests.conftest import Factories

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


async def _teaching_setup(
    factories: Factories, *, with_assignment: bool = True
) -> dict[str, Any]:
    """Professor + offering + session + enrolled student + one present scan."""
    program = await factories.program()
    year_level = await factories.year_level(program)
    course = await factories.course()
    offering = await factories.offering(course, program, year_level)
    professor_user = await factories.user(role=UserRole.PROFESSOR.value)
    professor = await factories.professor(professor_user)
    admin = await factories.user(role=UserRole.ADMIN.value)

    if with_assignment:
        await factories.assignment(offering, professor, admin)

    session = await factories.session(
        offering, professor, created_at=NOW, expires_at=NOW
    )
    student = await factories.student(year_level, await factories.user())
    await factories.enrollment(student, offering)
    await factories.attendance(student, session, timestamp=NOW)
    return {
        "program": program,
        "year_level": year_level,
        "course": course,
        "offering": offering,
        "professor": professor,
        "professor_user": professor_user,
        "session": session,
        "student": student,
    }


async def _professor_headers(
    auth_headers: Any, setup: dict[str, Any]
) -> dict[str, str]:
    return await auth_headers(setup["professor_user"])


async def test_reports_require_professor_role(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    await _teaching_setup(factories)
    student_headers = await auth_headers(await factories.user())
    admin_headers = await auth_headers(
        await factories.user(role=UserRole.ADMIN.value)
    )
    # Two failing requests in one test: the first one's rollback would take
    # the seed (including both users) down with it, so the seed commits first
    # and the headers are minted before that commit expires the rows.
    await test_db_session.commit()

    for headers in (student_headers, admin_headers):
        response = await api_client.get(
            "/api/professor/reports/all-courses",
            headers=headers,
        )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "insufficient_permissions"


async def test_all_courses_aggregates_assigned_offering(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    setup = await _teaching_setup(factories)

    response = await api_client.get(
        "/api/professor/reports/all-courses?granularity=daily",
        headers=await _professor_headers(auth_headers, setup),
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    (item,) = body["items"]
    assert item["date"] == NOW.date().isoformat()
    assert item["total_sessions"] == 1
    assert item["total_students"] == 1
    assert item["compliance_rate"] == 1.0
    assert item["participation_rate"] == 1.0
    assert body["avg_compliance"] == 1.0
    assert body["avg_participation"] == 1.0


async def test_owned_session_visible_without_assignment(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    setup = await _teaching_setup(factories, with_assignment=False)

    response = await api_client.get(
        "/api/professor/reports/all-courses",
        headers=await _professor_headers(auth_headers, setup),
    )

    assert response.status_code == 200
    assert len(response.json()["items"]) == 1


async def test_unrelated_offering_stays_out_of_scope(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    setup = await _teaching_setup(factories)
    other_professor_user = await factories.user(role=UserRole.PROFESSOR.value)
    other_professor = await factories.professor(other_professor_user)
    other_course = await factories.course()
    other_offering = await factories.offering(
        other_course, setup["program"], setup["year_level"]
    )
    # Opened by the other professor and never assigned to the requester, so
    # it must not leak into their reports.
    await factories.session(other_offering, other_professor, created_at=NOW)

    response = await api_client.get(
        "/api/professor/reports/comparison",
        headers=await _professor_headers(auth_headers, setup),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["course_id"] == setup["course"].id


async def test_comparison_shape_and_pagination(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    setup = await _teaching_setup(factories)

    response = await api_client.get(
        "/api/professor/reports/comparison?page=1&size=20",
        headers=await _professor_headers(auth_headers, setup),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["page"] == 1
    (item,) = body["items"]
    assert item["course_id"] == setup["course"].id
    assert item["course_code"] == setup["course"].course_code
    assert item["program_id"] == setup["program"].id
    assert item["year_level_id"] == setup["year_level"].id
    assert item["compliance_rate"] == 1.0
    assert item["total_sessions"] == 1


async def test_trends_metric_selects_rate(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    setup = await _teaching_setup(factories)
    late_student = await factories.student(
        setup["year_level"], await factories.user()
    )
    await factories.enrollment(late_student, setup["offering"])
    await factories.attendance(
        late_student,
        setup["session"],
        timestamp=NOW,
        validation_status=ValidationStatus.LATE.value,
    )
    headers = await _professor_headers(auth_headers, setup)

    compliance = await api_client.get(
        "/api/professor/reports/trends?metric=compliance",
        headers=headers,
    )
    participation = await api_client.get(
        "/api/professor/reports/trends?metric=participation",
        headers=headers,
    )

    assert compliance.status_code == 200
    assert participation.status_code == 200
    assert compliance.json()["items"][0]["rate"] == 0.5
    assert participation.json()["items"][0]["rate"] == 1.0


async def test_trends_carries_course_identity(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    setup = await _teaching_setup(factories)

    response = await api_client.get(
        "/api/professor/reports/trends",
        headers=await _professor_headers(auth_headers, setup),
    )

    assert response.status_code == 200
    (item,) = response.json()["items"]
    assert item["course_id"] == setup["course"].id
    assert item["course_code"] == setup["course"].course_code
    assert item["date"] == NOW.date().isoformat()


async def test_unclaimed_professor_is_404(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    await _teaching_setup(factories)
    stranger = await factories.user(role=UserRole.PROFESSOR.value)

    response = await api_client.get(
        "/api/professor/reports/all-courses",
        headers=await auth_headers(stranger),
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "professor_not_found"
