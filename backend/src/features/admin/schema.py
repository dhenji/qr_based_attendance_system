from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from shared.enums import UserRole

_CREATABLE_ROLES: set[UserRole] = {UserRole.ADMIN, UserRole.PROFESSOR, UserRole.STUDENT}


class AdminUserBase(BaseModel):
    email: EmailStr
    role: UserRole


class AdminUserCreate(AdminUserBase):
    first_name: str = Field(min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    username: str | None = Field(default=None, min_length=3, max_length=20)

    @field_validator("role")
    @classmethod
    def _restrict_role(cls, value: UserRole) -> UserRole:
        if value not in _CREATABLE_ROLES:
            raise ValueError(
                "super_admin accounts cannot be created; the first one is seeded at deployment"
            )

        return value


class AdminUserRead(AdminUserBase):
    id: int
    username: str | None
    first_name: str | None = None
    last_name: str | None = None
    is_active: bool
    must_change_password: bool
    last_login: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminUserCreateResponse(AdminUserRead):
    temp_password: str
