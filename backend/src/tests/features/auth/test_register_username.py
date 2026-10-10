"""Fresh-path `username` uniqueness on `register()`.

The reclaim path already raised `409 username_exists` for a taken handle;
the fresh-create path used to rely on the DB unique constraint, surfacing a
generic 409 instead. Both now raise `UsernameTakenException`, so a claimant
gets the same actionable code either way.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.security import hash_otp, hash_password
from features.auth.exceptions import UsernameTakenException
from features.auth.model import OtpCodes, User
from features.auth.service import AuthService
from features.student.service import StudentService
from shared.enums import OtpPurpose, UserRole
from tests.conftest import Factories

OTP = "123456"
PASSWORD = "New-holder-pass-2"
OLD_PASSWORD = "old-holder-pass-1"


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


async def test_register_fresh_path_with_taken_username_is_409(
    test_db_session: AsyncSession, settings: Any, factories: Factories
) -> None:
    """A handle held by any other account blocks a fresh claim too."""

    await factories.user(username="takenname")
    program = await factories.program()
    year = await factories.year_level(program)
    email = "fresh.holder@isu.edu.ph"
    await factories.student(year, user=None, email=email)
    await _seed_claim_otp(test_db_session, email)

    with pytest.raises(UsernameTakenException):
        await AuthService(test_db_session, settings).register(
            email=email,
            otp_code=OTP,
            username="takenname",
            password=PASSWORD,
            security_question="Pet?",
            security_answer="Cat",
        )


async def test_register_fresh_path_stores_normalized_handle(
    test_db_session: AsyncSession, settings: Any, factories: Factories
) -> None:
    """The service persists the handle it is given; schemas normalize first.

    HTTP callers go through `RegisterRequest`, which lowercases/strips, so by
    the time this runs the value is canonical — assert the stored row matches.
    """

    program = await factories.program()
    year = await factories.year_level(program)
    email = "second.holder@isu.edu.ph"
    await factories.student(year, user=None, email=email)
    await _seed_claim_otp(test_db_session, email)

    tokens = await AuthService(test_db_session, settings).register(
        email=email,
        otp_code=OTP,
        username="second.holder",
        password=PASSWORD,
        security_question="Pet?",
        security_answer="Cat",
    )

    assert tokens.access_token is not None
    user = await test_db_session.scalar(select(User).where(User.email == email))
    assert user is not None
    assert user.username == "second.holder"


async def test_register_reclaim_with_same_username_succeeds(
    test_db_session: AsyncSession, settings: Any, factories: Factories
) -> None:
    """Delete -> re-add -> re-register with the same handle revives the login.

    The orphaned `users` row still holds the username, but it is the same
    row the reclaim revives — not a rival claim — so the fresh-path
    uniqueness check must exempt it.
    """

    email = "same.handle@isu.edu.ph"
    program = await factories.program()
    year = await factories.year_level(program)
    user = await factories.user(
        email=email,
        username="same.handle",
        password_hash=hash_password(OLD_PASSWORD),
    )
    student = await factories.student(year, user=user, email=email)
    service = StudentService(test_db_session)
    await service.archive(student_id=student.id, actor_id=user.id)
    await service.hard_delete(student_id=student.id, actor_id=user.id)

    # Roster re-created with the same email, then claimed with the same handle.
    fresh = await factories.student(year, user=None, email=email)
    await _seed_claim_otp(test_db_session, email)

    tokens = await AuthService(test_db_session, settings).register(
        email=email,
        otp_code=OTP,
        username="same.handle",
        password=PASSWORD,
        security_question="Pet?",
        security_answer="Cat",
    )

    assert tokens.access_token is not None
    await test_db_session.refresh(fresh)
    assert fresh.user_id == user.id


async def test_roster_create_ignores_stray_username_key(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """Old clients still sending `username` on roster add get 201, minus it.

    Pydantic's default `extra="ignore"` drops the unknown key, so the
    removal needs no versioned contract — the response simply carries no
    username field because `StudentRead` never had one.
    """

    admin = await factories.user(
        email="roster.admin@isu.edu.ph",
        username="roster.admin",
        role=UserRole.ADMIN.value,
        is_active=True,
    )
    program = await factories.program()
    year = await factories.year_level(program)

    response = await api_client.post(
        "/api/admin/students",
        headers=await auth_headers(admin),
        json={
            "student_id": "2024-00099",
            "first_name": "Jose",
            "last_name": "Rizal",
            "email": "jose.rizal@isu.edu.ph",
            "program_id": program.id,
            "year_level_id": year.id,
            "username": "stray.handle",
        },
    )

    assert response.status_code == 201
    assert "username" not in response.json()
