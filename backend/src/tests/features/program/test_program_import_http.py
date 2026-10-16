"""HTTP-level cover for the program import/template routes.

Service-level parsing and validation live in `test_program_import.py`;
only a real request can prove the routing (static `/import` before
`/{program_id}`), the admin role gate, and the 200 contract.
"""

from __future__ import annotations

from typing import Any

from shared.enums import UserRole
from tests.conftest import Factories

HEADER = "code,name,description,total_years"


async def test_import_creates_programs_and_template_downloads(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    admin = await factories.user(role=UserRole.ADMIN.value)
    headers = await auth_headers(admin)
    content = f"{HEADER}\nBSCS,BS Computer Science,,4\nBSIT,BS IT,,4\n".encode()

    response = await api_client.post(
        "/api/admin/programs/import",
        files={"file": ("programs.csv", content, "text/csv")},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["imported"] == 2
    assert body["duplicates"] == 0
    assert body["errors"] == []

    listing = await api_client.get("/api/admin/programs", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["total"] == 2

    template = await api_client.get("/api/admin/programs/import/template", headers=headers)
    assert template.status_code == 200
    assert template.text.strip() == HEADER


async def test_import_second_run_counts_duplicates(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    admin = await factories.user(role=UserRole.ADMIN.value)
    headers = await auth_headers(admin)
    content = f"{HEADER}\nBSCS,BS Computer Science,,4\n".encode()
    files = {"file": ("programs.csv", content, "text/csv")}

    first = await api_client.post("/api/admin/programs/import", files=files, headers=headers)
    assert first.status_code == 200

    second = await api_client.post(
        "/api/admin/programs/import",
        files={"file": ("programs.csv", content, "text/csv")},
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
    content = f"{HEADER}\nBSCS,BS Computer Science,,4\n".encode()

    response = await api_client.post(
        "/api/admin/programs/import",
        files={"file": ("programs.csv", content, "text/csv")},
        headers=headers,
    )

    assert response.status_code == 403
