"""Regression cover for `StudentService.change_password`'s User load.

The service used to read `student.user` straight off the row returned by
`get_by(user_id=...)`, which issues `select(Student)` with no loader
options. `Student.user` declares no `lazy=`, so in async that is an
implicit lazy load and raises `MissingGreenlet` (coding-standards §1.6).
The User is now loaded with an explicit `session.get`.

The fakes here never touch a real database, so `MissingGreenlet` cannot be
raised directly. Instead `_ExplodingStudent.user` fails the test if it is
read at all: any return to the relationship path is a hard error rather
than a silent pass.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import pytest

from core.security import hash_password, verify_password
from features.student.exceptions import (
    CurrentPasswordInvalidException,
    StudentNotFoundException,
)
from features.student.model import Student
from features.student.service import StudentService

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)

CURRENT_PASSWORD = "correct-horse"
NEW_PASSWORD = "battery-staple"


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


class _ExplodingStudent(Student):
    """A Student whose `user` relationship explodes on access.

    Inheriting from the real model keeps `_students.get_by()` happy (it
    matches on the entity in the statement) while making the relationship
    unreadable, so the test proves the code path never depends on it.
    """

    @property
    def user(self) -> Any:
        raise AssertionError(
            "student.user was read; the User must be loaded with an "
            "explicit session.get (coding-standards §1.6)"
        )


class _FakeUser:
    def __init__(self, user_id: int, password: str, must_change: bool) -> None:
        self.id = user_id
        self.email = "student@example.com"
        self.password_hash = hash_password(password)
        self.must_change_password = must_change


class _FakeResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def one_or_none(self) -> Any:
        assert len(self._rows) <= 1
        return self._rows[0] if self._rows else None


class _FakeSession:
    """Serves the Student lookup and records every explicit `get` call.

    `scalars()` answers `BaseCRUD.get_by`; `get()` answers the explicit
    User load and is the assertion point for the fix.
    """

    def __init__(self, *, student: Any = None, user: Any = None) -> None:
        self.student = student
        self.user = user
        self.get_calls: list[tuple[Any, Any]] = []

    async def scalars(self, stmt: Any) -> _FakeResult:
        return _FakeResult([self.student] if self.student is not None else [])

    async def get(self, model: Any, ident: Any) -> Any:
        self.get_calls.append((model, ident))
        return self.user

    async def flush(self) -> None:
        pass

    def add(self, obj: Any) -> None:
        pass


def _student() -> _ExplodingStudent:
    return _ExplodingStudent(
        id=5,
        user_id=42,
        student_id="24-0001",
        email="student@example.com",
        first_name="Jose",
        middle_name=None,
        last_name="Rizal",
        year_level_id=301,
        section="A",
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
    )


def test_loads_user_explicitly_instead_of_the_relationship() -> None:
    """The fix: the User arrives via session.get, not student.user."""
    from features.auth.model import User

    fake = _FakeSession(
        student=_student(), user=_FakeUser(42, CURRENT_PASSWORD, must_change=True)
    )
    service = StudentService(fake)

    _run(service.change_password(42, CURRENT_PASSWORD, NEW_PASSWORD))

    assert fake.get_calls == [(User, 42)]


def test_reading_the_relationship_would_fail_the_test() -> None:
    """Guards the guard: prove _ExplodingStudent.user is really poisoned.

    Without this, a refactor that quietly removed the exploding property
    would let the test above pass for the wrong reason.
    """
    with pytest.raises(AssertionError, match="student.user was read"):
        _ = _student().user


def test_updates_hash_and_clears_must_change_password() -> None:
    user = _FakeUser(42, CURRENT_PASSWORD, must_change=True)
    original_hash = user.password_hash
    service = StudentService(_FakeSession(student=_student(), user=user))

    _run(service.change_password(42, CURRENT_PASSWORD, NEW_PASSWORD))

    assert user.password_hash != original_hash
    assert verify_password(NEW_PASSWORD, user.password_hash)
    assert not verify_password(CURRENT_PASSWORD, user.password_hash)
    assert user.must_change_password is False


def test_wrong_current_password_leaves_hash_untouched() -> None:
    user = _FakeUser(42, CURRENT_PASSWORD, must_change=True)
    original_hash = user.password_hash
    service = StudentService(_FakeSession(student=_student(), user=user))

    with pytest.raises(CurrentPasswordInvalidException):
        _run(service.change_password(42, "not-the-password", NEW_PASSWORD))

    assert user.password_hash == original_hash
    assert user.must_change_password is True


def test_unknown_student_raises_404() -> None:
    service = StudentService(_FakeSession(student=None, user=None))

    with pytest.raises(StudentNotFoundException):
        _run(service.change_password(42, CURRENT_PASSWORD, NEW_PASSWORD))


def test_missing_linked_user_raises_404() -> None:
    """A student row with no matching User must not fall through."""
    service = StudentService(_FakeSession(student=_student(), user=None))

    with pytest.raises(StudentNotFoundException):
        _run(service.change_password(42, CURRENT_PASSWORD, NEW_PASSWORD))


def test_reused_new_password_is_rejected() -> None:
    from features.student.exceptions import PasswordReusedException

    user = _FakeUser(42, CURRENT_PASSWORD, must_change=True)
    original_hash = user.password_hash
    service = StudentService(_FakeSession(student=_student(), user=user))

    with pytest.raises(PasswordReusedException):
        _run(service.change_password(42, CURRENT_PASSWORD, CURRENT_PASSWORD))

    assert user.password_hash == original_hash
    assert user.must_change_password is True
