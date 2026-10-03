"""`GET /admin/audit-logs` — the read side of the audit trail.

The write side is asserted next to each service that writes (see
`test_roster_import.py`, `test_face_enrollment_service.py`,
`test_offering_service.py`, `test_login_lockout.py`). What is checked here is
the read contract: that every filter narrows correctly, that the two audit
endpoints stay scoped apart, and that an unrecognised filter value is rejected
rather than silently returning nothing.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from features.system.model import AuditLog
from shared.enums import AuditAction, AuditEntity, UserRole
from tests.conftest import Factories

ENDPOINT = "/api/admin/audit-logs"
STRUCTURAL_ENDPOINT = "/api/admin/system/academic-structure"


async def _admin_headers(
    auth_headers: Any, factories: Factories
) -> dict[str, str]:
    admin = await factories.user(role=UserRole.ADMIN.value)
    return await auth_headers(admin)


def _at(day: int, hour: int, minute: int = 0) -> datetime:
    """A September 2026 timestamp, for the date-range cases."""
    return datetime(2026, 9, day, hour, minute, tzinfo=timezone.utc)


def _row(**overrides: Any) -> AuditLog:
    values: dict[str, Any] = {
        "action": AuditAction.UPDATE,
        "entity_type": AuditEntity.PROGRAM,
        "entity_id": 1,
        "old_value": {"name": "Old"},
        "new_value": {"name": "New"},
        "performed_by": None,
        "performed_at": datetime(2026, 9, 20, 8, 0, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return AuditLog(**values)


async def _seed(session: AsyncSession, rows: list[AuditLog]) -> None:
    session.add_all(rows)
    await session.commit()


async def _items(
    api_client: Any, headers: dict[str, str], **params: Any
) -> list[dict[str, Any]]:
    response = await api_client.get(ENDPOINT, headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()["items"]


# --- shape and paging ------------------------------------------------------


async def test_audit_logs_starts_empty(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    headers = await _admin_headers(auth_headers, factories)

    response = await api_client.get(ENDPOINT, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "page": 1, "size": 20}


async def test_audit_logs_returns_the_stored_row_unshaped(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    """The read model is the table, not a derived view of it."""
    headers = await _admin_headers(auth_headers, factories)
    actor = await factories.user(role=UserRole.ADMIN.value)
    await _seed(
        test_db_session,
        [
            _row(performed_by=actor.id, entity_id=42),
        ],
    )

    (item,) = await _items(api_client, headers)

    assert set(item) == {
        "id",
        "action",
        "entity_type",
        "entity_id",
        "old_value",
        "new_value",
        "performed_by",
        "performed_at",
    }
    assert item["action"] == "update"
    assert item["entity_type"] == "program"
    assert item["entity_id"] == 42
    assert item["performed_by"] == actor.id
    assert item["old_value"] == {"name": "Old"}


async def test_audit_logs_orders_newest_first_with_id_tiebreak(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    headers = await _admin_headers(auth_headers, factories)
    same = datetime(2026, 9, 20, 8, 0, tzinfo=timezone.utc)
    await _seed(
        test_db_session,
        [
            _row(entity_type=AuditEntity.COURSE, performed_at=same),
            _row(entity_type=AuditEntity.STUDENT, performed_at=same),
            _row(
                entity_type=AuditEntity.SESSION,
                performed_at=same - timedelta(days=1),
            ),
        ],
    )

    items = await _items(api_client, headers)

    # Equal timestamps resolve by descending id, so paging cannot repeat or
    # skip a row.
    assert [i["entity_type"] for i in items] == ["student", "course", "session"]


async def test_audit_logs_paginates(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    headers = await _admin_headers(auth_headers, factories)
    await _seed(
        test_db_session,
        [
            _row(entity_type=AuditEntity.COURSE, entity_id=index)
            for index in range(1, 6)
        ],
    )

    first = await _items(api_client, headers, page=1, size=2)
    second = await _items(api_client, headers, page=2, size=2)

    assert len(first) == 2
    assert len(second) == 2
    assert {i["entity_id"] for i in first}.isdisjoint(
        {i["entity_id"] for i in second}
    )

    response = await api_client.get(ENDPOINT, headers=headers, params={"size": 2})
    assert response.json()["total"] == 5


# --- filters ---------------------------------------------------------------


async def test_filter_by_entity_type(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    headers = await _admin_headers(auth_headers, factories)
    await _seed(
        test_db_session,
        [
            _row(entity_type=AuditEntity.EXCUSE, entity_id=1),
            _row(entity_type=AuditEntity.EXCUSE, entity_id=2),
            _row(entity_type=AuditEntity.SESSION, entity_id=3),
        ],
    )

    items = await _items(api_client, headers, entity_type=AuditEntity.EXCUSE)

    assert [i["entity_id"] for i in items] == [2, 1]


async def test_filter_by_action(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    headers = await _admin_headers(auth_headers, factories)
    await _seed(
        test_db_session,
        [
            _row(action=AuditAction.LOCK, entity_id=1),
            _row(action=AuditAction.LOGIN_FAILED, entity_id=2),
        ],
    )

    items = await _items(api_client, headers, action=AuditAction.LOCK)

    assert [i["entity_id"] for i in items] == [1]


async def test_filter_by_performed_by(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    headers = await _admin_headers(auth_headers, factories)
    actor = await factories.user(role=UserRole.ADMIN.value)
    await _seed(
        test_db_session,
        [
            _row(performed_by=actor.id, entity_id=1),
            _row(performed_by=None, entity_id=2),
        ],
    )

    items = await _items(api_client, headers, performed_by=actor.id)

    assert [i["entity_id"] for i in items] == [1]


async def test_date_range_is_inclusive_of_both_days(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    headers = await _admin_headers(auth_headers, factories)
    await _seed(
        test_db_session,
        [
            _row(entity_id=1, performed_at=_at(18, 23, 59)),
            _row(entity_id=2, performed_at=_at(19, 0, 0)),
            _row(entity_id=3, performed_at=_at(19, 23, 59)),
            _row(entity_id=4, performed_at=_at(20, 0, 0)),
        ],
    )

    items = await _items(
        api_client, headers, date_from="2026-09-19", date_to="2026-09-19"
    )

    assert sorted(i["entity_id"] for i in items) == [2, 3]


async def test_single_day_range_selects_that_day(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    headers = await _admin_headers(auth_headers, factories)
    await _seed(
        test_db_session,
        [
            _row(entity_id=1, performed_at=_at(19, 12)),
            _row(entity_id=2, performed_at=_at(20, 12)),
        ],
    )

    items = await _items(
        api_client, headers, date_from="2026-09-19", date_to="2026-09-19"
    )

    assert [i["entity_id"] for i in items] == [1]


async def test_filters_combine(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    headers = await _admin_headers(auth_headers, factories)
    actor = await factories.user(role=UserRole.ADMIN.value)
    await _seed(
        test_db_session,
        [
            _row(
                entity_type=AuditEntity.EXCUSE,
                action=AuditAction.APPROVE,
                performed_by=actor.id,
                entity_id=1,
            ),
            _row(
                entity_type=AuditEntity.EXCUSE,
                action=AuditAction.REJECT,
                performed_by=actor.id,
                entity_id=2,
            ),
            _row(
                entity_type=AuditEntity.SESSION,
                action=AuditAction.APPROVE,
                performed_by=actor.id,
                entity_id=3,
            ),
            _row(
                entity_type=AuditEntity.EXCUSE,
                action=AuditAction.APPROVE,
                performed_by=None,
                entity_id=4,
            ),
        ],
    )

    items = await _items(
        api_client,
        headers,
        entity_type=AuditEntity.EXCUSE,
        action=AuditAction.APPROVE,
        performed_by=actor.id,
    )

    assert [i["entity_id"] for i in items] == [1]


# --- rejected filters ------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "entity_type=not_a_thing",
        "action=not_a_thing",
        "date_from=2026-09-20&date_to=2026-09-19",
    ],
)
async def test_invalid_filter_is_422_not_an_empty_page(
    api_client: Any, auth_headers: Any, factories: Factories, query: str
) -> None:
    """An unknown filter must fail loudly.

    Silently matching nothing is indistinguishable from "no such activity",
    which is the one conclusion an audit query must never let a reader draw by
    accident.
    """
    headers = await _admin_headers(auth_headers, factories)

    response = await api_client.get(f"{ENDPOINT}?{query}", headers=headers)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] in {
        "invalid_audit_filter",
        "invalid_audit_date_range",
    }


async def test_empty_filter_string_is_not_rejected_as_unknown(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """`?entity_type=` is "no filter", not "unknown entity type"."""
    headers = await _admin_headers(auth_headers, factories)

    response = await api_client.get(f"{ENDPOINT}?entity_type=&action=", headers=headers)

    assert response.status_code == 200


@pytest.mark.parametrize("query", ["page=0", "size=0", "size=201", "performed_by=0"])
async def test_rejects_bad_pagination_and_actor(
    api_client: Any, auth_headers: Any, factories: Factories, query: str
) -> None:
    headers = await _admin_headers(auth_headers, factories)

    response = await api_client.get(f"{ENDPOINT}?{query}", headers=headers)

    assert response.status_code == 422


# --- the two audit endpoints stay apart ------------------------------------


async def test_non_structural_rows_are_absent_from_academic_structure(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    """The structural view stays pinned to the four structural entity types.

    Widening it would change an endpoint that already has published consumers;
    the wider trail is what `/admin/audit-logs` is for.
    """
    headers = await _admin_headers(auth_headers, factories)
    await _seed(
        test_db_session,
        [
            _row(entity_type=AuditEntity.PROGRAM),
            _row(entity_type=AuditEntity.EXCUSE),
            _row(entity_type=AuditEntity.USER),
        ],
    )

    trail = await api_client.get(ENDPOINT, headers=headers)
    structure = await api_client.get(STRUCTURAL_ENDPOINT, headers=headers)

    assert trail.json()["total"] == 3
    assert structure.json()["total"] == 1
    assert structure.json()["items"][0]["entity_type"] == "program"


async def test_structural_rows_appear_in_both(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    headers = await _admin_headers(auth_headers, factories)
    await _seed(
        test_db_session,
        [_row(entity_type=AuditEntity.COURSE_OFFERING)],
    )

    trail = await api_client.get(ENDPOINT, headers=headers)
    structure = await api_client.get(STRUCTURAL_ENDPOINT, headers=headers)

    assert trail.json()["total"] == 1
    assert structure.json()["total"] == 1
    # Same row, both shapes name the same columns.
    assert set(trail.json()["items"][0]) == set(structure.json()["items"][0])


# --- authorization ---------------------------------------------------------


@pytest.mark.parametrize("role", [UserRole.STUDENT.value, UserRole.PROFESSOR.value])
async def test_audit_logs_requires_admin(
    api_client: Any, auth_headers: Any, factories: Factories, role: str
) -> None:
    user = await factories.user(role=role)

    response = await api_client.get(ENDPOINT, headers=await auth_headers(user))

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "insufficient_permissions"


async def test_super_admin_passes_the_admin_guard(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    root = await factories.user(role=UserRole.SUPER_ADMIN.value)

    response = await api_client.get(ENDPOINT, headers=await auth_headers(root))

    assert response.status_code == 200


async def test_audit_logs_requires_auth(api_client: Any) -> None:
    assert (await api_client.get(ENDPOINT)).status_code == 401


# --- a real mutation shows up ----------------------------------------------


async def test_program_create_appears_in_the_trail(
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
        json={"code": "BSCS", "name": "Computer Science", "total_years": 4},
        headers=headers,
    )
    assert created.status_code == 201

    (item,) = await _items(api_client, headers, action=AuditAction.CREATE)

    assert item["entity_type"] == "program"
    assert item["entity_id"] == created.json()["id"]
    assert item["performed_by"] == admin.id
    assert item["new_value"]["code"] == "BSCS"


async def test_date_filter_accepts_a_date_object(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """A `date` passed as a query param serialises to `YYYY-MM-DD` and binds."""
    headers = await _admin_headers(auth_headers, factories)
    today = date.today()

    response = await api_client.get(
        ENDPOINT,
        headers=headers,
        params={"date_from": today, "date_to": today},
    )

    assert response.status_code == 200