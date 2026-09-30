from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile, status

from api.deps import CourseServiceDep, require_role
from features.auth.model import User
from features.course.constants import DEFAULT_PAGE, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from features.course.schema import (
    AssignmentRead,
    BulkEnrollResult,
    OfferingCreate,
    OfferingRead,
    OfferingUpdate,
    ProfessorAssignment,
    RosterItem,
)
from shared.enums import UserRole
from shared.pagination import PaginatedResponse

# This module owns /admin/offerings ONLY.
#
# The course feature spans TWO mount points, so it needs TWO routers:
#   course/router.py           -> /admin/courses   (Course template CRUD)
#   course/offering_router.py  -> /admin/offerings (CourseOffering CRUD)
# Do not add offering routes to course/router.py — they would register as
# /api/admin/courses/{id}/... instead of /api/admin/offerings/...
#
# Prefix baked in here; mounted with no prefix= argument in api/router.py.
# Collection routes use "" not "/" so the registered path matches the contract
# exactly.
router = APIRouter(prefix="/admin/offerings")


@router.get(
    "",
    response_model=PaginatedResponse[OfferingRead],
    summary="List offerings (program/year/semester/course/status filters, paginated)",
)
async def list_offerings(
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: CourseServiceDep,
    program_id: int | None = Query(default=None, gt=0),
    year_level_id: int | None = Query(default=None, gt=0),
    semester: str | None = Query(default=None),
    course_id: int | None = Query(default=None, gt=0),
    is_active: bool | None = Query(default=None),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PaginatedResponse[OfferingRead]:
    return await service.list_offerings(
        program_id=program_id,
        year_level_id=year_level_id,
        semester=semester,
        course_id=course_id,
        is_active=is_active,
        page=page,
        size=size,
    )


@router.post(
    "",
    response_model=OfferingRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a course offering",
)
async def create_offering(
    payload: OfferingCreate,
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: CourseServiceDep,
) -> OfferingRead:
    return await service.create_offering(payload=payload)


@router.get(
    "/{offering_id}",
    response_model=OfferingRead,
    summary="Get a course offering",
)
async def get_offering(
    offering_id: int,
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: CourseServiceDep,
) -> OfferingRead:
    return await service.get_offering(offering_id=offering_id)


@router.patch(
    "/{offering_id}",
    response_model=OfferingRead,
    summary="Update a course offering (mutable fields only)",
)
async def update_offering(
    offering_id: int,
    payload: OfferingUpdate,
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: CourseServiceDep,
) -> OfferingRead:
    return await service.update_offering(offering_id=offering_id, payload=payload)


@router.delete(
    "/{offering_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Archive a course offering (is_active=false)",
)
async def archive_offering(
    offering_id: int,
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: CourseServiceDep,
) -> None:
    await service.archive_offering(offering_id=offering_id)


@router.get(
    "/{offering_id}/professors",
    response_model=list[AssignmentRead],
    summary="List professor assignments of an offering",
)
async def list_professors(
    offering_id: int,
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: CourseServiceDep,
) -> Sequence[AssignmentRead]:
    return await service.list_assignments(offering_id=offering_id)


@router.post(
    "/{offering_id}/professors",
    response_model=AssignmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Assign a professor to an offering",
)
async def assign_professor(
    offering_id: int,
    payload: ProfessorAssignment,
    user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: CourseServiceDep,
) -> AssignmentRead:
    return await service.assign_professor(
        offering_id=offering_id, payload=payload, assigned_by=user.id
    )


@router.delete(
    "/{offering_id}/professors/{professor_id}",
    summary="End a professor assignment (effective_to=today)",
)
async def remove_professor(
    offering_id: int,
    professor_id: int,
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: CourseServiceDep,
) -> dict[str, date]:
    effective_to: date = await service.remove_professor(
        offering_id=offering_id, professor_id=professor_id
    )

    return {"effective_to": effective_to}


@router.post(
    "/{offering_id}/enrollments/bulk",
    response_model=BulkEnrollResult,
    status_code=status.HTTP_201_CREATED,
    summary="Bulk-enroll existing students via CSV upload",
)
async def bulk_enroll(
    offering_id: int,
    file: Annotated[UploadFile, File(description="students.csv")],
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: CourseServiceDep,
) -> BulkEnrollResult:
    content: bytes = await file.read()

    return await service.bulk_enroll(offering_id=offering_id, content=content)


@router.get(
    "/{offering_id}/students",
    response_model=PaginatedResponse[RosterItem],
    summary="Read the offering roster (section filter, paginated)",
)
async def get_roster(
    offering_id: int,
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: CourseServiceDep,
    section: str | None = Query(default=None),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PaginatedResponse[RosterItem]:
    return await service.get_roster(
        offering_id=offering_id, section=section, page=page, size=size
    )
