from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Query, Response, UploadFile, status

from shared.csv_import import csv_template_header
from shared.pagination import PaginatedResponse

from api.deps import AdminUser, CourseServiceDep
from features.course.constants import DEFAULT_PAGE, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from features.course.schema import (
    CourseCreate,
    CourseImportResult,
    CourseRead,
    CourseUpdate,
)
from features.course.service import COURSE_CSV_COLUMNS

# This module owns /admin/courses ONLY.
#
# The course feature spans TWO mount points, so it needs TWO routers:
#   course/router.py          -> /admin/courses   (Course template CRUD)
#   course/offering_router.py -> /admin/offerings (CourseOffering CRUD)
# Do not add offering routes here — they would register as
# /api/admin/courses/{id}/... instead of /api/admin/offerings/{id}/...
#
# Prefix baked in here; mounted with no prefix= argument in api/router.py.
# Collection routes use "" not "/" so the registered path matches the contract
# exactly.
router = APIRouter(prefix="/admin/courses")


@router.get(
    "",
    response_model=PaginatedResponse[CourseRead],
    summary="List course templates (status filter, paginated)",
)
async def list_courses(
    _: AdminUser,
    service: CourseServiceDep,
    is_active: bool | None = Query(default=None),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PaginatedResponse[CourseRead]:
    return await service.list(is_active=is_active, page=page, size=size)


@router.post(
    "",
    response_model=CourseRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a course template",
)
async def create_course(
    payload: CourseCreate,
    user: AdminUser,
    service: CourseServiceDep,
) -> CourseRead:
    return await service.create(payload=payload, actor_id=user.id)


# Static import/template routes are declared before /{course_id} so they
# are not captured as course ids.
@router.post(
    "/import",
    response_model=CourseImportResult,
    summary="Import new course templates from a CSV upload",
)
async def import_courses(
    file: Annotated[UploadFile, File(description="courses.csv")],
    user: AdminUser,
    service: CourseServiceDep,
) -> CourseImportResult:
    content: bytes = await file.read()

    return await service.import_roster(content=content, actor_id=user.id)


@router.get(
    "/import/template",
    summary="Download the course import CSV template",
)
async def download_import_template(
    _: AdminUser,
) -> Response:
    return Response(
        content=csv_template_header(COURSE_CSV_COLUMNS),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=courses_template.csv"},
    )


@router.get(
    "/{course_id}",
    response_model=CourseRead,
    summary="Get a course template",
)
async def get_course(
    course_id: int,
    _: AdminUser,
    service: CourseServiceDep,
) -> CourseRead:
    return await service.get(course_id=course_id)


@router.patch(
    "/{course_id}",
    response_model=CourseRead,
    summary="Update a course template",
)
async def update_course(
    course_id: int,
    payload: CourseUpdate,
    user: AdminUser,
    service: CourseServiceDep,
) -> CourseRead:
    return await service.update(course_id=course_id, payload=payload, actor_id=user.id)


@router.delete(
    "/{course_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Permanently delete an archived course with no offerings",
)
async def hard_delete_course(
    course_id: int,
    user: AdminUser,
    service: CourseServiceDep,
) -> None:
    await service.hard_delete(course_id=course_id, actor_id=user.id)
