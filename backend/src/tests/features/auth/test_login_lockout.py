"""Lockout bookkeeping commits outside the request transaction.

`_get_db` rolls its transaction back on any exception, and a wrong password
raises. The failed-attempt counter and the audit row describing it therefore
cannot be written through the request session: they would be discarded along
with the 401, and the threshold would never be reached.

These tests drive `AuthService.login` against the real database with
`database.get_session()` redirected at the same session, the pattern
`test_scheduler.py` uses for the cron adapters.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import database
from core.exceptions import DomainException
from core.security import hash_password

from shared.enums import AuditAction, AuditEntity

from features.auth.exceptions import (
    AccountLockedException,
    InvalidCredentialsException,
    PermanentAccountLockedException,
)
from features.auth.model import User
from features.auth.service import AuthService
from features.system.model import AuditLog
from tests.conftest import Factories

PASSWORD = "correct-horse-battery-staple"
WRONG = "not-the-password"
LOCKOUT_ATTEMPTS = 3
LOCKOUT_MINUTES = 15


def _settings(lockout_attempts: int = LOCKOUT_ATTEMPTS) -> Any:
    from core.config import Settings

    return Settings(
        debug=True,
        jwt_secret="test-jwt-secret-for-lockout-tests-000000000",
        lockout_attempts=lockout_attempts,
        lockout_duration_minutes=LOCKOUT_MINUTES,
    )


@pytest.fixture(autouse=True)
def use_test_session(
    monkeypatch: pytest.MonkeyPatch, test_db_session: AsyncSession
) -> None:
    """Point `database.get_session()` at the test session.

    The lockout writes commit on a session of their own; without this they
    would reach for the configured Postgres instead of the test database.
    """

    @asynccontextmanager
    async def _fake_get_session() -> AsyncIterator[AsyncSession]:
        yield test_db_session

    monkeypatch.setattr(database, "get_session", _fake_get_session)


async def _user(factories: Factories, **overrides: Any) -> User:
    # `LoginRequest.email` is an `EmailStr`, and email-validator rejects the
    # factory default's `.local` TLD as special-use. These tests go through the
    # route, so the address has to be a deliverable-looking one.
    return await factories.user(
        email=overrides.pop("email", "lockout.subject@isu.edu.ph"),
        password_hash=hash_password(PASSWORD),
        **overrides,
    )


async def _service(session: AsyncSession) -> AuthService:
    return AuthService(session, _settings())


async def _audit_rows(session: AsyncSession, user: User) -> list[AuditLog]:
    result = await session.scalars(
        select(AuditLog)
        .where(
            AuditLog.entity_type == AuditEntity.USER.value,
            AuditLog.entity_id == user.id,
        )
        .order_by(AuditLog.id)
    )
    return list(result.all())


async def _reload(session: AsyncSession, user: User) -> User:
    """Re-read the row from the database, overwriting the cached copy.

    `populate_existing` rather than `expire_all`: expiring marks the loaded
    instance dirty-looking and the next attribute read tries to lazy-load,
    which needs a greenlet that a plain attribute access does not have.
    """
    reloaded = await session.get(User, user.id, populate_existing=True)
    assert reloaded is not None
    return reloaded


# --- the counter survives the 401 -------------------------------------------


async def test_wrong_password_persists_the_counter(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    user = await _user(factories)
    await test_db_session.commit()
    service = await _service(test_db_session)

    with pytest.raises(InvalidCredentialsException):
        await service.login(user.email, WRONG)

    reloaded = await _reload(test_db_session, user)
    assert reloaded.failed_login_attempts == 1
    assert reloaded.is_locked is False


async def test_threshold_locks_the_account(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    user = await _user(factories)
    await test_db_session.commit()
    service = await _service(test_db_session)

    for _ in range(LOCKOUT_ATTEMPTS - 1):
        with pytest.raises(InvalidCredentialsException):
            await service.login(user.email, WRONG)

    with pytest.raises(InvalidCredentialsException):
        await service.login(user.email, WRONG)

    reloaded = await _reload(test_db_session, user)
    assert reloaded.failed_login_attempts == LOCKOUT_ATTEMPTS
    assert reloaded.is_locked is True
    assert reloaded.locked_at is not None


async def test_locked_account_reports_the_remaining_window(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    user = await _user(factories, is_locked=True)
    from datetime import datetime, timezone

    user.locked_at = datetime.now(timezone.utc)
    await test_db_session.commit()
    service = await _service(test_db_session)

    with pytest.raises(AccountLockedException):
        await service.login(user.email, PASSWORD)

    reloaded = await _reload(test_db_session, user)
    assert reloaded.is_locked is True


async def test_permanently_locked_account_reports_a_domain_error(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """A level past the escalation table never auto-clears.

    The permanent branch is the one lockout path with no natural expiry, so
    it is also the one an admin must be able to distinguish from a temporary
    lock. It raises the domain-level exception (423), not a bare AppException.
    """
    from datetime import datetime, timedelta, timezone

    user = await _user(factories, is_locked=True, lockout_level=99)
    user.locked_at = datetime.now(timezone.utc) - timedelta(days=365)
    await test_db_session.commit()
    service = await _service(test_db_session)

    with pytest.raises(PermanentAccountLockedException) as excinfo:
        await service.login(user.email, PASSWORD)

    assert isinstance(excinfo.value, DomainException)
    assert excinfo.value.status_code == 423
    assert excinfo.value.code == "account_permanently_locked"


async def test_expired_lock_releases_and_allows_login(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    from datetime import datetime, timedelta, timezone

    user = await _user(factories, is_locked=True)
    user.locked_at = datetime.now(timezone.utc) - timedelta(minutes=LOCKOUT_MINUTES + 1)
    user.failed_login_attempts = LOCKOUT_ATTEMPTS
    await test_db_session.commit()
    service = await _service(test_db_session)

    await service.login(user.email, PASSWORD)

    reloaded = await _reload(test_db_session, user)
    assert reloaded.is_locked is False
    assert reloaded.locked_at is None
    assert reloaded.failed_login_attempts == 0
    assert reloaded.last_login is not None


async def test_correct_password_resets_the_counter(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    user = await _user(factories, failed_login_attempts=2)
    await test_db_session.commit()
    service = await _service(test_db_session)

    await service.login(user.email, PASSWORD)

    reloaded = await _reload(test_db_session, user)
    assert reloaded.failed_login_attempts == 0
    assert reloaded.last_login is not None


# --- the audit rows ---------------------------------------------------------


async def test_failed_login_is_audited_without_an_actor(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    user = await _user(factories)
    await test_db_session.commit()
    service = await _service(test_db_session)

    with pytest.raises(InvalidCredentialsException):
        await service.login(user.email, WRONG)

    rows = await _audit_rows(test_db_session, user)
    assert len(rows) == 1
    row = rows[0]
    assert row.action == AuditAction.LOGIN_FAILED.value
    assert row.entity_type == AuditEntity.USER.value
    assert row.entity_id == user.id
    assert row.performed_by is None
    assert row.old_value["failed_login_attempts"] == 0
    assert row.new_value["failed_login_attempts"] == 1
    assert row.new_value["is_locked"] is False


async def test_threshold_writes_a_lock_row_not_a_login_failed_row(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    user = await _user(factories)
    await test_db_session.commit()
    service = await _service(test_db_session)

    for _ in range(LOCKOUT_ATTEMPTS):
        with pytest.raises(InvalidCredentialsException):
            await service.login(user.email, WRONG)

    rows = await _audit_rows(test_db_session, user)
    actions = [row.action for row in rows]
    assert actions == [
        AuditAction.LOGIN_FAILED.value,
        AuditAction.LOGIN_FAILED.value,
        AuditAction.LOCK.value,
    ]
    assert rows[-1].new_value["is_locked"] is True
    assert rows[-1].new_value["locked_at"] is not None


async def test_expired_lock_writes_an_unlock_row(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    from datetime import datetime, timedelta, timezone

    user = await _user(factories, is_locked=True)
    user.locked_at = datetime.now(timezone.utc) - timedelta(minutes=LOCKOUT_MINUTES + 1)
    await test_db_session.commit()
    service = await _service(test_db_session)

    await service.login(user.email, PASSWORD)

    rows = await _audit_rows(test_db_session, user)
    assert [row.action for row in rows] == [AuditAction.UNLOCK.value]
    assert rows[0].old_value["is_locked"] is True
    assert rows[0].new_value["is_locked"] is False


async def test_audit_snapshot_never_carries_the_email_or_the_hash(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    user = await _user(factories)
    await test_db_session.commit()
    service = await _service(test_db_session)

    with pytest.raises(InvalidCredentialsException):
        await service.login(user.email, WRONG)

    row = (await _audit_rows(test_db_session, user))[0]
    for snapshot in (row.old_value, row.new_value):
        assert set(snapshot) == {
            "failed_login_attempts",
            "is_locked",
            "locked_at",
            "lockout_level",
            "last_lockout_at",
            "lockout_override_until",
            "must_change_password",
        }
        assert user.email not in str(snapshot)
        assert user.password_hash not in str(snapshot)


# --- over HTTP, where `_get_db` rolls the request back ----------------------
#
# The service-level tests above never hit the rollback, so they would pass even
# with the counter written on the request session. These two are the ones that
# would have caught the original defect.


async def _post_login(client: Any, email: str, password: str) -> Any:
    return await client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )


def _code(response: Any) -> str:
    """The error code out of the AppException envelope."""
    return response.json()["detail"]["code"]


@pytest.fixture
def low_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop the route's lockout threshold to the service-level value.

    `AuthServiceDep` builds the service with `api.deps.settings`, not the
    `settings` fixture, so the configured default of 5 applies to the HTTP
    tests. Reaching 5 would need 5 requests against a per-email rate limit of
    5, which leaves no room for the follow-up call that proves the account is
    actually locked.
    """
    from api import deps

    monkeypatch.setattr(deps.settings, "lockout_attempts", LOCKOUT_ATTEMPTS)


async def test_counter_survives_the_400_rollback(
    api_client: Any, test_db_session: AsyncSession, factories: Factories
) -> None:
    user = await _user(factories)
    await test_db_session.commit()

    response = await _post_login(api_client, user.email, WRONG)

    assert response.status_code == 400
    assert _code(response) == "invalid_credentials"
    reloaded = await _reload(test_db_session, user)
    assert reloaded.failed_login_attempts == 1


async def test_lockout_takes_effect_over_http(
    api_client: Any,
    test_db_session: AsyncSession,
    factories: Factories,
    low_threshold: None,
) -> None:
    user = await _user(factories)
    await test_db_session.commit()

    for _ in range(LOCKOUT_ATTEMPTS - 1):
        assert (await _post_login(api_client, user.email, WRONG)).status_code == 400

    assert (await _post_login(api_client, user.email, WRONG)).status_code == 400

    reloaded = await _reload(test_db_session, user)
    assert reloaded.is_locked is True

    # The account is now locked, so even the right password is refused.
    locked = await _post_login(api_client, user.email, PASSWORD)
    assert locked.status_code == 423
    assert _code(locked) == "account_locked"


async def test_audit_row_survives_the_400_rollback(
    api_client: Any, test_db_session: AsyncSession, factories: Factories
) -> None:
    user = await _user(factories)
    await test_db_session.commit()

    await _post_login(api_client, user.email, WRONG)

    rows = await _audit_rows(test_db_session, user)
    assert [row.action for row in rows] == [AuditAction.LOGIN_FAILED.value]


# --- escalation observable across two lockouts -------------------------------


async def test_second_lockout_escalates_to_five_minutes(
    api_client: Any,
    test_db_session: AsyncSession,
    factories: Factories,
    low_threshold: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.config import get_settings

    from api import deps

    monkeypatch.setattr(deps.settings, "lockout_escalation_minutes", "1,5,15,30,60,120")
    monkeypatch.setattr(
        get_settings(), "lockout_escalation_minutes", "1,5,15,30,60,120"
    )
    monkeypatch.setattr(deps.settings, "lockout_duration_minutes", 1)
    monkeypatch.setattr(get_settings(), "lockout_duration_minutes", 1)

    user = await _user(factories, email="escalate@isu.edu.ph")
    email = user.email
    uid = user.id
    await test_db_session.commit()

    async def _post(e: str, p: str) -> Any:
        return await api_client.post(
            "/api/auth/login", json={"email": e, "password": p}
        )

    for _ in range(LOCKOUT_ATTEMPTS):
        assert (await _post(email, WRONG)).status_code == 400
    r = await _post(email, PASSWORD)
    assert r.status_code == 423
    assert "1 minute" in r.json()["detail"]["message"]

    # Expire the lock.
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from features.auth.model import User

    row = (
        await test_db_session.execute(select(User).where(User.id == uid))
    ).scalar_one()
    row.locked_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    await test_db_session.commit()

    from shared import rate_limit

    rate_limit._limiter._windows.clear()

    for _ in range(LOCKOUT_ATTEMPTS):
        assert (await _post(email, WRONG)).status_code == 400
    rate_limit._limiter._windows.clear()
    r = await _post(email, PASSWORD)
    assert r.status_code == 423
    assert "5 minutes" in r.json()["detail"]["message"]
