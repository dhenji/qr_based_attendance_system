from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from api.deps import AdminServiceDep, AuthServiceDep, require_role
from features.admin.constants import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    SEARCH_MAX_LENGTH,
)
from features.admin.schema import (
    AdminUserCreate,
    AdminUserCreateResponse,
    AdminUserRead,
)
from features.auth.model import User
from features.auth.schema import AdminPasswordResetResponse
from shared.enums import UserRole
from shared.pagination import PaginatedResponse

# The full contract path is baked into the router and mounted without a prefix
# argument (api/router.py). This module owns the admin *user* endpoints only;
# sibling features mount their own routers under /api/admin/... (programs,
# courses, students, ...) - one APIRouter per mount point.
router = APIRouter(prefix="/admin/users")


@router.get(
    "",
    response_model=PaginatedResponse[AdminUserRead],
    summary="List users (search, role/status filters, paginated)",
)
async def list_users(
    _: Annotated[User, Depends(require_role(UserRole.SUPER_ADMIN))],
    service: AdminServiceDep,
    search: str | None = Query(default=None, max_length=SEARCH_MAX_LENGTH),
    role: UserRole | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PaginatedResponse[AdminUserRead]:
    return await service.list_users(
        search=search, role=role, is_active=is_active, page=page, size=size
    )


@router.post(
    "",
    response_model=AdminUserCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an admin/professor/student user account (returns temp password once)",
)
async def create_user(
    payload: AdminUserCreate,
    actor: Annotated[User, Depends(require_role(UserRole.SUPER_ADMIN))],
    service: AdminServiceDep,
) -> AdminUserCreateResponse:
    return await service.create_user(payload=payload, actor_id=actor.id)


@router.post(
    "/{user_id}/reset-password",
    response_model=AdminPasswordResetResponse,
    summary="Reset a user account's password to a temp one (clears lockout)",
)
async def reset_user_password(
    user_id: int,
    actor: Annotated[User, Depends(require_role(UserRole.SUPER_ADMIN))],
    auth_service: AuthServiceDep,
) -> AdminPasswordResetResponse:
    # `AuthService` owns the credential write — this route names a `users.id`
    # directly, so there is no roster row to resolve first.
    temp_password: str = await auth_service.admin_reset_password(
        user_id=user_id, actor_id=actor.id
    )
    return AdminPasswordResetResponse(temp_password=temp_password)


@router.patch(
    "/{user_id}/deactivate",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-deactivate a user (rejects self-deactivation)",
)
async def deactivate_user(
    user_id: int,
    actor: Annotated[User, Depends(require_role(UserRole.SUPER_ADMIN))],
    service: AdminServiceDep,
) -> None:
    await service.deactivate_user(actor_id=actor.id, user_id=user_id)
