from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from api.deps import CourseServiceDep, require_role
from features.auth.model import User
from features.course.constants import DEFAULT_PAGE, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from features.course.schema import CourseCreate, CourseRead, CourseUpdate
from shared.enums import UserRole
from shared.pagination import PaginatedResponse

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
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
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
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: CourseServiceDep,
) -> CourseRead:
    return await service.create(payload=payload)


@router.get(
    "/{course_id}",
    response_model=CourseRead,
    summary="Get a course template",
)
async def get_course(
    course_id: int,
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
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
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: CourseServiceDep,
) -> CourseRead:
    return await service.update(course_id=course_id, payload=payload)


@router.delete(
    "/{course_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Archive a course template (is_active=false)",
)
async def archive_course(
    course_id: int,
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: CourseServiceDep,
) -> None:
    await service.archive(course_id=course_id)
