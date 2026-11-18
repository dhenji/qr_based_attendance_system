"""Roster create ignores unknown keys.

Old clients still sending `username` on roster add get 201, minus it.
Pydantic's default `extra="ignore"` drops the unknown key, so the
removal needs no versioned contract — the response simply carries no
username field because `StudentRead` never had one.
"""

from __future__ import annotations

from typing import Any

from shared.enums import UserRole

from tests.conftest import Factories


async def test_roster_create_ignores_stray_username_key(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    admin = await factories.user(
        email="roster.admin@isu.edu.ph",
        role=UserRole.ADMIN.value,
        is_active=True,
    )
    program = await factories.program()
    year = await factories.year_level(program)

    response = await api_client.post(
        "/api/admin/students",
        headers=await auth_headers(admin),
        json={
            "student_id": "2024-00099",
            "first_name": "Jose",
            "last_name": "Rizal",
            "email": "jose.rizal@isu.edu.ph",
            "program_id": program.id,
            "year_level_id": year.id,
            "username": "stray.handle",
        },
    )

    assert response.status_code == 201
    assert "username" not in response.json()
