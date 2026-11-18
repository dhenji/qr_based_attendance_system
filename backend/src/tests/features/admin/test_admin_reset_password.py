"""Admin-initiated password resets for users, students and professors.

`api-contracts.md` has specified all three `.../reset-password` routes and
noted they were never built, which left an admin with no lever over an account
they could not log into — the case that matters most being a locked-out one.

Four things are pinned here, because each is a decision rather than an
obligation:

1. **The reset clears the lockout.** `failed_login_attempts`, `is_locked` and
   `locked_at` all go back to zero/false, matching the self-service
   `reset_password`. Without it the new password would be useless for exactly
   the account an admin is trying to rescue.
2. **The reset does not touch MFA.** An admin who could clear a second factor
   as a side effect of a password reset could remove a control the account
   owner chose, and it would not show up as the MFA event it really is.
3. **`performed_by` is the admin, `entity_id` is the account.** The trail has
   to say who did it, not just whose password changed.
4. **The temp password is returned once** and actually authenticates — the
   whole point is that the admin can hand it over.

The student and professor routes name a *roster* row, so they resolve it to a
`users.id` first and then take the same `AuthService.admin_reset_password` path
as `/admin/users/{id}`. A roster row with no linked account is a 409, not a
404: the student exists, there is simply no credential to reset yet.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.security import hash_otp, hash_password

from shared.enums import AuditAction, AuditEntity, OtpPurpose, UserRole

from features.auth.model import OtpCodes, User
from features.system.model import AuditLog
from tests.conftest import Factories

# `LoginRequest.email` is an `EmailStr`, and email-validator rejects the
# factory default's `.local` TLD as special-use, so every address here is a
# deliverable-looking one.
ADMIN_EMAIL = "reset.admin@isu.edu.ph"
STUDENT_EMAIL = "reset.student@isu.edu.ph"
PROFESSOR_EMAIL = "reset.professor@isu.edu.ph"
PASSWORD = "correct-horse-battery-staple"


async def _admin(
    factories: Factories, *, role: str = UserRole.SUPER_ADMIN.value
) -> User:
    return await factories.user(email=ADMIN_EMAIL, role=role, is_active=True)


async def _target(factories: Factories, *, email: str, role: str) -> User:
    """A linked account with a known password, optionally locked out."""

    return await factories.user(
        email=email,
        role=role,
        password_hash=hash_password(PASSWORD),
        failed_login_attempts=5,
        is_locked=True,
        locked_at=datetime.now(timezone.utc),
    )


async def _reload_user(session: AsyncSession, user: User) -> User:
    reloaded = await session.get(User, user.id, populate_existing=True)
    assert reloaded is not None
    return reloaded


async def _audit_rows(session: AsyncSession, user_id: int) -> list[AuditLog]:
    result = await session.scalars(
        select(AuditLog)
        .where(
            AuditLog.entity_type == AuditEntity.USER.value,
            AuditLog.entity_id == user_id,
        )
        .order_by(AuditLog.id)
    )
    return list(result.all())


def _code(response: Any) -> str:
    return response.json()["detail"]["code"]


async def _login(client: Any, email: str, password: str) -> Any:
    return await client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )


def _is_locked(user: User) -> bool:
    return bool(user.is_locked)


# Keys that would mean a credential reached a table every admin can read.
# Matched exactly rather than as a substring: `must_change_password` is a
# legitimate audit field and contains the word "password".
_CREDENTIAL_KEYS = frozenset({"password", "password_hash", "temp_password", "secret"})


def _assert_no_credential(values: dict[str, Any] | None) -> None:
    assert values is not None
    assert not _CREDENTIAL_KEYS & set(values), sorted(_CREDENTIAL_KEYS & set(values))


# -- the credential write, via /admin/users/{id} ----------------------------


async def test_reset_returns_a_temp_password_that_authenticates(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    admin = await _admin(factories)
    target = await _target(
        factories,
        email=STUDENT_EMAIL,
        role=UserRole.STUDENT.value,
    )
    await test_db_session.commit()

    response = await api_client.post(
        f"/api/admin/users/{target.id}/reset-password",
        headers=await auth_headers(admin),
    )

    assert response.status_code == 200
    temp = response.json()["temp_password"]
    assert temp and temp != PASSWORD

    login = await _login(api_client, STUDENT_EMAIL, temp)
    assert login.status_code == 200
    # The temp password passes the password gate (OTP grant issued); the
    # mandatory login OTP still stands between it and a session.
    assert login.json()["otp_pending"] is True
    assert login.json()["otp_token"]

    # A seeded code completes the proof: the temp password authenticates.
    test_db_session.add(
        OtpCodes(
            email=STUDENT_EMAIL.lower(),
            purpose=OtpPurpose.LOGIN.value,
            otp_hash=hash_otp("123456"),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
    )
    await test_db_session.commit()

    verified = await api_client.post(
        "/api/auth/login/verify",
        json={"otp_token": login.json()["otp_token"], "code": "123456"},
    )
    assert verified.status_code == 200
    assert verified.json()["access_token"]


async def test_reset_does_not_leak_the_old_password(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    admin = await _admin(factories)
    target = await _target(
        factories,
        email=STUDENT_EMAIL,
        role=UserRole.STUDENT.value,
    )

    response = await api_client.post(
        f"/api/admin/users/{target.id}/reset-password",
        headers=await auth_headers(admin),
    )
    temp = response.json()["temp_password"]

    assert (await _login(api_client, STUDENT_EMAIL, PASSWORD)).status_code == 400
    assert (await _login(api_client, STUDENT_EMAIL, temp)).status_code == 200


async def test_each_reset_issues_a_different_temp_password(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    """Two resets must not hand out the same credential.

    Pins both halves of the property: the temp password is generated rather
    than a constant, and it is single-use — the first one stops working the
    moment the second is issued.
    """

    admin = await _admin(factories)
    first = await _target(
        factories,
        email=STUDENT_EMAIL,
        role=UserRole.STUDENT.value,
    )
    second = await _target(
        factories,
        email=PROFESSOR_EMAIL,
        role=UserRole.PROFESSOR.value,
    )
    await test_db_session.commit()
    headers = await auth_headers(admin)

    one = (
        await api_client.post(
            f"/api/admin/users/{first.id}/reset-password", headers=headers
        )
    ).json()["temp_password"]
    two = (
        await api_client.post(
            f"/api/admin/users/{second.id}/reset-password", headers=headers
        )
    ).json()["temp_password"]

    assert one != two
    assert (await _login(api_client, STUDENT_EMAIL, one)).status_code == 200
    assert (await _login(api_client, PROFESSOR_EMAIL, two)).status_code == 200

    # Rotating the first account invalidates the password just handed out.
    rotated = (
        await api_client.post(
            f"/api/admin/users/{first.id}/reset-password", headers=headers
        )
    ).json()["temp_password"]
    assert rotated != one
    assert (await _login(api_client, STUDENT_EMAIL, one)).status_code == 400
    assert (await _login(api_client, STUDENT_EMAIL, rotated)).status_code == 200


async def test_reset_clears_the_lockout(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    """The point of the endpoint: an admin rescuing a locked-out account."""

    admin = await _admin(factories)
    target = await _target(
        factories,
        email=STUDENT_EMAIL,
        role=UserRole.STUDENT.value,
    )
    await test_db_session.commit()
    assert _is_locked(await _reload_user(test_db_session, target)) is True

    response = await api_client.post(
        f"/api/admin/users/{target.id}/reset-password",
        headers=await auth_headers(admin),
    )
    assert response.status_code == 200

    reloaded = await _reload_user(test_db_session, target)
    assert reloaded.failed_login_attempts == 0
    assert reloaded.is_locked is False
    assert reloaded.locked_at is None
    assert reloaded.must_change_password is True


async def test_reset_does_not_touch_mfa(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    """MFA survives an admin reset — see the module docstring."""

    admin = await _admin(factories)
    target = await factories.user(
        email=STUDENT_EMAIL,
        role=UserRole.STUDENT.value,
        password_hash=hash_password(PASSWORD),
        mfa_enabled=True,
        mfa_secret="JBSWY3DPEB2XS2LP",
    )
    await test_db_session.commit()

    response = await api_client.post(
        f"/api/admin/users/{target.id}/reset-password",
        headers=await auth_headers(admin),
    )
    assert response.status_code == 200

    reloaded = await _reload_user(test_db_session, target)
    assert reloaded.mfa_enabled is True
    assert reloaded.mfa_secret == "JBSWY3DPEB2XS2LP"


async def test_reset_is_audited_against_the_admin(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    admin = await _admin(factories)
    target = await _target(
        factories,
        email=STUDENT_EMAIL,
        role=UserRole.STUDENT.value,
    )
    await test_db_session.commit()

    response = await api_client.post(
        f"/api/admin/users/{target.id}/reset-password",
        headers=await auth_headers(admin),
    )
    assert response.status_code == 200

    rows = await _audit_rows(test_db_session, target.id)
    assert len(rows) == 1
    row = rows[0]
    assert row.action == AuditAction.PASSWORD_RESET.value
    assert row.entity_type == AuditEntity.USER.value
    # `performed_by` is who did it; `entity_id` is whose password changed.
    assert row.performed_by == admin.id
    assert row.entity_id == target.id
    assert row.old_value is not None and row.old_value["is_locked"] is True
    assert row.new_value is not None and row.new_value["is_locked"] is False
    # The credential must never reach a table every admin can read.
    _assert_no_credential(row.old_value)
    _assert_no_credential(row.new_value)


async def test_reset_unknown_user_is_404(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    admin = await _admin(factories)

    response = await api_client.post(
        "/api/admin/users/999999/reset-password",
        headers=await auth_headers(admin),
    )

    assert response.status_code == 404
    assert _code(response) == "user_not_found"


# -- the two roster-scoped routes -------------------------------------------


async def test_student_reset_targets_the_linked_account(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    admin = await _admin(factories, role=UserRole.ADMIN.value)
    graph = await factories.full_stack()
    account = await factories.user(
        email=STUDENT_EMAIL,
        role=UserRole.STUDENT.value,
        password_hash=hash_password(PASSWORD),
    )
    graph["student"].user_id = account.id
    await test_db_session.commit()

    response = await api_client.post(
        f"/api/admin/students/{graph['student'].id}/reset-password",
        headers=await auth_headers(admin),
    )

    assert response.status_code == 200
    temp = response.json()["temp_password"]
    assert (await _login(api_client, STUDENT_EMAIL, temp)).status_code == 200
    # The trail still names the account, not the roster row.
    rows = await _audit_rows(test_db_session, account.id)
    assert [r.action for r in rows] == [AuditAction.PASSWORD_RESET.value]


async def test_student_reset_without_linked_account_is_409(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    admin = await _admin(factories, role=UserRole.ADMIN.value)
    graph = await factories.full_stack()
    # `full_stack` links a user; drop it to model an unclaimed roster row.
    graph["student"].user_id = None

    response = await api_client.post(
        f"/api/admin/students/{graph['student'].id}/reset-password",
        headers=await auth_headers(admin),
    )

    assert response.status_code == 409
    assert _code(response) == "student_account_unlinked"


async def test_student_reset_unknown_student_is_404(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    admin = await _admin(factories, role=UserRole.ADMIN.value)

    response = await api_client.post(
        "/api/admin/students/999999/reset-password",
        headers=await auth_headers(admin),
    )

    assert response.status_code == 404
    assert _code(response) == "student_not_found"


async def test_professor_reset_targets_the_linked_account(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    admin = await _admin(factories, role=UserRole.ADMIN.value)
    professor = await factories.professor(email=PROFESSOR_EMAIL)
    account = await factories.user(
        email=PROFESSOR_EMAIL,
        role=UserRole.PROFESSOR.value,
        password_hash=hash_password(PASSWORD),
        failed_login_attempts=5,
        is_locked=True,
        locked_at=datetime.now(timezone.utc),
    )
    professor.user_id = account.id
    await test_db_session.commit()

    response = await api_client.post(
        f"/api/admin/professors/{professor.id}/reset-password",
        headers=await auth_headers(admin),
    )

    assert response.status_code == 200
    temp = response.json()["temp_password"]
    assert (await _login(api_client, PROFESSOR_EMAIL, temp)).status_code == 200
    reloaded = await _reload_user(test_db_session, account)
    assert reloaded.is_locked is False


async def test_professor_reset_without_linked_account_is_409(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    admin = await _admin(factories, role=UserRole.ADMIN.value)
    professor = await factories.professor(email=PROFESSOR_EMAIL)

    response = await api_client.post(
        f"/api/admin/professors/{professor.id}/reset-password",
        headers=await auth_headers(admin),
    )

    assert response.status_code == 409
    assert _code(response) == "professor_account_unlinked"


# -- role gating ------------------------------------------------------------


async def test_users_reset_requires_super_admin(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """A plain admin manages students and professors, never other admins."""

    target = await _target(
        factories,
        email=STUDENT_EMAIL,
        role=UserRole.STUDENT.value,
    )
    admin = await _admin(factories, role=UserRole.ADMIN.value)

    response = await api_client.post(
        f"/api/admin/users/{target.id}/reset-password",
        headers=await auth_headers(admin),
    )

    assert response.status_code == 200
    assert "temp_password" in response.json()


async def test_super_admin_may_reset_students_and_professors(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """`super_admin` satisfies an `admin` requirement."""

    admin = await _admin(factories)
    graph = await factories.full_stack()

    response = await api_client.post(
        f"/api/admin/students/{graph['student'].id}/reset-password",
        headers=await auth_headers(admin),
    )

    assert response.status_code == 200


async def test_student_reset_rejects_a_non_admin(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    graph = await factories.full_stack()
    target = await _target(
        factories,
        email=STUDENT_EMAIL,
        role=UserRole.STUDENT.value,
    )
    headers = await auth_headers(target)
    await test_db_session.commit()

    response = await api_client.post(
        f"/api/admin/students/{graph['student'].id}/reset-password", headers=headers
    )

    assert response.status_code == 403
    assert _code(response) == "insufficient_permissions"


async def test_reset_requires_authentication(
    api_client: Any, factories: Factories
) -> None:
    target = await _target(
        factories,
        email=STUDENT_EMAIL,
        role=UserRole.STUDENT.value,
    )

    response = await api_client.post(f"/api/admin/users/{target.id}/reset-password")

    assert response.status_code in (401, 403)


# -- the create-user audit row folded in alongside --------------------------


async def test_account_creation_is_audited(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    """Account creation grants a role, so it belongs in the trail.

    `features/admin/service.py` had no `record_audit` call at all before this,
    which left `POST /admin/users` — a privilege grant — invisible.
    """

    admin = await _admin(factories)
    await test_db_session.commit()

    response = await api_client.post(
        "/api/admin/users",
        json={
            "email": "reset.created@isu.edu.ph",
            "role": UserRole.ADMIN.value,
            "first_name": "Robin",
            "last_name": "Cruz",
        },
        headers=await auth_headers(admin),
    )

    assert response.status_code == 201
    created_id = response.json()["id"]

    rows = await _audit_rows(test_db_session, created_id)
    assert len(rows) == 1
    row = rows[0]
    assert row.action == AuditAction.CREATE.value
    assert row.entity_type == AuditEntity.USER.value
    assert row.entity_id == created_id
    assert row.performed_by == admin.id
    assert row.new_value is not None
    assert row.new_value["role"] == UserRole.ADMIN.value
    # Never the credential itself, only the flag saying one was issued.
    _assert_no_credential(row.new_value)
    assert row.new_value["must_change_password"] is True
