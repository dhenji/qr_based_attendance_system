from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Query, UploadFile, status

from api.deps import AuthServiceDep, ProfessorServiceDep, require_role
from features.auth.model import User
from features.auth.schema import AdminPasswordResetResponse
from features.professor.constants import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    DEPARTMENT_MAX_LENGTH,
    MAX_PAGE_SIZE,
    SEARCH_MAX_LENGTH,
)
from features.professor.schema import (
    ProfessorCreate,
    ProfessorDetail,
    ProfessorImportResult,
    ProfessorRead,
    ProfessorUpdate,
)
from shared.enums import UserRole
from shared.pagination import PaginatedResponse

# This module owns /admin/professors ONLY.
#
# The professor feature spans TWO mount points, so it needs TWO routers:
#   professor/router.py        -> /professor        (professor-facing routes)
#   professor/admin_router.py  -> /admin/professors (admin CRUD, this module)
# Do not add admin routes to professor/router.py — they would register as
# /api/professor/... instead of /api/admin/professors/... (ADR-057).
#
# Prefix baked in here; mounted with no prefix= argument in api/router.py
# (the mount lives there — do NOT add an include_router call here).
# Collection routes use "" not "/" so the registered path matches the contract
# exactly. There is NO DELETE /{id} route: soft archive/reactivate is PATCH
# with is_active; the only DELETE is the hard DELETE /{id}/archive.
router = APIRouter(prefix="/admin/professors")


@router.get(
    "",
    response_model=PaginatedResponse[ProfessorRead],
    summary="List professors (search, department/status filters, paginated)",
)
async def list_professors(
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: ProfessorServiceDep,
    search: str | None = Query(default=None, max_length=SEARCH_MAX_LENGTH),
    department: str | None = Query(default=None, max_length=DEPARTMENT_MAX_LENGTH),
    is_active: bool | None = Query(default=None),
    sort_by: Literal["last_name", "email", "created_at"] | None = Query(default=None),
    sort_dir: Literal["asc", "desc"] | None = Query(default=None),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PaginatedResponse[ProfessorRead]:
    return await service.list(
        search=search,
        department=department,
        is_active=is_active,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        size=size,
    )


@router.post(
    "",
    response_model=ProfessorRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a professor",
)
async def create_professor(
    payload: ProfessorCreate,
    user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: ProfessorServiceDep,
) -> ProfessorRead:
    return await service.create(payload=payload, assigned_by=user.id)


# The static import route is declared before /{professor_id} so it is not
# captured as a professor id.
@router.post(
    "/import",
    response_model=ProfessorImportResult,
    summary="Import new professor records from a CSV upload",
)
async def import_professors(
    file: Annotated[UploadFile, File(description="professors.csv")],
    user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: ProfessorServiceDep,
) -> ProfessorImportResult:
    content: bytes = await file.read()

    return await service.import_roster(content=content, actor_id=user.id)


@router.get(
    "/{professor_id}",
    response_model=ProfessorDetail,
    summary="Get a professor",
)
async def get_professor(
    professor_id: int,
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: ProfessorServiceDep,
) -> ProfessorDetail:
    return await service.get(professor_id=professor_id)


@router.patch(
    "/{professor_id}",
    response_model=ProfessorRead,
    summary="Update a professor (fields, courses, archive/reactivate via is_active)",
)
async def update_professor(
    professor_id: int,
    payload: ProfessorUpdate,
    user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: ProfessorServiceDep,
) -> ProfessorRead:
    return await service.update(
        professor_id=professor_id, payload=payload, assigned_by=user.id
    )


@router.delete(
    "/{professor_id}/archive",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Permanently delete an archived professor with no sessions",
)
async def hard_delete_professor(
    professor_id: int,
    user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: ProfessorServiceDep,
) -> None:
    await service.hard_delete(professor_id=professor_id, actor_id=user.id)


@router.post(
    "/{professor_id}/reset-password",
    response_model=AdminPasswordResetResponse,
    summary="Reset a professor's linked account password to a temp one",
)
async def reset_professor_password(
    professor_id: int,
    user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: ProfessorServiceDep,
    auth_service: AuthServiceDep,
) -> AdminPasswordResetResponse:
    # Resolves the roster row to a `users.id`; `AuthService` does the
    # credential write, the same path `/admin/users/{id}/reset-password` uses.
    temp_password: str = await auth_service.admin_reset_password(
        user_id=await service.account_user_id(professor_id), actor_id=user.id
    )
    return AdminPasswordResetResponse(temp_password=temp_password)
