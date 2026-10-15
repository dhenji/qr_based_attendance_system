"""HTTP-level cover for the course import/template routes.

Service-level parsing and validation live in `test_course_import.py`;
only a real request can prove the routing (static `/import` before
`/{course_id}`), the admin role gate, and the 200 contract.
"""

from __future__ import annotations

from typing import Any

from shared.enums import UserRole
from tests.conftest import Factories

HEADER = "course_code,course_name,units,session_duration_hours"


async def test_import_creates_courses_and_template_downloads(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    admin = await factories.user(role=UserRole.ADMIN.value)
    headers = await auth_headers(admin)
    content = f"{HEADER}\nCS101,Software Engineering 1,3,1.5\n".encode()

    response = await api_client.post(
        "/api/admin/courses/import",
        files={"file": ("courses.csv", content, "text/csv")},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["imported"] == 1
    assert body["duplicates"] == 0
    assert body["errors"] == []

    listing = await api_client.get("/api/admin/courses", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["total"] == 1

    template = await api_client.get("/api/admin/courses/import/template", headers=headers)
    assert template.status_code == 200
    assert template.text.strip() == HEADER


async def test_import_second_run_counts_duplicates(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    admin = await factories.user(role=UserRole.ADMIN.value)
    headers = await auth_headers(admin)
    content = f"{HEADER}\nCS101,Software Engineering 1,3,1.5\n".encode()

    first = await api_client.post(
        "/api/admin/courses/import", files={"file": ("courses.csv", content, "text/csv")}, headers=headers
    )
    assert first.status_code == 200

    second = await api_client.post(
        "/api/admin/courses/import",
        files={"file": ("courses.csv", content, "text/csv")},
        headers=headers,
    )
    assert second.status_code == 200
    assert second.json()["imported"] == 0
    assert second.json()["duplicates"] == 1


async def test_import_requires_admin(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    student = await factories.user(role=UserRole.STUDENT.value)
    headers = await auth_headers(student)
    content = f"{HEADER}\nCS101,Software Engineering 1,3,1.5\n".encode()

    response = await api_client.post(
        "/api/admin/courses/import",
        files={"file": ("courses.csv", content, "text/csv")},
        headers=headers,
    )

    assert response.status_code == 403
