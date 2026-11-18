from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.enums import UserRole

from features.system.model import AuditLog
from tests.conftest import Factories

ENDPOINT = "/api/admin/system/academic-structure"


async def _admin_headers(auth_headers: Any, factories: Factories) -> dict[str, str]:
    admin = await factories.user(role=UserRole.ADMIN.value)
    return await auth_headers(admin)


async def _seed(test_db_session: AsyncSession, rows: list[AuditLog]) -> list[AuditLog]:
    test_db_session.add_all(rows)
    await test_db_session.commit()
    return rows


def _row(**overrides: Any) -> AuditLog:
    values: dict[str, Any] = {
        "action": "update",
        "entity_type": "program",
        "entity_id": 1,
        "old_value": {"name": "Old"},
        "new_value": {"name": "New"},
        "performed_by": None,
    }
    values.update(overrides)
    return AuditLog(**values)


async def test_academic_structure_starts_empty(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    headers = await _admin_headers(auth_headers, factories)

    response = await api_client.get(ENDPOINT, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "page": 1, "size": 20}


async def test_academic_structure_returns_structural_rows(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    headers = await _admin_headers(auth_headers, factories)
    await _seed(
        test_db_session,
        [
            _row(action="create", entity_type="course", old_value=None),
            _row(action="delete", entity_type="year_level", new_value=None),
        ],
    )

    response = await api_client.get(ENDPOINT, headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert {item["entity_type"] for item in body["items"]} == {"course", "year_level"}
    assert [item["action"] for item in body["items"]] == ["delete", "create"]


async def test_academic_structure_hides_non_structural_rows(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    headers = await _admin_headers(auth_headers, factories)
    await _seed(
        test_db_session,
        [
            _row(entity_type="program"),
            _row(entity_type="session"),
            _row(entity_type="excuse_request"),
        ],
    )

    response = await api_client.get(ENDPOINT, headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["entity_type"] == "program"


async def test_academic_structure_paginates(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    headers = await _admin_headers(auth_headers, factories)
    await _seed(test_db_session, [_row(entity_id=n) for n in range(1, 6)])

    first = await api_client.get(f"{ENDPOINT}?page=1&size=2", headers=headers)
    second = await api_client.get(f"{ENDPOINT}?page=2&size=2", headers=headers)

    assert first.status_code == 200
    assert first.json()["total"] == 5
    assert len(first.json()["items"]) == 2
    assert second.json()["page"] == 2
    # `performed_at` is server-assigned and identical within one batch, so the
    # id tiebreak is what makes paging deterministic.
    assert [item["entity_id"] for item in first.json()["items"]] == [5, 4]
    assert [item["entity_id"] for item in second.json()["items"]] == [3, 2]


async def test_academic_structure_records_the_actor(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    admin = await factories.user(role=UserRole.ADMIN.value)
    await test_db_session.commit()
    headers = await auth_headers(admin)

    created = await api_client.post(
        "/api/admin/programs",
        json={"code": "BSCS", "name": "BS Computer Science", "total_years": 4},
        headers=headers,
    )
    assert created.status_code == 201
    program_id = created.json()["id"]

    listed = await api_client.get(ENDPOINT, headers=headers)

    assert listed.status_code == 200
    (item,) = listed.json()["items"]
    assert item["action"] == "create"
    assert item["entity_type"] == "program"
    assert item["entity_id"] == program_id
    assert item["performed_by"] == admin.id
    assert item["old_value"] is None
    assert item["new_value"]["code"] == "BSCS"


async def test_academic_structure_stores_the_before_and_after(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    admin = await factories.user(role=UserRole.ADMIN.value)
    program = await factories.program(code="BSIT", name="BS Information Tech")
    await test_db_session.commit()
    headers = await auth_headers(admin)

    response = await api_client.patch(
        f"/api/admin/programs/{program.id}",
        json={"name": "BS Information Technology"},
        headers=headers,
    )

    assert response.status_code == 200
    rows = (
        await test_db_session.scalars(
            select(AuditLog)
            .where(AuditLog.entity_type == "program")
            .order_by(AuditLog.id.desc())
        )
    ).all()
    (row,) = rows
    assert row.action == "update"
    assert row.entity_id == program.id
    assert row.old_value["name"] == "BS Information Tech"
    assert row.new_value["name"] == "BS Information Technology"
    assert row.performed_by == admin.id


async def test_academic_structure_records_a_delete(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    admin = await factories.user(role=UserRole.ADMIN.value)
    program = await factories.program()
    year = await factories.year_level(program)
    await test_db_session.commit()
    headers = await auth_headers(admin)

    response = await api_client.delete(
        f"/api/admin/programs/{program.id}/years/{year.id}", headers=headers
    )

    assert response.status_code == 204
    (row,) = (
        await test_db_session.scalars(
            select(AuditLog).where(AuditLog.entity_type == "year_level")
        )
    ).all()
    assert row.action == "delete"
    assert row.entity_id == year.id
    assert row.new_value is None
    assert row.old_value["year_number"] == year.year_number


async def test_academic_structure_rolls_back_with_a_failed_mutation(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    """A rejected mutation must not leave an audit row behind."""
    admin = await factories.user(role=UserRole.ADMIN.value)
    await factories.program(code="BSCS")
    await test_db_session.commit()
    headers = await auth_headers(admin)

    rejected = await api_client.post(
        "/api/admin/programs",
        json={"code": "BSCS", "name": "Duplicate", "total_years": 4},
        headers=headers,
    )

    assert rejected.status_code == 409
    assert (await test_db_session.scalars(select(AuditLog))).all() == []


async def test_academic_structure_requires_admin(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    student_user = await factories.user()

    response = await api_client.get(ENDPOINT, headers=await auth_headers(student_user))

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "insufficient_permissions"


async def test_academic_structure_requires_auth(api_client: Any) -> None:
    assert (await api_client.get(ENDPOINT)).status_code == 401


@pytest.mark.parametrize("query", ["page=0", "size=0", "size=201"])
async def test_academic_structure_rejects_bad_pagination(
    api_client: Any, auth_headers: Any, factories: Factories, query: str
) -> None:
    headers = await _admin_headers(auth_headers, factories)

    response = await api_client.get(f"{ENDPOINT}?{query}", headers=headers)

    assert response.status_code == 422
