"""Deactivate/reactivate routes on `/admin/users`.

These pin the write side of user Management: the two PATCH routes flip
`users.is_active` in opposite directions, reject self-transitions, 404 on
unknown ids, and are super_admin-only.
"""

from __future__ import annotations

from typing import Any

import pytest

from shared.enums import UserRole

from features.admin.exceptions import SelfDeactivationForbidden
from features.admin.service import AdminService
from tests.conftest import Factories

ADMIN_EMAIL = "status.admin@isu.edu.ph"
TARGET_EMAIL = "status.target@isu.edu.ph"


async def _admin(factories: Factories) -> Any:
    return await factories.user(email=ADMIN_EMAIL, role=UserRole.SUPER_ADMIN.value)


async def _target(factories: Factories, *, is_active: bool = True) -> Any:
    return await factories.user(
        email=TARGET_EMAIL, role=UserRole.ADMIN.value, is_active=is_active
    )


# -- service-level ---------------------------------------------------------


async def test_deactivate_user_sets_inactive(
    test_db_session: Any, factories: Factories
) -> None:
    target = await _target(factories)
    await test_db_session.commit()

    await AdminService(test_db_session).deactivate_user(
        actor_id=target.id + 1, user_id=target.id
    )

    await test_db_session.refresh(target)
    assert target.is_active is False


async def test_reactivate_user_sets_active(
    test_db_session: Any, factories: Factories
) -> None:
    target = await _target(factories, is_active=False)
    await test_db_session.commit()

    await AdminService(test_db_session).reactivate_user(
        actor_id=target.id + 1, user_id=target.id
    )

    await test_db_session.refresh(target)
    assert target.is_active is True


async def test_deactivate_reactivate_round_trip(
    test_db_session: Any, factories: Factories
) -> None:
    target = await _target(factories)
    await test_db_session.commit()
    service = AdminService(test_db_session)

    await service.deactivate_user(actor_id=target.id + 1, user_id=target.id)
    await test_db_session.refresh(target)
    assert target.is_active is False

    await service.reactivate_user(actor_id=target.id + 1, user_id=target.id)
    await test_db_session.refresh(target)
    assert target.is_active is True


async def test_deactivate_unknown_user_raises(
    test_db_session: Any, factories: Factories
) -> None:
    await _admin(factories)
    await test_db_session.commit()

    with pytest.raises(Exception) as exc_info:
        await AdminService(test_db_session).deactivate_user(actor_id=1, user_id=9999)
    assert exc_info.value.__class__.__name__ == "AdminUserNotFound"


async def test_reactivate_unknown_user_raises(
    test_db_session: Any, factories: Factories
) -> None:
    await _admin(factories)
    await test_db_session.commit()

    with pytest.raises(Exception) as exc_info:
        await AdminService(test_db_session).reactivate_user(actor_id=1, user_id=9999)
    assert exc_info.value.__class__.__name__ == "AdminUserNotFound"


async def test_self_deactivation_rejected(
    test_db_session: Any, factories: Factories
) -> None:
    admin = await _admin(factories)
    await test_db_session.commit()

    with pytest.raises(SelfDeactivationForbidden):
        await AdminService(test_db_session).deactivate_user(
            actor_id=admin.id, user_id=admin.id
        )


async def test_self_reactivation_rejected(
    test_db_session: Any, factories: Factories
) -> None:
    admin = await _admin(factories)
    await test_db_session.commit()

    with pytest.raises(SelfDeactivationForbidden):
        await AdminService(test_db_session).reactivate_user(
            actor_id=admin.id, user_id=admin.id
        )


# -- HTTP-level ------------------------------------------------------------


async def test_deactivate_route_returns_204(
    api_client: Any, auth_headers: Any, factories: Factories, test_db_session: Any
) -> None:
    admin = await _admin(factories)
    target = await _target(factories)
    await test_db_session.commit()

    response = await api_client.patch(
        f"/api/admin/users/{target.id}/deactivate",
        headers=await auth_headers(admin),
    )
    assert response.status_code == 204

    await test_db_session.refresh(target)
    assert target.is_active is False


async def test_reactivate_route_returns_204(
    api_client: Any, auth_headers: Any, factories: Factories, test_db_session: Any
) -> None:
    admin = await _admin(factories)
    target = await _target(factories, is_active=False)
    await test_db_session.commit()

    response = await api_client.patch(
        f"/api/admin/users/{target.id}/reactivate",
        headers=await auth_headers(admin),
    )
    assert response.status_code == 204

    await test_db_session.refresh(target)
    assert target.is_active is True


async def test_reactivate_unknown_user_returns_404(
    api_client: Any, auth_headers: Any, factories: Factories, test_db_session: Any
) -> None:
    admin = await _admin(factories)
    await test_db_session.commit()

    response = await api_client.patch(
        "/api/admin/users/9999/reactivate",
        headers=await auth_headers(admin),
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "admin_user_not_found"


async def test_deactivate_unknown_user_returns_404(
    api_client: Any, auth_headers: Any, factories: Factories, test_db_session: Any
) -> None:
    admin = await _admin(factories)
    await test_db_session.commit()

    response = await api_client.patch(
        "/api/admin/users/9999/deactivate",
        headers=await auth_headers(admin),
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "admin_user_not_found"


async def test_non_super_admin_cannot_reactivate(
    api_client: Any, auth_headers: Any, factories: Factories, test_db_session: Any
) -> None:
    await _admin(factories)
    plain_admin = await factories.user(
        email="plain.admin@isu.edu.ph", role=UserRole.ADMIN.value
    )
    target = await _target(factories, is_active=False)
    await test_db_session.commit()

    response = await api_client.patch(
        f"/api/admin/users/{target.id}/reactivate",
        headers=await auth_headers(plain_admin),
    )
    assert response.status_code == 403

    await test_db_session.refresh(target)
    assert target.is_active is False


async def test_non_super_admin_cannot_deactivate(
    api_client: Any, auth_headers: Any, factories: Factories, test_db_session: Any
) -> None:
    await _admin(factories)
    plain_admin = await factories.user(
        email="plain.admin@isu.edu.ph", role=UserRole.ADMIN.value
    )
    target = await _target(factories)
    await test_db_session.commit()

    response = await api_client.patch(
        f"/api/admin/users/{target.id}/deactivate",
        headers=await auth_headers(plain_admin),
    )
    assert response.status_code == 403

    await test_db_session.refresh(target)
    assert target.is_active is True


async def test_self_deactivation_route_returns_409(
    api_client: Any, auth_headers: Any, factories: Factories, test_db_session: Any
) -> None:
    admin = await _admin(factories)
    await test_db_session.commit()

    response = await api_client.patch(
        f"/api/admin/users/{admin.id}/deactivate",
        headers=await auth_headers(admin),
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "self_deactivation_forbidden"
