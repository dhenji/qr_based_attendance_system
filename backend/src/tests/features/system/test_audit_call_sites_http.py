"""Audit rows written by the mutations across the feature slices.

`test_audit_logs_http.py` covers the read endpoint and the two hand-rolled
fake-session suites assert their own writes. What is left is the set of
mutations that only exist behind an HTTP route: this file drives them and
checks the row that lands.

The recurring assertion is the rollback coupling. `record_audit` flushes into
the caller's transaction rather than committing, so a mutation the backend
rejects must leave no trail either — an audit trail that records attempts which
never took effect is worse than none.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from features.system.model import AuditLog
from shared.enums import AuditAction, AuditEntity, UserRole
from tests.conftest import Factories

AUDIT_ENDPOINT = "/api/admin/audit-logs"


async def _headers(
    auth_headers: Any, factories: Factories, role: str = UserRole.ADMIN.value
) -> dict[str, str]:
    return await auth_headers(await factories.user(role=role))


async def _assigned_professor(
    factories: Factories, auth_headers: Any
) -> tuple[dict[str, Any], dict[str, str], Any]:
    """A professor who is actually assigned to the offering, plus their headers.

    `POST /professor/sessions` requires both the PROFESSOR role and a teaching
    assignment on the offering, and `full_stack` seeds neither: its professor
    row is unclaimed and unassigned.
    """
    # `full_stack` seeds an active session, which would make the create a 409.
    stack = await factories.full_stack(
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1)
    )
    professor_user = await factories.user(role=UserRole.PROFESSOR.value)
    stack["professor"].user_id = professor_user.id
    assigner = await factories.user(role=UserRole.ADMIN.value)
    await factories.assignment(
        stack["offering"], stack["professor"], assigner
    )
    return stack, await auth_headers(professor_user), professor_user


async def _rows(
    session: AsyncSession,
    entity_type: AuditEntity,
    entity_id: int | None = None,
) -> list[AuditLog]:
    stmt = select(AuditLog).where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    return list((await session.scalars(stmt.order_by(AuditLog.id))).all())


# --- student archive / reactivate -----------------------------------------


async def test_archive_writes_one_row(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    program = await factories.program()
    year = await factories.year_level(program)
    student = await factories.student(year)
    await test_db_session.commit()
    headers = await _headers(auth_headers, factories)

    response = await api_client.patch(
        f"/api/admin/students/{student.id}",
        json={"is_active": False},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False

    (row,) = await _rows(test_db_session, AuditEntity.STUDENT, student.id)
    assert row.action == AuditAction.ARCHIVE
    assert row.performed_by is not None
    assert row.old_value["is_active"] is True
    assert row.new_value["is_active"] is False
    # Archiving revokes the face, and the trail records that without the blob.
    assert row.new_value["face_embedding_version"] == 1
    assert "face_embedding" not in row.new_value


async def test_archive_via_patch_is_not_double_logged(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    """`update()` delegates to `archive()`, so the PATCH must yield one row."""
    program = await factories.program()
    year = await factories.year_level(program)
    student = await factories.student(year)
    await test_db_session.commit()
    headers = await _headers(auth_headers, factories)

    await api_client.patch(
        f"/api/admin/students/{student.id}",
        json={"is_active": False, "section": "C3"},
        headers=headers,
    )

    assert len(await _rows(test_db_session, AuditEntity.STUDENT, student.id)) == 1


async def test_reactivate_writes_one_row(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    program = await factories.program()
    year = await factories.year_level(program)
    student = await factories.student(year, is_active=False)
    await test_db_session.commit()
    headers = await _headers(auth_headers, factories)

    response = await api_client.patch(
        f"/api/admin/students/{student.id}",
        json={"is_active": True},
        headers=headers,
    )

    assert response.status_code == 200
    (row,) = await _rows(test_db_session, AuditEntity.STUDENT, student.id)
    assert row.action == AuditAction.UPDATE
    assert row.old_value["is_active"] is False
    assert row.new_value["is_active"] is True


async def test_rejected_mutation_leaves_no_trail(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    """A 409 must roll the audit row back with the mutation."""
    program = await factories.program()
    year = await factories.year_level(program)
    other = await factories.student(year)
    await factories.student(year, email="taken@example.com")
    # Read the id before the request: the 409 rolls the session back, which
    # expires every instance and makes the next attribute access a lazy load.
    other_id = other.id
    await test_db_session.commit()
    headers = await _headers(auth_headers, factories)

    rejected = await api_client.patch(
        f"/api/admin/students/{other_id}",
        json={"email": "taken@example.com"},
        headers=headers,
    )

    assert rejected.status_code == 409
    assert await _rows(test_db_session, AuditEntity.STUDENT, other_id) == []


# --- professor archive -----------------------------------------------------


async def test_professor_archive_writes_one_row(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    professor = await factories.professor()
    await test_db_session.commit()
    headers = await _headers(auth_headers, factories)

    response = await api_client.patch(
        f"/api/admin/professors/{professor.id}",
        json={"is_active": False},
        headers=headers,
    )

    assert response.status_code == 200
    (row,) = await _rows(test_db_session, AuditEntity.PROFESSOR, professor.id)
    assert row.action == AuditAction.ARCHIVE
    assert row.old_value["is_active"] is True


async def test_professor_hard_delete_writes_a_delete_row(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    professor = await factories.professor(is_active=False)
    await test_db_session.commit()
    headers = await _headers(auth_headers, factories)

    response = await api_client.delete(
        f"/api/admin/professors/{professor.id}/archive", headers=headers
    )

    assert response.status_code == 204
    (row,) = await _rows(test_db_session, AuditEntity.PROFESSOR, professor.id)
    assert row.action == AuditAction.DELETE
    assert row.new_value is None
    assert row.old_value["email"] == professor.email


async def test_blocked_hard_delete_leaves_no_trail(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    """The has-records guard rejects the delete, so no row may survive."""
    program = await factories.program()
    year = await factories.year_level(program)
    student = await factories.student(year)
    course = await factories.course()
    offering = await factories.offering(course, program, year)
    professor = await factories.professor(is_active=False)
    admin = await factories.user(role=UserRole.ADMIN.value)
    await factories.assignment(offering, professor, admin)
    await factories.session(offering, professor)
    professor_id = professor.id
    await test_db_session.commit()
    headers = await auth_headers(admin)

    response = await api_client.delete(
        f"/api/admin/professors/{professor_id}/archive", headers=headers
    )

    assert response.status_code == 409
    assert await _rows(test_db_session, AuditEntity.PROFESSOR, professor_id) == []


# --- system settings -------------------------------------------------------


async def test_settings_patch_records_the_previous_value(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    headers = await _headers(auth_headers, factories)

    first = await api_client.patch(
        "/api/admin/system/settings",
        json={"present_window_default": 7},
        headers=headers,
    )
    assert first.status_code == 200

    await api_client.patch(
        "/api/admin/system/settings",
        json={"present_window_default": 11},
        headers=headers,
    )

    rows = await _rows(test_db_session, AuditEntity.APP_SETTING)
    assert len(rows) == 2
    latest = rows[-1]
    assert latest.action == AuditAction.UPDATE
    assert latest.entity_id is None
    # First write seeds the row, so there is no previous value to report.
    assert rows[0].old_value["present_window_default"] is None
    assert latest.old_value["present_window_default"] == "7"
    assert latest.new_value["present_window_default"] == "11"
    # Only the field that was sent.
    assert set(latest.new_value) == {"present_window_default"}


async def test_settings_patch_with_nothing_writes_no_row(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    headers = await _headers(auth_headers, factories)

    await api_client.patch("/api/admin/system/settings", json={}, headers=headers)

    assert await _rows(test_db_session, AuditEntity.APP_SETTING) == []


# --- session open / close --------------------------------------------------


async def test_open_and_close_write_a_row_each(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    stack, headers, _ = await _assigned_professor(factories, auth_headers)
    offering_id = stack["offering"].id

    opened = await api_client.post(
        "/api/professor/sessions",
        json={"offering_id": offering_id},
        headers=headers,
    )
    assert opened.status_code == 201, opened.text
    session_id = opened.json()["id"]

    (open_row,) = await _rows(test_db_session, AuditEntity.SESSION, session_id)
    assert open_row.action == AuditAction.OPEN
    assert open_row.old_value is None
    # Recorded after the code and expiry were stamped, so both are the real ones.
    assert open_row.new_value["session_code"] == opened.json()["session_code"]
    assert open_row.new_value["expires_at"] is not None

    closed = await api_client.post(
        f"/api/professor/sessions/{session_id}/close", headers=headers
    )
    assert closed.status_code == 200

    rows = await _rows(test_db_session, AuditEntity.SESSION, session_id)
    assert [r.action for r in rows] == [AuditAction.OPEN, AuditAction.CLOSE]
    # The close moves the expiry back to now, so the two snapshots differ.
    assert rows[-1].old_value["expires_at"] != rows[-1].new_value["expires_at"]


async def test_closing_an_already_closed_session_writes_nothing(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    """The close is idempotent, and a no-op must not look like a close."""
    stack, headers, _ = await _assigned_professor(factories, auth_headers)

    opened = await api_client.post(
        "/api/professor/sessions",
        json={"offering_id": stack["offering"].id},
        headers=headers,
    )
    assert opened.status_code == 201, opened.text
    session_id = opened.json()["id"]

    close_url = f"/api/professor/sessions/{session_id}/close"
    await api_client.post(close_url, headers=headers)
    await api_client.post(close_url, headers=headers)

    rows = await _rows(test_db_session, AuditEntity.SESSION, session_id)
    assert [r.action for r in rows] == [AuditAction.OPEN, AuditAction.CLOSE]


# --- the trail is admin-only even though professors write to it ------------


async def test_a_professor_opened_session_is_attributed_to_them(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    stack, headers, professor_user = await _assigned_professor(
        factories, auth_headers
    )

    opened = await api_client.post(
        "/api/professor/sessions",
        json={"offering_id": stack["offering"].id},
        headers=headers,
    )

    assert opened.status_code == 201, opened.text
    (row,) = await _rows(test_db_session, AuditEntity.SESSION, opened.json()["id"])
    assert row.performed_by == professor_user.id


@pytest.mark.parametrize("role", [UserRole.PROFESSOR.value, UserRole.STUDENT.value])
async def test_non_admins_cannot_read_the_trail(
    api_client: Any, auth_headers: Any, factories: Factories, role: str
) -> None:
    user = await factories.user(role=role)

    response = await api_client.get(AUDIT_ENDPOINT, headers=await auth_headers(user))

    assert response.status_code == 403