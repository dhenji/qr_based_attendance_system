"""HTTP-level cover for `PATCH /professor/profile/password`.

Mirrors the student happy-path/wrong-password cases in
`attendance/test_routes_http.py` and pins the two new slice-owned behaviors:
a weak `new_password` is rejected with 422 (strong-only policy), and a
professor-role login with no roster row gets 404 `professor_not_found`.
"""

from __future__ import annotations

from typing import Any

from core.security import hash_password
from shared.enums import UserRole
from tests.conftest import Factories


async def _linked_professor(factories: Factories) -> Any:
    user = await factories.user(
        role=UserRole.PROFESSOR.value,
        password_hash=hash_password("CurrentPass1!"),
    )
    await factories.professor(user=user)
    return user


async def test_change_password_updates_the_hash(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    user = await _linked_professor(factories)

    response = await api_client.patch(
        "/api/professor/profile/password",
        json={"current_password": "CurrentPass1!", "new_password": "BrandNewPass2!"},
        headers=await auth_headers(user),
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Password updated"}


async def test_change_password_rejects_a_wrong_current_password(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    user = await _linked_professor(factories)

    response = await api_client.patch(
        "/api/professor/profile/password",
        json={"current_password": "WrongPass1!", "new_password": "BrandNewPass2!"},
        headers=await auth_headers(user),
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "current_password_invalid"


async def test_change_password_rejects_a_weak_new_password(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    user = await _linked_professor(factories)

    response = await api_client.patch(
        "/api/professor/profile/password",
        json={"current_password": "CurrentPass1!", "new_password": "weakpass1"},
        headers=await auth_headers(user),
    )

    assert response.status_code == 422


async def test_change_password_without_a_roster_row_is_404(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    user = await factories.user(
        role=UserRole.PROFESSOR.value,
        password_hash=hash_password("CurrentPass1!"),
    )

    response = await api_client.patch(
        "/api/professor/profile/password",
        json={"current_password": "CurrentPass1!", "new_password": "BrandNewPass2!"},
        headers=await auth_headers(user),
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "professor_not_found"
