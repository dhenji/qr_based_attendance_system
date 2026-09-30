from __future__ import annotations

import secrets
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.security import hash_password
from features.admin.constants import DEFAULT_USERNAME_MAX_LENGTH, TEMP_PASSWORD_LENGTH
from features.admin.exceptions import (
    AdminUserNotFound,
    EmailAlreadyExists,
    RosterLinkImpossible,
    SelfDeactivationForbidden,
    UsernameAlreadyExists,
)
from features.admin.schema import (
    AdminUserCreate,
    AdminUserCreateResponse,
    AdminUserRead,
)
from features.auth.model import User
from features.professor.model import Professor
from features.student.model import Student
from shared.base import BaseCRUD
from shared.enums import UserRole
from shared.pagination import PaginatedResponse


class AdminService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users: BaseCRUD[User] = BaseCRUD(User, session)
        self._students: BaseCRUD[Student] = BaseCRUD(Student, session)
        self._professors: BaseCRUD[Professor] = BaseCRUD(Professor, session)

    async def create_user(self, *, payload: AdminUserCreate) -> AdminUserCreateResponse:
        normalized: str = payload.email.lower()

        if await self._users.get_by(email=normalized) is not None:
            raise EmailAlreadyExists()

        username: str = payload.username or self._default_username(
            payload.first_name, payload.last_name
        )

        if await self._users.get_by(username=username) is not None:
            raise UsernameAlreadyExists()

        temp_password: str = secrets.token_urlsafe(TEMP_PASSWORD_LENGTH)

        user: User = await self._users.create(
            username=username,
            email=normalized,
            password_hash=hash_password(temp_password),
            role=payload.role.value,
            must_change_password=True,
        )

        if payload.role is UserRole.STUDENT:
            await self._link_roster(
                self._students, email=normalized, user_id=user.id, role="student"
            )
        elif payload.role is UserRole.PROFESSOR:
            await self._link_roster(
                self._professors, email=normalized, user_id=user.id, role="professor"
            )

        return AdminUserCreateResponse(
            id=user.id,
            email=user.email,
            username=username,
            role=UserRole(user.role),
            first_name=payload.first_name,
            last_name=payload.last_name,
            is_active=user.is_active,
            must_change_password=user.must_change_password,
            last_login=user.last_login,
            created_at=user.created_at,
            temp_password=temp_password,
        )

    async def list_users(
        self,
        *,
        search: str | None,
        role: UserRole | None,
        is_active: bool | None,
        page: int,
        size: int,
    ) -> PaginatedResponse[AdminUserRead]:
        stmt: Select[Any] = (
            select(
                User,
                Student.first_name,
                Student.last_name,
                Professor.first_name,
                Professor.last_name,
            )
            .outerjoin(Student, Student.user_id == User.id)
            .outerjoin(Professor, Professor.user_id == User.id)
        )

        if role is not None:
            stmt = stmt.where(User.role == role.value)

        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)

        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    User.email.ilike(term),
                    User.username.ilike(term),
                    Student.first_name.ilike(term),
                    Student.last_name.ilike(term),
                    Professor.first_name.ilike(term),
                    Professor.last_name.ilike(term),
                )
            )

        total: int = (
            await self._session.scalar(
                select(func.count()).select_from(stmt.subquery())
            )
            or 0
        )

        rows: Sequence[Any] = (
            await self._session.execute(
                stmt.order_by(User.id).offset((page - 1) * size).limit(size)
            )
        ).all()

        items = [
            AdminUserRead(
                id=user.id,
                email=user.email,
                username=user.username,
                role=UserRole(user.role),
                first_name=student_first or professor_first,
                last_name=student_last or professor_last,
                is_active=user.is_active,
                must_change_password=user.must_change_password,
                last_login=user.last_login,
                created_at=user.created_at,
            )
            for user, student_first, student_last, professor_first, professor_last in rows
        ]

        return PaginatedResponse[AdminUserRead](
            items=items, total=total, page=page, size=size
        )

    async def deactivate_user(self, *, actor_id: int, user_id: int) -> None:
        if actor_id == user_id:
            raise SelfDeactivationForbidden()

        user: User | None = await self._users.get(user_id)

        if user is None:
            raise AdminUserNotFound()

        user.is_active = False
        await self._session.flush()

    async def _link_roster(
        self,
        roster: BaseCRUD[Student] | BaseCRUD[Professor],
        *,
        email: str,
        user_id: int,
        role: str,
    ) -> None:
        """Attach a freshly created account to its active, unclaimed roster row.

        Raises RosterLinkImpossible (409) rather than leaving the user unlinked,
        which would make /auth/me unable to resolve first/last name or claim
        status and would block the claim-based /auth/register flow.
        """

        record: Student | Professor | None = await roster.get_by(
            email=email, is_active=True
        )

        if record is None or record.user_id is not None:
            raise RosterLinkImpossible(role)

        record.user_id = user_id

    @staticmethod
    def _default_username(first_name: str, last_name: str) -> str:
        return f"{first_name[0].lower()}{last_name.lower()}"[
            :DEFAULT_USERNAME_MAX_LENGTH
        ]
