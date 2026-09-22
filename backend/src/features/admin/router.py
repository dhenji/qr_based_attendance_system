from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from api.deps import AdminServiceDep, require_role
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
from shared.enums import UserRole
from shared.pagination import PaginatedResponse

router = APIRouter()


@router.get(
    "/",
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
    "/",
    response_model=AdminUserCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an admin/professor/student user account (returns temp password once)",
)
async def create_user(
    payload: AdminUserCreate,
    _: Annotated[User, Depends(require_role(UserRole.SUPER_ADMIN))],
    service: AdminServiceDep,
) -> AdminUserCreateResponse:
    return await service.create_user(payload=payload)


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
