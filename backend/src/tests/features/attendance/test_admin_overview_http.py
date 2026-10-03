"""HTTP-level cover for the admin attendance overview routes.

Service math (rates, half-split trend) is exercised through real requests
here: these tests prove what only a request can — role gating off a real
JWT, the contract shapes, the CSV download, and the filter behavior.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from shared.enums import UserRole, ValidationStatus
from tests.conftest import Factories

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


async def _seed_two_sessions(factories: Factories) -> dict[str, Any]:
    """One course/offering, two students, two sessions, 3/4 present scans."""
    program = await factories.program()
    year_level = await factories.year_level(program)
    course = await factories.course(course_code="CS101", course_name="Intro")
    offering = await factories.offering(course, program, year_level)
    admin = await factories.user(role=UserRole.ADMIN.value)
    professor_user = await factories.user(role=UserRole.PROFESSOR.value)
    professor = await factories.professor(professor_user)
    await factories.assignment(offering, professor, admin)
    student_a = await factories.student(year_level, await factories.user())
    student_b = await factories.student(year_level, await factories.user())
    await factories.enrollment(student_a, offering)
    await factories.enrollment(student_b, offering)
    first = await factories.session(
        offering,
        professor,
        created_at=NOW - timedelta(days=2),
        scheduled_start_time=NOW - timedelta(days=2),
        scheduled_end_time=NOW - timedelta(days=2) + timedelta(minutes=60),
        expires_at=NOW - timedelta(days=2) + timedelta(minutes=60),
    )
    second = await factories.session(
        offering,
        professor,
        created_at=NOW - timedelta(days=1),
        scheduled_start_time=NOW - timedelta(days=1),
        scheduled_end_time=NOW - timedelta(days=1) + timedelta(minutes=60),
        expires_at=NOW - timedelta(days=1) + timedelta(minutes=60),
    )
    await factories.attendance(
        student_a, first, timestamp=NOW - timedelta(days=2)
    )
    await factories.attendance(
        student_b, first, timestamp=NOW - timedelta(days=2)
    )
    await factories.attendance(
        student_a, second, timestamp=NOW - timedelta(days=1)
    )
    return {
        "program": program,
        "year_level": year_level,
        "course": course,
        "offering": offering,
        "admin": admin,
        "professor": professor,
        "professor_user": professor_user,
        "student_a": student_a,
        "student_b": student_b,
        "first": first,
        "second": second,
    }


async def test_overview_reports_rate_and_trend(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed_two_sessions(factories)

    response = await api_client.get(
        "/api/admin/attendance/overview",
        headers=await auth_headers(seed["admin"]),
    )

    assert response.status_code == 200
    (item,) = response.json()["items"]
    assert item["course_id"] == seed["course"].id
    assert item["course_code"] == "CS101"
    assert item["course_name"] == "Intro"
    assert item["sessions_count"] == 2
    # 3 present scans over 2 students x 2 sessions.
    assert item["avg_rate"] == 0.75
    # First half 2/2, second half 1/2 -> declining.
    assert item["trend"] == "down"


async def test_overview_single_session_is_flat(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed_two_sessions(factories)

    response = await api_client.get(
        "/api/admin/attendance/overview",
        params={"date_from": (NOW - timedelta(days=1, hours=1)).isoformat()},
        headers=await auth_headers(seed["admin"]),
    )

    assert response.status_code == 200
    (item,) = response.json()["items"]
    assert item["sessions_count"] == 1
    assert item["avg_rate"] == 0.5
    assert item["trend"] == "flat"


async def test_overview_course_filter(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed_two_sessions(factories)
    other_course = await factories.course(course_code="MATH202")
    await factories.offering(other_course, seed["program"], seed["year_level"])

    response = await api_client.get(
        f"/api/admin/attendance/overview?course_id={seed['course'].id}",
        headers=await auth_headers(seed["admin"]),
    )

    assert response.status_code == 200
    (item,) = response.json()["items"]
    assert item["course_id"] == seed["course"].id


async def test_overview_professor_filter_uses_current_assignment(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed_two_sessions(factories)
    outsider_user = await factories.user(role=UserRole.PROFESSOR.value)
    outsider = await factories.professor(outsider_user)

    assigned = await api_client.get(
        f"/api/admin/attendance/overview?professor_id={seed['professor'].id}",
        headers=await auth_headers(seed["admin"]),
    )
    unassigned = await api_client.get(
        f"/api/admin/attendance/overview?professor_id={outsider.id}",
        headers=await auth_headers(seed["admin"]),
    )

    assert assigned.status_code == 200
    assert len(assigned.json()["items"]) == 1
    assert unassigned.status_code == 200
    assert unassigned.json()["items"] == []


async def test_overview_unknown_professor_returns_empty(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed_two_sessions(factories)

    response = await api_client.get(
        "/api/admin/attendance/overview?professor_id=999999",
        headers=await auth_headers(seed["admin"]),
    )

    assert response.status_code == 200
    assert response.json() == {"items": []}


async def test_overview_export_downloads_csv(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed_two_sessions(factories)

    response = await api_client.get(
        "/api/admin/attendance/overview/export",
        headers=await auth_headers(seed["admin"]),
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    lines = response.text.strip().splitlines()
    assert lines[0] == "course_id,course_code,course_name,sessions_count,avg_rate,trend"
    assert len(lines) == 2
    assert "CS101" in lines[1]
    assert "down" in lines[1]


async def test_recent_scans_returns_newest_first(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed_two_sessions(factories)

    response = await api_client.get(
        "/api/admin/attendance/recent-scans?limit=2",
        headers=await auth_headers(seed["admin"]),
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 2
    assert items[0]["course_code"] == "CS101"
    assert items[0]["student_name"]
    assert items[0]["status"] == ValidationStatus.PRESENT.value
    assert "scanned_at" in items[0]
    assert items[0]["id"] > items[1]["id"]


async def test_recent_scans_default_limit(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed_two_sessions(factories)

    response = await api_client.get(
        "/api/admin/attendance/recent-scans",
        headers=await auth_headers(seed["admin"]),
    )

    assert response.status_code == 200
    # Three seeded scans, all within the default limit of 10.
    assert len(response.json()["items"]) == 3


async def test_attendance_overview_routes_require_admin(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    await _seed_two_sessions(factories)
    headers = await auth_headers(role=UserRole.PROFESSOR.value)
    # Three failing requests in one test: the first one's rollback would take
    # the seed down with it, so the seed commits first.
    await test_db_session.commit()

    for path in (
        "/api/admin/attendance/overview",
        "/api/admin/attendance/recent-scans",
        "/api/admin/attendance/overview/export",
    ):
        response = await api_client.get(path, headers=headers)
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "insufficient_permissions"
