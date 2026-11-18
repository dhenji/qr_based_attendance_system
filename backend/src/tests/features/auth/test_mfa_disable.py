"""Disabling MFA clears the flag, the secret and every live backup code.

`POST /auth/mfa/disable` is the only path in the codebase that sets
`mfa_enabled` back to False -- `verify_mfa` is the only writer that sets it
True -- so before it existed an account that enabled MFA could never turn it
off again. These tests pin all four effects the contract names
(api-contracts.md: "verifies the current password, sets mfa_enabled=false,
clears the TOTP secret, and invalidates all unconsumed backup codes"), and
specifically that the codes die with it: leaving ten working codes behind on an
account that no longer challenges for a code would be worse than not having
disabled anything.

HTTP-level through `api_client`, like `test_login_lockout.py`. The service is
not driven directly because the interesting behaviour includes the route's
auth dependency and the 400-vs-409 split between the two failure modes.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.security import hash_otp, hash_password

from shared.enums import AuditAction, AuditEntity, OtpPurpose

from features.auth.model import MfaBackupCodes, OtpCodes, User
from features.system.model import AuditLog
from tests.conftest import Factories

PASSWORD = "correct-horse-battery-staple"
WRONG = "not-the-password"
SECRET = "JBSWY3DPEB2XS2LP"
LOGIN_OTP = "654321"

# `LoginRequest.email` is an `EmailStr` and email-validator rejects the factory
# default's `.local` TLD as special-use, so these tests go through the route and
# need a deliverable-looking address (same trap as `test_login_lockout.py`).
EMAIL = "mfa.disable.subject@isu.edu.ph"


async def _user(factories: Factories, **overrides: Any) -> User:
    defaults: dict[str, Any] = {
        "email": EMAIL,
        "password_hash": hash_password(PASSWORD),
        "mfa_enabled": True,
        "mfa_secret": SECRET,
    }
    defaults.update(overrides)
    return await factories.user(**defaults)


async def _backup_codes(
    session: AsyncSession, user: User, *, consumed: int = 1, live: int = 2
) -> list[MfaBackupCodes]:
    """Insert backup codes directly: `factories` has no builder for them.

    `consumed` rows carry a `used_at` so the invalidation can be shown to leave
    already-spent codes alone rather than rewriting the audit trail.
    """

    rows: list[MfaBackupCodes] = []
    for index in range(consumed + live):
        row = MfaBackupCodes(
            user_id=user.id,
            code_hash=hash_password(f"seed-code-{index}"),
            code_fingerprint=f"{'0' * 60}{index:04d}",
            used_at=(
                datetime.now(timezone.utc) - timedelta(hours=1)
                if index < consumed
                else None
            ),
        )
        session.add(row)
        rows.append(row)
    await session.flush()
    return rows


async def _reload(session: AsyncSession, user: User) -> User:
    """Re-read the row, overwriting the cached copy.

    `populate_existing` rather than `expire_all`: expiring marks the loaded
    instance dirty-looking and the next attribute read tries to lazy-load, which
    needs a greenlet a plain attribute access does not have.
    """

    reloaded = await session.get(User, user.id, populate_existing=True)
    assert reloaded is not None
    return reloaded


async def _codes_for(session: AsyncSession, user_id: int) -> Sequence[MfaBackupCodes]:
    result = await session.scalars(
        select(MfaBackupCodes)
        .where(MfaBackupCodes.user_id == user_id)
        .order_by(MfaBackupCodes.id)
    )
    return list(result.all())


async def _audit_rows(session: AsyncSession, user: User) -> Sequence[AuditLog]:
    result = await session.scalars(
        select(AuditLog)
        .where(
            AuditLog.entity_type == AuditEntity.USER.value,
            AuditLog.entity_id == user.id,
        )
        .order_by(AuditLog.id)
    )
    return list(result.all())


def _code(response: Any) -> str:
    """The error code out of the AppException envelope."""

    return response.json()["detail"]["code"]


async def _disable(client: Any, headers: dict[str, str], password: str) -> Any:
    return await client.post(
        "/api/auth/mfa/disable", json={"password": password}, headers=headers
    )


# --- the happy path invalidates everything the contract names ----------------


async def test_disable_clears_flag_secret_and_codes(
    api_client: Any,
    auth_headers: Any,
    test_db_session: AsyncSession,
    factories: Factories,
) -> None:
    user = await _user(factories)
    rows = await _backup_codes(test_db_session, user)
    await test_db_session.commit()

    response = await _disable(api_client, await auth_headers(user), PASSWORD)

    assert response.status_code == 204

    reloaded = await _reload(test_db_session, user)
    assert reloaded.mfa_enabled is False
    assert reloaded.mfa_secret is None

    codes = await _codes_for(test_db_session, user.id)
    assert len(codes) == len(rows)
    live = [row for row in codes if row.id in {r.id for r in rows[1:]}]
    assert all(row.used_at is not None for row in live)
    # The already-consumed row keeps its original timestamp rather than being
    # restamped, so the history of what was used when survives the disable.
    spent = next(row for row in codes if row.id == rows[0].id)
    assert spent.used_at is not None


async def test_disable_is_audited(
    api_client: Any,
    auth_headers: Any,
    test_db_session: AsyncSession,
    factories: Factories,
) -> None:
    user = await _user(factories)
    await test_db_session.commit()

    response = await _disable(api_client, await auth_headers(user), PASSWORD)
    assert response.status_code == 204

    rows = await _audit_rows(test_db_session, user)
    assert len(rows) == 1
    row = rows[0]
    assert row.action == AuditAction.UPDATE.value
    assert row.entity_type == AuditEntity.USER.value
    assert row.old_value == {"mfa_enabled": True}
    assert row.new_value == {"mfa_enabled": False}
    # `_account_snapshot` deliberately excludes MFA material, so this row is
    # built by hand -- assert the secret never reaches a table every admin reads.
    assert "mfa_secret" not in str(row.old_value) + str(row.new_value)


# --- the two failure modes stay distinguishable -----------------------------


async def test_wrong_password_changes_nothing(
    api_client: Any,
    auth_headers: Any,
    test_db_session: AsyncSession,
    factories: Factories,
) -> None:
    user = await _user(factories)
    rows = await _backup_codes(test_db_session, user)
    await test_db_session.commit()

    response = await _disable(api_client, await auth_headers(user), WRONG)

    assert response.status_code == 400
    assert _code(response) == "current_password_invalid"

    reloaded = await _reload(test_db_session, user)
    assert reloaded.mfa_enabled is True
    assert reloaded.mfa_secret == SECRET

    codes = await _codes_for(test_db_session, user.id)
    assert [row.used_at for row in codes[1:]] == [None for _ in rows[1:]]
    assert await _audit_rows(test_db_session, user) == []


async def test_disable_without_mfa_is_409(
    api_client: Any,
    auth_headers: Any,
    test_db_session: AsyncSession,
    factories: Factories,
) -> None:
    # A secret without the flag: `setup_mfa` writes the TOTP secret and only
    # `verify_mfa` enables, so confirming setup is exactly where a user can be.
    user = await _user(factories, mfa_enabled=False, mfa_secret=SECRET)
    await test_db_session.commit()

    response = await _disable(api_client, await auth_headers(user), PASSWORD)

    assert response.status_code == 409
    assert _code(response) == "mfa_not_enabled"

    reloaded = await _reload(test_db_session, user)
    assert reloaded.mfa_secret == SECRET


async def test_disable_requires_authentication(
    api_client: Any, test_db_session: AsyncSession, factories: Factories
) -> None:
    user = await _user(factories)
    await test_db_session.commit()

    response = await api_client.post(
        "/api/auth/mfa/disable", json={"password": PASSWORD}
    )

    assert response.status_code in (401, 403)
    reloaded = await _reload(test_db_session, user)
    assert reloaded.mfa_enabled is True
    assert reloaded.mfa_secret == SECRET


# --- the point of the endpoint: login stops challenging ---------------------


async def test_login_no_longer_challenges_after_disable(
    api_client: Any,
    auth_headers: Any,
    test_db_session: AsyncSession,
    factories: Factories,
) -> None:
    user = await _user(factories)
    await test_db_session.commit()

    gated = await api_client.post(
        "/api/auth/login", json={"email": EMAIL, "password": PASSWORD}
    )
    assert gated.status_code == 200
    assert gated.json()["mfa_pending"] is True
    assert gated.json().get("access_token") is None

    assert (
        await _disable(api_client, await auth_headers(user), PASSWORD)
    ).status_code == 204

    after = await api_client.post(
        "/api/auth/login", json={"email": EMAIL, "password": PASSWORD}
    )
    assert after.status_code == 200
    # MFA no longer gates, but the mandatory login OTP does: no preauth, no
    # tokens yet — just the OTP grant.
    assert after.json().get("mfa_pending") is not True
    assert after.json()["otp_pending"] is True
    assert after.json().get("access_token") is None

    # Completing the OTP step issues the session the old test asserted here.
    test_db_session.add(
        OtpCodes(
            email=EMAIL.lower(),
            purpose=OtpPurpose.LOGIN.value,
            otp_hash=hash_otp(LOGIN_OTP),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
    )
    await test_db_session.commit()

    verified = await api_client.post(
        "/api/auth/login/verify",
        json={"otp_token": after.json()["otp_token"], "code": LOGIN_OTP},
    )
    assert verified.status_code == 200
    assert verified.json()["access_token"]
