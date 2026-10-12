"""Archive/reactivate/hard-delete must sync the login gate.

Auth (`AuthService.login`, `refresh_token`, `_get_active_user`) gates only on
`users.is_active`, while Student Management writes `students.is_active`. This
suite pins the cascade: archiving deactivates the linked login, reactivating
restores it, and hard-delete deactivates the orphan instead of leaving it
login-capable.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import _get_active_user
from core.security import hash_password
from features.auth.exceptions import InvalidCredentialsException
from features.auth.model import User
from features.auth.service import AuthService
from features.student.service import StudentService
from features.system.model import AuditLog
from shared.enums import AuditAction, AuditEntity
from tests.conftest import Factories

PASSWORD = "correct-horse-battery-staple"


async def _reload_user(session: AsyncSession, user_id: int) -> User:
    user = await session.get(User, user_id)
    assert user is not None
    return user


async def _user_audit_rows(
    session: AsyncSession, user_id: int
) -> list[AuditLog]:
    rows = await session.scalars(
        select(AuditLog)
        .where(
            AuditLog.entity_type == AuditEntity.USER.value,
            AuditLog.entity_id == user_id,
        )
        .order_by(AuditLog.id)
    )
    return list(rows.all())


async def test_archive_deactivates_linked_user_and_blocks_login(
    test_db_session: AsyncSession, factories: Factories, settings: Any
) -> None:
    program = await factories.program()
    year = await factories.year_level(program)
    user = await factories.user(password_hash=hash_password(PASSWORD))
    student = await factories.student(year, user=user)

    await StudentService(test_db_session).archive(
        student_id=student.id, actor_id=user.id
    )

    db_user = await _reload_user(test_db_session, user.id)
    assert db_user.is_active is False

    with pytest.raises(InvalidCredentialsException):
        await AuthService(test_db_session, settings).login(user.email, PASSWORD)

    assert await _get_active_user(test_db_session, user.id) is None

    rows = await _user_audit_rows(test_db_session, user.id)
    assert len(rows) == 1
    assert rows[0].action == AuditAction.UPDATE
    assert rows[0].old_value == {"is_active": True}
    assert rows[0].new_value == {"is_active": False}


async def test_reactivate_restores_login(
    test_db_session: AsyncSession, factories: Factories, settings: Any
) -> None:
    program = await factories.program()
    year = await factories.year_level(program)
    user = await factories.user(password_hash=hash_password(PASSWORD))
    student = await factories.student(year, user=user)
    service = StudentService(test_db_session)

    await service.archive(student_id=student.id, actor_id=user.id)
    await service.reactivate(student_id=student.id, actor_id=user.id)

    db_user = await _reload_user(test_db_session, user.id)
    assert db_user.is_active is True

    tokens = await AuthService(test_db_session, settings).login(user.email, PASSWORD)
    assert tokens.mfa_pending is False
    assert await _get_active_user(test_db_session, user.id) is not None


async def test_archive_unclaimed_student_is_noop(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    program = await factories.program()
    year = await factories.year_level(program)
    student = await factories.student(year, user=None)
    assert student.user_id is None

    result = await StudentService(test_db_session).archive(
        student_id=student.id, actor_id=None
    )
    assert result.is_active is False


async def test_archive_is_idempotent_for_audit(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    program = await factories.program()
    year = await factories.year_level(program)
    user = await factories.user(password_hash=hash_password(PASSWORD))
    student = await factories.student(year, user=user)
    service = StudentService(test_db_session)

    await service.archive(student_id=student.id, actor_id=user.id)
    await service.archive(student_id=student.id, actor_id=user.id)

    rows = await _user_audit_rows(test_db_session, user.id)
    assert len(rows) == 1


async def test_hard_delete_deactivates_linked_user_but_keeps_row(
    test_db_session: AsyncSession, factories: Factories, settings: Any
) -> None:
    program = await factories.program()
    year = await factories.year_level(program)
    user = await factories.user(password_hash=hash_password(PASSWORD))
    student = await factories.student(year, user=user)
    service = StudentService(test_db_session)

    await service.archive(student_id=student.id, actor_id=user.id)
    await service.hard_delete(student_id=student.id, actor_id=user.id)

    # Roster row gone, login row retained but inactive.
    db_user = await _reload_user(test_db_session, user.id)
    assert db_user.is_active is False

    with pytest.raises(InvalidCredentialsException):
        await AuthService(test_db_session, settings).login(user.email, PASSWORD)
    assert await _get_active_user(test_db_session, user.id) is None


async def test_roster_reactivate_wins_over_prior_user_deactivate(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """Document last-writer-wins: restore re-enables the login.

    A separate `PATCH /admin/users/{id}/deactivate` followed by a roster
    restore ends active. The decision log records this contract; a ban that
    must survive a restore has to be re-applied afterwards.
    """
    program = await factories.program()
    year = await factories.year_level(program)
    user = await factories.user(password_hash=hash_password(PASSWORD))
    student = await factories.student(year, user=user)
    service = StudentService(test_db_session)

    user.is_active = False
    await test_db_session.flush()
    await service.reactivate(student_id=student.id, actor_id=user.id)

    db_user = await _reload_user(test_db_session, user.id)
    assert db_user.is_active is True
