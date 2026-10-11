"""Reclaim of deactivated logins on re-creation.

Hard-delete retains (and deactivates) the linked `users` row so audit history
stays joinable, which used to make re-creation impossible: roster re-create
succeeded, then `register()`/`create_user()` failed 409 on the still-taken
`users.email` while login failed `invalid_credentials` — a dead account.
`register()` and `AdminService.create_user()` now revive the inactive login
for a fresh, unclaimed roster row instead.

No live roster match, no revival: a ban without a roster row stays dead.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import _get_active_user
from core.security import hash_otp, hash_password, verify_password
from features.admin.exceptions import EmailAlreadyExists, RosterLinkImpossible
from features.admin.schema import AdminUserCreate
from features.admin.service import AdminService
from features.auth.exceptions import (
    InvalidCredentialsException,
    UnrecognizedEmailException,
    UserAlreadyClaimedException,
)
from features.auth.model import MfaBackupCodes, OtpCodes, User
from features.auth.service import AuthService
from features.student.service import StudentService
from features.system.model import AuditLog
from shared.enums import AuditAction, AuditEntity, OtpPurpose, UserRole
from tests.conftest import Factories

OLD_PASSWORD = "old-holder-pass-1"
NEW_PASSWORD = "new-holder-pass-2"
OTP = "123456"


async def _seed_claim_otp(session: AsyncSession, email: str) -> None:
    session.add(
        OtpCodes(
            email=email.lower(),
            purpose=OtpPurpose.CLAIM.value,
            otp_hash=hash_otp(OTP),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
    )
    await session.flush()


async def _register(
    session: AsyncSession,
    settings: Any,
    *,
    email: str,
    password: str = NEW_PASSWORD,
) -> Any:
    await _seed_claim_otp(session, email)
    return await AuthService(session, settings).register(
        email=email,
        otp_code=OTP,
        password=password,
        security_question="Pet?",
        security_answer="Cat",
    )


async def _user_audit_rows(session: AsyncSession, user_id: int) -> list[AuditLog]:
    rows = await session.scalars(
        select(AuditLog)
        .where(
            AuditLog.entity_type == AuditEntity.USER.value,
            AuditLog.entity_id == user_id,
        )
        .order_by(AuditLog.id)
    )
    return list(rows.all())


async def _user_activation_rows(
    session: AsyncSession, user_id: int
) -> list[AuditLog]:
    """USER rows that revive the login (`is_active` False -> True).

    Setup itself writes a USER deactivation row via the archive cascade, so
    "nothing was revived" must filter on the new value, not on row absence.
    """
    return [
        row
        for row in await _user_audit_rows(session, user_id)
        if row.action == AuditAction.UPDATE
        and (row.new_value or {}).get("is_active") is True
    ]


async def _hard_deleted_claim(
    session: AsyncSession, factories: Factories, *, email: str
) -> User:
    """A claimed student, archived + hard-deleted: login retained, inactive."""
    program = await factories.program()
    year = await factories.year_level(program)
    user = await factories.user(
        email=email, password_hash=hash_password(OLD_PASSWORD)
    )
    student = await factories.student(year, user=user, email=email)
    service = StudentService(session)
    await service.archive(student_id=student.id, actor_id=user.id)
    await service.hard_delete(student_id=student.id, actor_id=user.id)
    return user


# --- self-register reclaim --------------------------------------------------


async def test_register_reclaims_hard_deleted_student(
    test_db_session: AsyncSession, factories: Factories, settings: Any
) -> None:
    email = "rehire.student@isu.edu.ph"
    orphan = await _hard_deleted_claim(test_db_session, factories, email=email)

    with pytest.raises(InvalidCredentialsException):
        await AuthService(test_db_session, settings).login(email, OLD_PASSWORD)

    # Roster re-created (fresh row, new student_id, same email), then claimed.
    program = await factories.program()
    year = await factories.year_level(program)
    fresh = await factories.student(year, user=None, email=email)
    assert fresh.user_id is None

    tokens = await _register(test_db_session, settings, email=email)
    assert tokens.access_token

    await test_db_session.refresh(orphan)
    await test_db_session.refresh(fresh)
    assert orphan.is_active is True
    assert fresh.user_id == orphan.id

    # New credentials work, old ones do not.
    authed = await AuthService(test_db_session, settings).login(email, NEW_PASSWORD)
    assert authed.access_token
    assert await _get_active_user(test_db_session, orphan.id) is not None

    rows = await _user_audit_rows(test_db_session, orphan.id)
    assert any(
        row.action == AuditAction.UPDATE
        and row.old_value == {"is_active": False}
        and row.new_value == {"is_active": True}
        for row in rows
    )


async def test_register_active_dupe_still_409(
    test_db_session: AsyncSession, factories: Factories, settings: Any
) -> None:
    program = await factories.program()
    year = await factories.year_level(program)
    user = await factories.user(
        email="taken@isu.edu.ph", password_hash=hash_password(OLD_PASSWORD)
    )
    await factories.student(year, user=user, email="taken@isu.edu.ph")

    with pytest.raises(UserAlreadyClaimedException):
        await _register(test_db_session, settings, email="taken@isu.edu.ph")


async def test_register_inactive_orphan_without_roster_stays_dead(
    test_db_session: AsyncSession, factories: Factories, settings: Any
) -> None:
    orphan = await _hard_deleted_claim(
        test_db_session, factories, email="noroster@isu.edu.ph"
    )

    with pytest.raises(UnrecognizedEmailException):
        await _register(test_db_session, settings, email="noroster@isu.edu.ph")

    await test_db_session.refresh(orphan)
    assert orphan.is_active is False
    # Only the archive deactivation row from setup — no revival was recorded.
    assert await _user_activation_rows(test_db_session, orphan.id) == []


async def test_register_does_not_steal_claimed_match(
    test_db_session: AsyncSession, factories: Factories, settings: Any
) -> None:
    email = "contested@isu.edu.ph"
    orphan = await _hard_deleted_claim(test_db_session, factories, email=email)

    # Same email re-created but already claimed by somebody else's login.
    program = await factories.program()
    year = await factories.year_level(program)
    other = await factories.user(password_hash=hash_password(OLD_PASSWORD))
    taken = await factories.student(year, user=other, email=email)

    with pytest.raises(UserAlreadyClaimedException):
        await _register(test_db_session, settings, email=email)

    await test_db_session.refresh(orphan)
    await test_db_session.refresh(taken)
    assert orphan.is_active is False
    assert taken.user_id == other.id


async def test_register_reclaim_resets_mfa_lockout_and_credentials(
    test_db_session: AsyncSession, factories: Factories, settings: Any
) -> None:
    email = "locked.mfa@isu.edu.ph"
    orphan = await _hard_deleted_claim(test_db_session, factories, email=email)
    orphan.mfa_enabled = True
    orphan.mfa_secret = "JBSWY3DPEHPK3PXP"
    orphan.is_locked = True
    orphan.failed_login_attempts = 3
    test_db_session.add(
        MfaBackupCodes(
            user_id=orphan.id, code_hash="h1", code_fingerprint="f1"
        )
    )
    test_db_session.add(
        MfaBackupCodes(
            user_id=orphan.id, code_hash="h2", code_fingerprint="f2"
        )
    )
    await test_db_session.flush()

    program = await factories.program()
    year = await factories.year_level(program)
    await factories.student(year, user=None, email=email)

    await _register(test_db_session, settings, email=email)

    await test_db_session.refresh(orphan)
    assert orphan.is_active is True
    assert orphan.is_locked is False
    assert orphan.failed_login_attempts == 0
    assert orphan.mfa_enabled is False
    assert orphan.mfa_secret is None
    assert verify_password(NEW_PASSWORD, orphan.password_hash)
    assert not verify_password(OLD_PASSWORD, orphan.password_hash)

    remaining = await test_db_session.scalars(
        select(MfaBackupCodes).where(
            MfaBackupCodes.user_id == orphan.id,
            MfaBackupCodes.used_at.is_(None),
        )
    )
    assert list(remaining.all()) == []


# --- admin create-user reclaim ----------------------------------------------


def _admin_payload(email: str, **overrides: Any) -> AdminUserCreate:
    return AdminUserCreate(
        email=email,
        role=overrides.pop("role", UserRole.STUDENT),
        first_name=overrides.pop("first_name", "Ada"),
        last_name=overrides.pop("last_name", "Lovelace"),
        **overrides,
    )


async def test_admin_create_reclaims_inactive_login(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    email = "admin.rehire@isu.edu.ph"
    orphan = await _hard_deleted_claim(test_db_session, factories, email=email)
    admin = await factories.user(role=UserRole.SUPER_ADMIN.value)

    program = await factories.program()
    year = await factories.year_level(program)
    fresh = await factories.student(year, user=None, email=email)

    response = await AdminService(test_db_session).create_user(
        payload=_admin_payload(email), actor_id=admin.id
    )

    assert response.id == orphan.id
    assert response.is_active is True
    assert response.must_change_password is True
    assert response.temp_password

    await test_db_session.refresh(orphan)
    await test_db_session.refresh(fresh)
    assert orphan.is_active is True
    assert fresh.user_id == orphan.id

    rows = await _user_audit_rows(test_db_session, orphan.id)
    assert any(
        row.action == AuditAction.UPDATE
        and row.new_value == {"is_active": True}
        for row in rows
    )


async def test_admin_create_active_dupe_still_409(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    program = await factories.program()
    year = await factories.year_level(program)
    user = await factories.user(
        email="admin.taken@isu.edu.ph", password_hash=hash_password(OLD_PASSWORD)
    )
    await factories.student(year, user=user, email="admin.taken@isu.edu.ph")
    admin = await factories.user(role=UserRole.SUPER_ADMIN.value)

    with pytest.raises(EmailAlreadyExists):
        await AdminService(test_db_session).create_user(
            payload=_admin_payload("admin.taken@isu.edu.ph"), actor_id=admin.id
        )


async def test_admin_create_inactive_without_roster_stays_dead(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    orphan = await _hard_deleted_claim(
        test_db_session, factories, email="admin.noroster@isu.edu.ph"
    )
    admin = await factories.user(role=UserRole.SUPER_ADMIN.value)

    with pytest.raises(RosterLinkImpossible):
        await AdminService(test_db_session).create_user(
            payload=_admin_payload("admin.noroster@isu.edu.ph"), actor_id=admin.id
        )

    await test_db_session.refresh(orphan)
    assert orphan.is_active is False


async def test_admin_create_reclaim_adopts_new_role(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """Same email re-hired as the other roster type takes that role."""
    email = "role.switch@isu.edu.ph"
    orphan = await _hard_deleted_claim(test_db_session, factories, email=email)
    assert orphan.role == UserRole.STUDENT.value
    admin = await factories.user(role=UserRole.SUPER_ADMIN.value)

    professor = await factories.professor(user=None, email=email)

    response = await AdminService(test_db_session).create_user(
        payload=_admin_payload(
            email, role=UserRole.PROFESSOR, first_name="Grace", last_name="Hopper"
        ),
        actor_id=admin.id,
    )

    assert response.id == orphan.id
    await test_db_session.refresh(orphan)
    await test_db_session.refresh(professor)
    assert orphan.role == UserRole.PROFESSOR.value
    assert professor.user_id == orphan.id
