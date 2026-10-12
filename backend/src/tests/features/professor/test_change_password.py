"""Regression cover for `ProfessorService.change_password`'s User load.

Mirrors `tests/features/student/test_change_password.py`: the User must be
loaded with an explicit `session.get`, never via a lazy relationship read
(coding-standards §1.6). `_ExplodingProfessor.user` fails the test if it is
read at all.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import pytest

from core.security import hash_password, verify_password
from features.professor.exceptions import (
    CurrentPasswordInvalidException,
    ProfessorNotFoundException,
)
from features.professor.model import Professor
from features.professor.service import ProfessorService

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)

CURRENT_PASSWORD = "CurrentPass1!"
NEW_PASSWORD = "BrandNewPass2!"


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


class _ExplodingProfessor(Professor):
    """A Professor whose `user` relationship explodes on access."""

    @property
    def user(self) -> Any:
        raise AssertionError(
            "professor.user was read; the User must be loaded with an "
            "explicit session.get (coding-standards §1.6)"
        )


class _FakeUser:
    def __init__(self, user_id: int, password: str, must_change: bool) -> None:
        self.id = user_id
        self.email = "prof@example.com"
        self.password_hash = hash_password(password)
        self.must_change_password = must_change


class _FakeResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def one_or_none(self) -> Any:
        assert len(self._rows) <= 1
        return self._rows[0] if self._rows else None


class _FakeSession:
    """Serves the Professor lookup and records every explicit `get` call."""

    def __init__(self, *, professor: Any = None, user: Any = None) -> None:
        self.professor = professor
        self.user = user
        self.get_calls: list[tuple[Any, Any]] = []

    async def scalars(self, stmt: Any) -> _FakeResult:
        return _FakeResult([self.professor] if self.professor is not None else [])

    async def get(self, model: Any, ident: Any) -> Any:
        self.get_calls.append((model, ident))
        return self.user

    async def flush(self) -> None:
        pass

    def add(self, obj: Any) -> None:
        pass


def _professor() -> _ExplodingProfessor:
    return _ExplodingProfessor(
        id=7,
        user_id=42,
        email="prof@example.com",
        first_name="Ada",
        middle_name=None,
        last_name="Lovelace",
        department="CS",
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
    )


def test_loads_user_explicitly_instead_of_the_relationship() -> None:
    from features.auth.model import User

    fake = _FakeSession(
        professor=_professor(), user=_FakeUser(42, CURRENT_PASSWORD, must_change=True)
    )
    service = ProfessorService(fake)

    _run(
        service.change_password(
            user_id=42,
            current_password=CURRENT_PASSWORD,
            new_password=NEW_PASSWORD,
        )
    )

    assert fake.get_calls == [(User, 42)]


def test_reading_the_relationship_would_fail_the_test() -> None:
    with pytest.raises(AssertionError, match="professor.user was read"):
        _ = _professor().user


def test_updates_hash_and_clears_must_change_password() -> None:
    user = _FakeUser(42, CURRENT_PASSWORD, must_change=True)
    original_hash = user.password_hash
    service = ProfessorService(_FakeSession(professor=_professor(), user=user))

    _run(
        service.change_password(
            user_id=42,
            current_password=CURRENT_PASSWORD,
            new_password=NEW_PASSWORD,
        )
    )

    assert user.password_hash != original_hash
    assert verify_password(NEW_PASSWORD, user.password_hash)
    assert not verify_password(CURRENT_PASSWORD, user.password_hash)
    assert user.must_change_password is False


def test_wrong_current_password_leaves_hash_untouched() -> None:
    user = _FakeUser(42, CURRENT_PASSWORD, must_change=True)
    original_hash = user.password_hash
    service = ProfessorService(_FakeSession(professor=_professor(), user=user))

    with pytest.raises(CurrentPasswordInvalidException):
        _run(
            service.change_password(
                user_id=42,
                current_password="WrongPass1!",
                new_password=NEW_PASSWORD,
            )
        )

    assert user.password_hash == original_hash
    assert user.must_change_password is True


def test_unknown_professor_raises_404() -> None:
    service = ProfessorService(_FakeSession(professor=None, user=None))

    with pytest.raises(ProfessorNotFoundException):
        _run(
            service.change_password(
                user_id=42,
                current_password=CURRENT_PASSWORD,
                new_password=NEW_PASSWORD,
            )
        )


def test_missing_linked_user_raises_404() -> None:
    service = ProfessorService(_FakeSession(professor=_professor(), user=None))

    with pytest.raises(ProfessorNotFoundException):
        _run(
            service.change_password(
                user_id=42,
                current_password=CURRENT_PASSWORD,
                new_password=NEW_PASSWORD,
            )
        )


def test_reused_new_password_is_rejected() -> None:
    from features.professor.exceptions import PasswordReusedException

    user = _FakeUser(42, CURRENT_PASSWORD, must_change=True)
    original_hash = user.password_hash
    service = ProfessorService(_FakeSession(professor=_professor(), user=user))

    with pytest.raises(PasswordReusedException):
        _run(
            service.change_password(
                user_id=42,
                current_password=CURRENT_PASSWORD,
                new_password=CURRENT_PASSWORD,
            )
        )

    assert user.password_hash == original_hash
    assert user.must_change_password is True
