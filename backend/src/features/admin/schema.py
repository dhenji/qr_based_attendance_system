from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from features.admin.constants import NAME_MAX_LENGTH, NAME_MIN_LENGTH
from shared.enums import UserRole

_CREATABLE_ROLES: set[UserRole] = {UserRole.ADMIN, UserRole.PROFESSOR, UserRole.STUDENT}


class AdminUserBase(BaseModel):
    email: EmailStr
    role: UserRole


class AdminUserCreate(AdminUserBase):
    first_name: str = Field(min_length=NAME_MIN_LENGTH, max_length=NAME_MAX_LENGTH)
    middle_name: str | None = Field(default=None, max_length=NAME_MAX_LENGTH)
    last_name: str = Field(min_length=NAME_MIN_LENGTH, max_length=NAME_MAX_LENGTH)

    @field_validator("role")
    @classmethod
    def _restrict_role(cls, value: UserRole) -> UserRole:
        if value not in _CREATABLE_ROLES:
            raise ValueError(
                "super_admin accounts cannot be created; the first one is seeded at deployment"
            )

        return value


class AdminUserRead(AdminUserBase):
    email: EmailStr | None = None
    id: int
    first_name: str | None = None
    last_name: str | None = None
    is_active: bool
    must_change_password: bool
    last_login: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminUserCreateResponse(AdminUserRead):
    temp_password: str
