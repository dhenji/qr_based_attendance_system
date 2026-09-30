from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from features.admin.exceptions import RosterLinkImpossible
from features.admin.schema import AdminUserCreate
from features.admin.service import AdminService
from shared.enums import UserRole

STUDENT_EMAIL = "s@example.com"


class _FakeSession:
    """Routes the three BaseCRUD lookups create_user makes, in call order."""

    def __init__(self, *, existing_user=None, roster=None):
        self.existing_user = existing_user
        self.roster = roster
        self.added = []
        self._user_lookup = 0

    async def scalars(self, stmt):
        self._user_lookup += 1

        if self._user_lookup == 1:
            return SimpleNamespace(one_or_none=lambda: self.existing_user)

        if self._user_lookup == 2:
            return SimpleNamespace(one_or_none=lambda: self.existing_user)

        return SimpleNamespace(one_or_none=lambda: self.roster)

    async def flush(self):
        pass

    def add(self, obj):
        # BaseCRUD.create builds a real ORM instance whose server_default columns
        # are still unset (they are applied by the real DB on flush); fill them so
        # the response schema can validate. must_change_password is passed
        # explicitly by create_user, so it must not be clobbered here.
        obj.id = len(self.added) + 1
        obj.created_at = datetime.now(timezone.utc)
        obj.is_active = True
        obj.last_login = None
        self.added.append(obj)


def _payload(role: UserRole = UserRole.STUDENT) -> AdminUserCreate:
    return AdminUserCreate(
        email=STUDENT_EMAIL,
        role=role,
        first_name="Ada",
        last_name="Lovelace",
    )


def _roster(user_id=None):
    return SimpleNamespace(email=STUDENT_EMAIL, is_active=True, user_id=user_id)


def _run(session) -> None:
    asyncio.run(AdminService(session).create_user(payload=_payload()))


def test_links_to_an_unclaimed_active_roster_row() -> None:
    roster = _roster()
    session = _FakeSession(roster=roster)

    _run(session)

    assert roster.user_id == 1


def test_rejects_when_no_roster_row_exists() -> None:
    """Item 3b: fail loudly instead of minting an unlinkable account."""

    session = _FakeSession(roster=None)

    with pytest.raises(RosterLinkImpossible):
        _run(session)


def test_rejects_when_roster_row_is_already_claimed() -> None:
    session = _FakeSession(roster=_roster(user_id=99))

    with pytest.raises(RosterLinkImpossible):
        _run(session)


def test_conflict_is_a_409_with_an_actionable_message() -> None:
    error = RosterLinkImpossible("student")

    assert error.status_code == 409
    assert error.code == "roster_link_impossible"
    assert "student" in error.message
    assert "roster record first" in error.message


def test_admin_role_needs_no_roster_row() -> None:
    session = _FakeSession(roster=None)
    payload = AdminUserCreate(
        email="boss@example.com",
        role=UserRole.ADMIN,
        first_name="Grace",
        last_name="Hopper",
    )

    result = asyncio.run(AdminService(session).create_user(payload=payload))

    assert result.role is UserRole.ADMIN
    assert result.must_change_password is True
    assert result.temp_password


def test_created_user_is_forced_to_change_password() -> None:
    session = _FakeSession(roster=_roster())

    result = asyncio.run(AdminService(session).create_user(payload=_payload()))

    assert result.must_change_password is True
    assert result.is_active is True
    assert isinstance(result.created_at, datetime)
    assert result.username == "alovelace"


def test_super_admin_cannot_be_created_through_the_api() -> None:
    with pytest.raises(ValueError, match="super_admin"):
        AdminUserCreate(
            email="root@example.com",
            role=UserRole.SUPER_ADMIN,
            first_name="Root",
            last_name="Admin",
        )
