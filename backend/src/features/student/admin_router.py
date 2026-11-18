from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status

from shared.csv_import import csv_template_header
from shared.enums import UserRole
from shared.pagination import PaginatedResponse

from api.deps import AuthServiceDep, StudentServiceDep, require_role
from features.auth.model import User
from features.auth.schema import AdminPasswordResetResponse
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
    StudentImportResult,
    StudentRead,
    StudentUpdate,
)
from features.student.service import ROSTER_CSV_COLUMNS

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
    user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: StudentServiceDep,
) -> StudentRead:
    return await service.create(payload=payload, actor_id=user.id)


# Static import/template routes are declared before /{student_id} so they
# are not captured as student ids.
@router.post(
    "/import",
    response_model=StudentImportResult,
    summary="Import new student records from a CSV upload",
)
async def import_students(
    file: Annotated[UploadFile, File(description="students.csv")],
    user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: StudentServiceDep,
) -> StudentImportResult:
    content: bytes = await file.read()

    return await service.import_roster(content=content, actor_id=user.id)


@router.get(
    "/import/template",
    summary="Download the student import CSV template",
)
async def download_import_template(
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
) -> Response:
    return Response(
        content=csv_template_header(ROSTER_CSV_COLUMNS),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=students_template.csv"},
    )


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
    user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: StudentServiceDep,
) -> StudentRead:
    return await service.update(
        student_id=student_id, payload=payload, actor_id=user.id
    )


@router.delete(
    "/{student_id}/archive",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Permanently delete an archived student with no records",
)
async def hard_delete_student(
    student_id: int,
    user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: StudentServiceDep,
) -> None:
    await service.hard_delete(student_id=student_id, actor_id=user.id)


@router.post(
    "/{student_id}/reset-password",
    response_model=AdminPasswordResetResponse,
    summary="Reset a student's linked account password to a temp one",
)
async def reset_student_password(
    student_id: int,
    user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: StudentServiceDep,
    auth_service: AuthServiceDep,
) -> AdminPasswordResetResponse:
    # The path names a roster row, so this resolves it to a `users.id` first;
    # `AuthService` then does the credential write, which is the same code path
    # `/admin/users/{id}/reset-password` uses.
    temp_password: str = await auth_service.admin_reset_password(
        user_id=await service.account_user_id(student_id), actor_id=user.id
    )
    return AdminPasswordResetResponse(temp_password=temp_password)
