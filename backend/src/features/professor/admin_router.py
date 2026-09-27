from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status

from api.deps import ProfessorServiceDep, require_role
from features.auth.model import User
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
# (PROMPT 3.7 owns that mount — do NOT add an include_router call here).
# Collection routes use "" not "/" so the registered path matches the contract
# exactly. There is NO DELETE /{id} route: soft archive/reactivate is PATCH
# with is_active, and the only DELETE is the hard DELETE /{id}/archive that
# PROMPT 3.9 adds.
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
    sort_by: Literal["last_name", "email", "created_at"] | None = Query(
        default=None
    ),
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
