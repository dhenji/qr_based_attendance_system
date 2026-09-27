from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status

from api.deps import StudentServiceDep, require_role
from features.auth.model import User
from features.student.constants import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    SEARCH_MAX_LENGTH,
    SECTION_MAX_LENGTH,
)
from features.student.schema import (
    StudentCreate,
    StudentDetail,
    StudentRead,
    StudentUpdate,
)
from shared.enums import UserRole
from shared.pagination import PaginatedResponse

# This module owns /admin/students ONLY.
#
# The student feature spans TWO mount points, so it needs TWO routers:
#   student/router.py        -> /student         (student-facing routes)
#   student/admin_router.py  -> /admin/students  (admin CRUD, this module)
# Do not add admin routes to student/router.py — they would register as
# /api/student/... instead of /api/admin/students/... (ADR-057).
#
# Prefix baked in here; mounted with no prefix= argument in api/router.py
# (the mount lives there — do NOT add an include_router call here).
# Collection routes use "" not "/" so the registered path matches the contract
# exactly. There is NO DELETE /{id} route: soft archive/reactivate is PATCH
# with is_active; the only DELETE is the hard DELETE /{id}/archive.
router = APIRouter(prefix="/admin/students")


@router.get(
    "",
    response_model=PaginatedResponse[StudentRead],
    summary="List students (search, program/year/section/status filters, paginated)",
)
async def list_students(
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: StudentServiceDep,
    search: str | None = Query(default=None, max_length=SEARCH_MAX_LENGTH),
    program_id: int | None = Query(default=None, gt=0),
    year_level_id: int | None = Query(default=None, gt=0),
    section: str | None = Query(default=None, max_length=SECTION_MAX_LENGTH),
    is_active: bool | None = Query(default=None),
    sort_by: Literal["last_name", "student_id", "created_at"] | None = Query(
        default=None
    ),
    sort_dir: Literal["asc", "desc"] | None = Query(default=None),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PaginatedResponse[StudentRead]:
    return await service.list(
        search=search,
        program_id=program_id,
        year_level_id=year_level_id,
        section=section,
        is_active=is_active,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        size=size,
    )


@router.post(
    "",
    response_model=StudentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a student",
)
async def create_student(
    payload: StudentCreate,
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: StudentServiceDep,
) -> StudentRead:
    return await service.create(payload=payload)


@router.get(
    "/{student_id}",
    response_model=StudentDetail,
    summary="Get a student",
)
async def get_student(
    student_id: int,
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: StudentServiceDep,
) -> StudentDetail:
    return await service.get(student_id=student_id)


@router.patch(
    "/{student_id}",
    response_model=StudentRead,
    summary="Update a student (fields, program/year, archive/reactivate via is_active)",
)
async def update_student(
    student_id: int,
    payload: StudentUpdate,
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: StudentServiceDep,
) -> StudentRead:
    return await service.update(student_id=student_id, payload=payload)
