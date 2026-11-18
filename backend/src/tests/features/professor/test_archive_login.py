"""Professor archive/reactivate/hard-delete must sync the login gate.

Same contract as the student slice: auth gates only on `users.is_active`,
so the roster cascade owns deactivating and restoring the linked login.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.security import hash_password

from shared.enums import AuditAction, AuditEntity

from api.deps import _get_active_user
from features.auth.exceptions import InvalidCredentialsException
from features.auth.model import User
from features.auth.service import AuthService
from features.professor.service import ProfessorService
from features.system.model import AuditLog
from tests.conftest import Factories

PASSWORD = "correct-horse-battery-staple"


async def _reload_user(session: AsyncSession, user_id: int) -> User:
    user = await session.get(User, user_id)
    assert user is not None
    return user


async def test_archive_deactivates_linked_user_and_blocks_login(
    test_db_session: AsyncSession, factories: Factories, settings: Any
) -> None:
    user = await factories.user(password_hash=hash_password(PASSWORD), role="professor")
    professor = await factories.professor(user=user)

    await ProfessorService(test_db_session).archive(
        professor_id=professor.id, actor_id=user.id
    )

    db_user = await _reload_user(test_db_session, user.id)
    assert db_user.is_active is False

    with pytest.raises(InvalidCredentialsException):
        await AuthService(test_db_session, settings).login(user.email, PASSWORD)
    assert await _get_active_user(test_db_session, user.id) is None

    rows = list(
        (
            await test_db_session.scalars(
                select(AuditLog)
                .where(
                    AuditLog.entity_type == AuditEntity.USER.value,
                    AuditLog.entity_id == user.id,
                )
                .order_by(AuditLog.id)
            )
        ).all()
    )
    assert len(rows) == 1
    assert rows[0].action == AuditAction.UPDATE
    assert rows[0].new_value == {"is_active": False}


async def test_reactivate_restores_login(
    test_db_session: AsyncSession, factories: Factories, settings: Any
) -> None:
    user = await factories.user(password_hash=hash_password(PASSWORD), role="professor")
    professor = await factories.professor(user=user)
    service = ProfessorService(test_db_session)

    await service.archive(professor_id=professor.id, actor_id=user.id)
    await service.reactivate(professor_id=professor.id, actor_id=user.id)

    db_user = await _reload_user(test_db_session, user.id)
    assert db_user.is_active is True

    tokens = await AuthService(test_db_session, settings).login(user.email, PASSWORD)
    assert tokens.mfa_pending is False


async def test_update_is_active_true_restores_login(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """`PATCH /admin/professors/{id} {is_active:true}` must sync too.

    Unlike `reactivate()`, `update()` handles the True branch inline, so the
    cascade has to live there as well or the PATCH restore leaves the login
    dead.
    """
    from features.professor.schema import ProfessorUpdate

    user = await factories.user(password_hash=hash_password(PASSWORD), role="professor")
    professor = await factories.professor(user=user)
    service = ProfessorService(test_db_session)

    await service.archive(professor_id=professor.id, actor_id=user.id)
    await service.update(
        professor_id=professor.id,
        payload=ProfessorUpdate(is_active=True),
        assigned_by=user.id,
    )

    assert (await _reload_user(test_db_session, user.id)).is_active is True


async def test_hard_delete_deactivates_linked_user(
    test_db_session: AsyncSession, factories: Factories, settings: Any
) -> None:
    user = await factories.user(password_hash=hash_password(PASSWORD), role="professor")
    professor = await factories.professor(user=user)
    service = ProfessorService(test_db_session)

    await service.archive(professor_id=professor.id, actor_id=user.id)
    await service.hard_delete(professor_id=professor.id, actor_id=user.id)

    db_user = await _reload_user(test_db_session, user.id)
    assert db_user.is_active is False

    with pytest.raises(InvalidCredentialsException):
        await AuthService(test_db_session, settings).login(user.email, PASSWORD)
