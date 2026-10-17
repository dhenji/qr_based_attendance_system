"""HTTP-level cover for the offering unenroll route.

`unenroll_student` has service-level cover in `test_offering_service.py`;
only a real request can prove the routing, the admin role gate, the 204
contract, and the read-path consequences both portals show (roster total and
the student schedule).
"""

from __future__ import annotations

from typing import Any

from shared.enums import UserRole
from tests.conftest import Factories


async def _seed(factories: Factories) -> dict[str, Any]:
    """One offering with one enrolled student, plus an admin account."""
    program = await factories.program()
    year_level = await factories.year_level(program)
    course = await factories.course()
    offering = await factories.offering(course, program, year_level)
    student_user = await factories.user()
    student = await factories.student(year_level, student_user)
    enrollment = await factories.enrollment(student, offering)
    admin = await factories.user(role=UserRole.ADMIN.value)
    return {
        "offering": offering,
        "student": student,
        "student_user": student_user,
        "enrollment": enrollment,
        "admin": admin,
    }


def _unenroll_path(seed: dict[str, Any], student_number: str | None = None) -> str:
    number = student_number if student_number is not None else seed["student"].student_id
    return f"/api/admin/offerings/{seed['offering'].id}/students/{number}"


async def test_unenroll_removes_link_and_shrinks_roster(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed(factories)
    admin_headers = await auth_headers(seed["admin"])

    response = await api_client.delete(_unenroll_path(seed), headers=admin_headers)

    assert response.status_code == 204

    roster = await api_client.get(
        f"/api/admin/offerings/{seed['offering'].id}/students",
        headers=admin_headers,
    )
    assert roster.status_code == 200
    assert roster.json()["total"] == 0
    assert roster.json()["items"] == []

    schedule = await api_client.get(
        "/api/student/schedule",
        headers=await auth_headers(seed["student_user"]),
    )
    assert schedule.status_code == 200
    assert schedule.json()["offerings"] == []


async def test_unenroll_repeat_is_404(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed(factories)
    admin_headers = await auth_headers(seed["admin"])

    first = await api_client.delete(_unenroll_path(seed), headers=admin_headers)
    assert first.status_code == 204

    second = await api_client.delete(_unenroll_path(seed), headers=admin_headers)
    assert second.status_code == 404
    assert second.json()["detail"]["code"] == "enrollment_not_found"


async def test_unenroll_unknown_student_is_404(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed(factories)

    response = await api_client.delete(
        _unenroll_path(seed, student_number="NOPE-1"),
        headers=await auth_headers(seed["admin"]),
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "student_not_found"


async def test_unenroll_unknown_offering_is_404(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed(factories)
    student_number = seed["student"].student_id

    response = await api_client.delete(
        f"/api/admin/offerings/999999/students/{student_number}",
        headers=await auth_headers(seed["admin"]),
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "offering_not_found"


async def test_unenroll_requires_admin(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed(factories)

    response = await api_client.delete(
        _unenroll_path(seed),
        headers=await auth_headers(seed["student_user"]),
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "insufficient_permissions"
