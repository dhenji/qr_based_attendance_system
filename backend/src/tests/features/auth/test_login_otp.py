"""Mandatory email-OTP second factor on login.

Password-OK no longer issues tokens directly (except for students/professors
with MFA, who keep their TOTP path): `login()` mints a LOGIN OTP and returns
an `otp_pending` grant, and `verify_login_otp()` exchanges the grant plus the
emailed code for tokens — or for an MFA challenge when the account is an
admin with MFA enabled (OTP then TOTP).

HTTP-level through `api_client`, like `test_mfa_disable.py`. The emailed code
itself is hashed and unknowable, so every test seeds a *known* LOGIN OTP row
*after* `login()` minted the real one: `verify_otp` picks the newest
unconsumed row, so the seeded code is what verifies. The seeded-code trick
mirrors `_seed_claim_otp` in `test_register_reclaim.py`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pyotp
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from core.security import (
    create_access_token,
    create_login_otp_token,
    hash_otp,
    hash_password,
)
from features.auth.constants import (
    LOGIN_OTP_IP_MAX_ATTEMPTS,
    LOGIN_OTP_MAX_ATTEMPTS,
)
from features.auth.exceptions import InvalidCredentialsException, OtpInvalidException
from features.auth.model import OtpCodes
from features.auth.service import AuthService
from shared.enums import OtpPurpose
from shared.rate_limit import RateLimitedException
from tests.conftest import Factories

PASSWORD = "correct-horse-battery-staple"
SECRET = "JBSWY3DPEB2XS2LP"
KNOWN_CODE = "123456"
WRONG_CODE = "000000"


def _email(tag: str) -> str:
    # `LoginRequest.email` is an `EmailStr`: needs a deliverable-looking
    # address, same trap as `test_login_lockout.py`.
    return f"login.otp.{tag}@isu.edu.ph"


async def _user(
    factories: Factories, tag: str, **overrides: Any
):
    defaults: dict[str, Any] = {
        "email": _email(tag),
        "password_hash": hash_password(PASSWORD),
    }
    defaults.update(overrides)
    return await factories.user(**defaults)


async def _seed_login_otp(
    session: AsyncSession,
    email: str,
    code: str = KNOWN_CODE,
    *,
    expires_at: datetime | None = None,
) -> None:
    session.add(
        OtpCodes(
            email=email.lower(),
            purpose=OtpPurpose.LOGIN.value,
            otp_hash=hash_otp(code),
            expires_at=expires_at
            or (datetime.now(timezone.utc) + timedelta(minutes=5)),
        )
    )
    await session.flush()


async def _login(api_client: Any, email: str) -> Any:
    response = await api_client.post(
        "/api/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 200
    return response.json()


async def _login_otp_rows(session: AsyncSession, email: str) -> list[OtpCodes]:
    return list(
        (
            await session.scalars(
                select(OtpCodes)
                .where(
                    OtpCodes.email == email.lower(),
                    OtpCodes.purpose == OtpPurpose.LOGIN.value,
                )
                .order_by(OtpCodes.id)
            )
        ).all()
    )


def _code(response: Any) -> str:
    return response.json()["detail"]["code"]


# --- the baseline: password-OK mints an OTP, not tokens ----------------------


async def test_login_returns_otp_grant_without_tokens(
    api_client: Any, test_db_session: AsyncSession, factories: Factories
) -> None:
    user = await _user(factories, "baseline")
    email = user.email
    await test_db_session.commit()

    body = await _login(api_client, email)

    assert body["otp_pending"] is True
    assert body["otp_token"]
    assert body.get("access_token") is None
    assert body.get("refresh_token") is None
    assert body.get("mfa_pending") is not True

    rows = await _login_otp_rows(test_db_session, email)
    assert len(rows) == 1
    assert rows[0].consumed_at is None


async def test_verify_issues_tokens_and_consumes_the_code(
    api_client: Any, test_db_session: AsyncSession, factories: Factories
) -> None:
    user = await _user(factories, "happy")
    email = user.email
    await test_db_session.commit()

    body = await _login(api_client, email)
    await _seed_login_otp(test_db_session, email)
    await test_db_session.commit()

    verified = await api_client.post(
        "/api/auth/login/verify",
        json={"otp_token": body["otp_token"], "code": KNOWN_CODE},
    )

    assert verified.status_code == 200
    assert verified.json()["access_token"]
    assert verified.json()["refresh_token"]
    assert verified.json().get("otp_pending") is not True

    # Single-use: the same code is dead on arrival the second time.
    replay = await api_client.post(
        "/api/auth/login/verify",
        json={"otp_token": body["otp_token"], "code": KNOWN_CODE},
    )
    assert replay.status_code == 400
    assert _code(replay) == "otp_invalid"


async def test_claim_otp_cannot_verify_a_login_grant(
    api_client: Any, test_db_session: AsyncSession, factories: Factories
) -> None:
    """Purpose isolation: a CLAIM code is not a LOGIN code."""

    user = await _user(factories, "purpose")
    email = user.email
    await test_db_session.commit()

    body = await _login(api_client, email)
    test_db_session.add(
        OtpCodes(
            email=email.lower(),
            purpose=OtpPurpose.CLAIM.value,
            otp_hash=hash_otp(KNOWN_CODE),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
    )
    await test_db_session.commit()

    response = await api_client.post(
        "/api/auth/login/verify",
        json={"otp_token": body["otp_token"], "code": KNOWN_CODE},
    )

    assert response.status_code == 400
    assert _code(response) == "otp_invalid"


# --- retry budget: wrong codes lock, expiry does not -------------------------


async def test_wrong_codes_lock_after_the_cap(
    api_client: Any, test_db_session: AsyncSession, factories: Factories
) -> None:
    user = await _user(factories, "cap")
    email = user.email
    await test_db_session.commit()

    body = await _login(api_client, email)

    for _ in range(LOGIN_OTP_MAX_ATTEMPTS):
        attempt = await api_client.post(
            "/api/auth/login/verify",
            json={"otp_token": body["otp_token"], "code": WRONG_CODE},
        )
        assert attempt.status_code == 400
        assert _code(attempt) == "otp_invalid"

    locked = await api_client.post(
        "/api/auth/login/verify",
        json={"otp_token": body["otp_token"], "code": WRONG_CODE},
    )
    assert locked.status_code == 423
    assert _code(locked) == "login_otp_locked"


async def test_expired_code_does_not_spend_retry_budget(
    api_client: Any, test_db_session: AsyncSession, factories: Factories
) -> None:
    user = await _user(factories, "expiry")
    email = user.email
    await test_db_session.commit()

    body = await _login(api_client, email)
    await _seed_login_otp(
        test_db_session,
        email,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    await test_db_session.commit()

    stale = await api_client.post(
        "/api/auth/login/verify",
        json={"otp_token": body["otp_token"], "code": KNOWN_CODE},
    )
    assert stale.status_code == 400
    assert _code(stale) == "otp_expired"

    # Budget is intact: two further mismatches stay 400 (cap is 3), and a
    # fresh code still verifies afterwards.
    for _ in range(LOGIN_OTP_MAX_ATTEMPTS - 1):
        attempt = await api_client.post(
            "/api/auth/login/verify",
            json={"otp_token": body["otp_token"], "code": WRONG_CODE},
        )
        assert attempt.status_code == 400

    await _seed_login_otp(test_db_session, email)
    await test_db_session.commit()

    verified = await api_client.post(
        "/api/auth/login/verify",
        json={"otp_token": body["otp_token"], "code": KNOWN_CODE},
    )
    assert verified.status_code == 200
    assert verified.json()["access_token"]


# --- resend burns the previous code ------------------------------------------


async def test_resend_burns_the_previous_code(
    api_client: Any, test_db_session: AsyncSession, factories: Factories
) -> None:
    user = await _user(factories, "resend")
    email = user.email
    await test_db_session.commit()

    body = await _login(api_client, email)
    await _seed_login_otp(test_db_session, email)
    await test_db_session.commit()

    resend = await api_client.post(
        "/api/auth/login/resend", json={"otp_token": body["otp_token"]}
    )
    assert resend.status_code == 204

    # The seeded code died with the resend even though it never verified.
    dead = await api_client.post(
        "/api/auth/login/verify",
        json={"otp_token": body["otp_token"], "code": KNOWN_CODE},
    )
    assert dead.status_code == 400
    assert _code(dead) == "otp_invalid"

    rows = await _login_otp_rows(test_db_session, email)
    assert len(rows) == 3  # minted + seeded + resend
    assert rows[0].consumed_at is not None
    assert rows[1].consumed_at is not None
    assert rows[2].consumed_at is None


async def test_resend_needs_the_grant(
    api_client: Any, test_db_session: AsyncSession, factories: Factories
) -> None:
    user = await _user(factories, "resend-gate")
    email = user.email
    await test_db_session.commit()

    await _login(api_client, email)

    response = await api_client.post(
        "/api/auth/login/resend", json={"otp_token": "not-a-grant"}
    )

    assert response.status_code == 400
    assert _code(response) == "invalid_credentials"


# --- MFA interaction: replace for students/profs, chain for admins -----------


async def test_student_with_mfa_keeps_totp_path_and_no_email(
    api_client: Any, test_db_session: AsyncSession, factories: Factories
) -> None:
    user = await _user(
        factories, "mfa-student", mfa_enabled=True, mfa_secret=SECRET
    )
    email = user.email
    await test_db_session.commit()

    body = await _login(api_client, email)

    assert body["mfa_pending"] is True
    assert body["preauth_token"]
    assert body.get("otp_pending") is not True

    count = await test_db_session.scalar(
        select(func.count())
        .select_from(OtpCodes)
        .where(
            OtpCodes.email == email.lower(),
            OtpCodes.purpose == OtpPurpose.LOGIN.value,
        )
    )
    assert count == 0


async def test_admin_with_mfa_chains_otp_then_totp(
    api_client: Any, test_db_session: AsyncSession, factories: Factories
) -> None:
    user = await _user(
        factories,
        "mfa-admin",
        role="admin",
        mfa_enabled=True,
        mfa_secret=SECRET,
    )
    email = user.email
    await test_db_session.commit()

    body = await _login(api_client, email)
    assert body["otp_pending"] is True

    await _seed_login_otp(test_db_session, email)
    await test_db_session.commit()

    challenged = await api_client.post(
        "/api/auth/login/verify",
        json={"otp_token": body["otp_token"], "code": KNOWN_CODE},
    )

    assert challenged.status_code == 200
    assert challenged.json()["mfa_pending"] is True
    assert challenged.json()["preauth_token"]
    assert challenged.json().get("access_token") is None

    unlocked = await api_client.post(
        "/api/auth/mfa/verify",
        json={
            "code": pyotp.TOTP(SECRET).now(),
            "preauth_token": challenged.json()["preauth_token"],
        },
    )

    assert unlocked.status_code == 200
    assert unlocked.json()["access_token"]


# --- grants fail closed and non-probeably ------------------------------------


async def test_wrong_typed_grant_is_invalid_credentials(
    api_client: Any,
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Any,
) -> None:
    user = await _user(factories, "grant-type")
    email = user.email
    await test_db_session.commit()

    await _login(api_client, email)

    # A well-signed access token in the grant slot: rejected on `type`, not
    # on signature, and reported generically either way.
    response = await api_client.post(
        "/api/auth/login/verify",
        json={
            "otp_token": create_access_token(user.id, user.role, settings),
            "code": KNOWN_CODE,
        },
    )

    assert response.status_code == 400
    assert _code(response) == "invalid_credentials"


async def test_grant_for_another_email_is_invalid_credentials(
    test_db_session: AsyncSession, factories: Factories, settings: Any
) -> None:
    user = await _user(factories, "grant-email")
    email = user.email
    await test_db_session.commit()

    forged = create_login_otp_token(user.id, "someone.else@isu.edu.ph", settings)
    service = AuthService(test_db_session, settings)

    with pytest.raises(InvalidCredentialsException):
        await service.verify_login_otp(forged, KNOWN_CODE)


async def test_expired_grant_is_invalid_credentials(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    user = await _user(factories, "grant-expiry")
    email = user.email
    await test_db_session.commit()

    expired_settings = Settings(
        debug=True,
        jwt_secret="test-jwt-secret-for-otp-tests-0000000000",
        preauth_token_expire_minutes=-1,
    )
    stale = create_login_otp_token(user.id, user.email, expired_settings)
    service = AuthService(test_db_session, expired_settings)

    with pytest.raises(InvalidCredentialsException):
        await service.verify_login_otp(stale, KNOWN_CODE)


# --- the lock is per email, but the IP gate follows the device --------------


async def test_locked_email_does_not_block_another_email(
    api_client: Any, test_db_session: AsyncSession, factories: Factories
) -> None:
    """The reported scenario: email A locked, email B must still verify.

    The email-keyed cap (`login_otp|<email>`) resets per account; the IP
    budgets (5 email failures here, far below the 15-cap) stay green, so B's
    correct code issues tokens.
    """

    locked_user = await _user(factories, "locked-a")
    locked_email = locked_user.email
    fresh_user = await _user(factories, "fresh-b")
    fresh_email = fresh_user.email
    await test_db_session.commit()

    locked_body = await _login(api_client, locked_email)

    for _ in range(LOGIN_OTP_MAX_ATTEMPTS):
        await api_client.post(
            "/api/auth/login/verify",
            json={"otp_token": locked_body["otp_token"], "code": WRONG_CODE},
        )

    locked = await api_client.post(
        "/api/auth/login/verify",
        json={"otp_token": locked_body["otp_token"], "code": WRONG_CODE},
    )
    assert locked.status_code == 423
    assert _code(locked) == "login_otp_locked"

    fresh_body = await _login(api_client, fresh_email)
    await _seed_login_otp(test_db_session, fresh_email)
    await test_db_session.commit()

    verified = await api_client.post(
        "/api/auth/login/verify",
        json={"otp_token": fresh_body["otp_token"], "code": KNOWN_CODE},
    )
    assert verified.status_code == 200
    assert verified.json()["access_token"]


async def test_resend_resets_the_email_budget_but_not_the_ip_budget(
    api_client: Any, test_db_session: AsyncSession, factories: Factories
) -> None:
    """A resend mints a fresh code, so guesses against the burned one stop
    counting — but a resend loop still burns the IP budget underneath."""

    user = await _user(factories, "resend-reset")
    email = user.email
    await test_db_session.commit()

    body = await _login(api_client, email)

    # Two misses against the first code...
    for _ in range(LOGIN_OTP_MAX_ATTEMPTS - 1):
        attempt = await api_client.post(
            "/api/auth/login/verify",
            json={"otp_token": body["otp_token"], "code": WRONG_CODE},
        )
        assert attempt.status_code == 400

    # ...then a resend, which restarts the email budget from zero.
    resend = await api_client.post(
        "/api/auth/login/resend", json={"otp_token": body["otp_token"]}
    )
    assert resend.status_code == 204

    # A full fresh budget: three more misses before the lock bites.
    for _ in range(LOGIN_OTP_MAX_ATTEMPTS):
        attempt = await api_client.post(
            "/api/auth/login/verify",
            json={"otp_token": body["otp_token"], "code": WRONG_CODE},
        )
        assert attempt.status_code == 400
        assert _code(attempt) == "otp_invalid"

    locked = await api_client.post(
        "/api/auth/login/verify",
        json={"otp_token": body["otp_token"], "code": WRONG_CODE},
    )
    assert locked.status_code == 423
    assert _code(locked) == "login_otp_locked"


async def test_resend_unlocks_a_locked_email(
    api_client: Any, test_db_session: AsyncSession, factories: Factories
) -> None:
    """The direct fix for the report: locked out, resend, verify the fresh
    code — no waiting out the window."""

    user = await _user(factories, "resend-unlock")
    email = user.email
    await test_db_session.commit()

    body = await _login(api_client, email)

    for _ in range(LOGIN_OTP_MAX_ATTEMPTS + 1):
        await api_client.post(
            "/api/auth/login/verify",
            json={"otp_token": body["otp_token"], "code": WRONG_CODE},
        )

    resend = await api_client.post(
        "/api/auth/login/resend", json={"otp_token": body["otp_token"]}
    )
    assert resend.status_code == 204

    await _seed_login_otp(test_db_session, email)
    await test_db_session.commit()

    verified = await api_client.post(
        "/api/auth/login/verify",
        json={"otp_token": body["otp_token"], "code": KNOWN_CODE},
    )
    assert verified.status_code == 200
    assert verified.json()["access_token"]


async def test_ip_failure_cap_survives_email_rotation(
    test_db_session: AsyncSession, factories: Factories, settings: Any
) -> None:
    """Guessing across many accounts from one device still trips the IP cap.

    Service-level (no router flood gate involved): 16 distinct accounts, one
    miss each from the same client IP — every email stays under its own cap
    of 3, but the shared IP bucket exhausts at 15 and the 16th raises 429.
    """

    service = AuthService(test_db_session, settings)
    grants: list[str] = []

    for n in range(LOGIN_OTP_IP_MAX_ATTEMPTS + 1):
        user = await _user(factories, f"rot-{n:02d}")
        pending = await service.login(user.email, PASSWORD)
        assert pending.otp_token is not None
        grants.append(pending.otp_token)
    await test_db_session.commit()

    for grant in grants[:-1]:
        with pytest.raises(OtpInvalidException):
            await service.verify_login_otp(grant, WRONG_CODE, client_ip="9.9.9.9")

    with pytest.raises(RateLimitedException):
        await service.verify_login_otp(grants[-1], WRONG_CODE, client_ip="9.9.9.9")
