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
    ComponentCreate,
    ComponentRead,
    ComponentUpdate,
    OfferingCreate,
    OfferingRead,
    OfferingUpdate,
    ProfessorAssignment,
    ProfessorReassignment,
    ProfessorReopen,
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
    user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: CourseServiceDep,
) -> OfferingRead:
    return await service.create_offering(payload=payload, actor_id=user.id)


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
    user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: CourseServiceDep,
) -> OfferingRead:
    return await service.update_offering(
        offering_id=offering_id, payload=payload, actor_id=user.id
    )


@router.delete(
    "/{offering_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Permanently delete an archived offering with no enrollments, sessions, or assignments",
)
async def hard_delete_offering(
    offering_id: int,
    user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: CourseServiceDep,
) -> None:
    await service.hard_delete_offering(offering_id=offering_id, actor_id=user.id)


# -- offering components (D77: per-type schedules) -----------------------


@router.get(
    "/{offering_id}/components",
    response_model=list[ComponentRead],
    summary="List active scheduled components of an offering",
)
async def list_components(
    offering_id: int,
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: CourseServiceDep,
) -> Sequence[ComponentRead]:
    return await service.list_components(offering_id=offering_id)


@router.post(
    "/{offering_id}/components",
    response_model=ComponentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a scheduled component (lecture/lab) to an offering",
)
async def create_component(
    offering_id: int,
    payload: ComponentCreate,
    user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: CourseServiceDep,
) -> ComponentRead:
    return await service.create_component(
        offering_id=offering_id, payload=payload, actor_id=user.id
    )


@router.patch(
    "/{offering_id}/components/{component_id}",
    response_model=ComponentRead,
    summary="Update a scheduled component (mutable fields only)",
)
async def update_component(
    offering_id: int,
    component_id: int,
    payload: ComponentUpdate,
    user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: CourseServiceDep,
) -> ComponentRead:
    return await service.update_component(
        offering_id=offering_id,
        component_id=component_id,
        payload=payload,
        actor_id=user.id,
    )


@router.delete(
    "/{offering_id}/components/{component_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Archive a scheduled component (is_active=false)",
)
async def archive_component(
    offering_id: int,
    component_id: int,
    user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: CourseServiceDep,
) -> None:
    await service.archive_component(
        offering_id=offering_id, component_id=component_id, actor_id=user.id
    )


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
    user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: CourseServiceDep,
    effective_from: Annotated[
        date | None,
        Query(description="Start date of the exact assignment row to end"),
    ] = None,
) -> dict[str, date]:
    effective_to: date = await service.remove_professor(
        offering_id=offering_id,
        professor_id=professor_id,
        actor_id=user.id,
        effective_from=effective_from,
    )

    return {"effective_to": effective_to}


@router.delete(
    "/{offering_id}/professors/{professor_id}/permanent",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Permanently remove an assignment with no sessions",
)
async def permanently_remove_professor(
    offering_id: int,
    professor_id: int,
    effective_from: Annotated[
        date,
        Query(
            description=(
                "Start date of the exact assignment row to permanently remove"
            )
        ),
    ],
    user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: CourseServiceDep,
) -> None:
    await service.permanently_remove_professor(
        offering_id=offering_id,
        professor_id=professor_id,
        effective_from=effective_from,
        actor_id=user.id,
    )


@router.post(
    "/{offering_id}/professors/{professor_id}/reassign",
    response_model=AssignmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Reassign a professor on an offering",
)
async def reassign_professor(
    offering_id: int,
    professor_id: int,
    payload: ProfessorReassignment,
    user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: CourseServiceDep,
) -> AssignmentRead:
    return await service.reassign_professor(
        offering_id=offering_id,
        old_professor_id=professor_id,
        payload=payload,
        assigned_by=user.id,
    )


@router.post(
    "/{offering_id}/professors/{professor_id}/reopen",
    response_model=AssignmentRead,
    summary="Undo an ended professor assignment",
)
async def reopen_professor(
    offering_id: int,
    professor_id: int,
    payload: ProfessorReopen,
    user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: CourseServiceDep,
) -> AssignmentRead:
    return await service.reopen_professor(
        offering_id=offering_id,
        professor_id=professor_id,
        payload=payload,
        actor_id=user.id,
    )


@router.post(
    "/{offering_id}/enrollments/bulk",
    response_model=BulkEnrollResult,
    status_code=status.HTTP_201_CREATED,
    summary="Bulk-enroll existing students via CSV upload",
)
async def bulk_enroll(
    offering_id: int,
    file: Annotated[UploadFile, File(description="students.csv")],
    user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: CourseServiceDep,
) -> BulkEnrollResult:
    content: bytes = await file.read()

    return await service.bulk_enroll(
        offering_id=offering_id, content=content, actor_id=user.id
    )


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


@router.delete(
    "/{offering_id}/students/{student_number}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unenroll a student from the offering (link row only)",
)
async def unenroll_student(
    offering_id: int,
    student_number: str,
    user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: CourseServiceDep,
) -> None:
    await service.unenroll_student(
        offering_id=offering_id, student_number=student_number, actor_id=user.id
    )
