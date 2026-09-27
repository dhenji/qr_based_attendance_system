from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from api.deps import ProfessorServiceDep, SessionServiceDep, require_role
from features.auth.model import User
from features.professor.schema import AssignedOfferingItem
from features.session.schema import (
    ProfessorAttendanceItem,
    SessionActiveResponse,
    SessionCloseResponse,
    SessionCreate,
    SessionHistoryItem,
    SessionListItem,
    SessionRead,
)
from shared.enums import UserRole, ValidationStatus
from shared.pagination import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PaginatedResponse,
)

# Session routes are professor-scoped; the prefix is baked in here and the
# router is mounted without a prefix argument in api/router.py.
#
# This module owns /professor/courses, /professor/sessions/* and
# /professor/attendance. It shares the /professor mount point
# with `features/professor/router.py` — several routers may share a prefix,
# but their inner paths must not collide, so do not add profile paths here:
# /professor/profile* belongs to the professor module.
#
# NOTE: GET /courses returns the enriched row shape (units, enrolled_count
# and the derived section set alongside the assignment columns). Keep single
# ownership here.
router = APIRouter(prefix="/professor")

ProfessorUser = Annotated[User, Depends(require_role(UserRole.PROFESSOR))]


@router.get(
    "/courses",
    response_model=PaginatedResponse[AssignedOfferingItem],
    summary="List own active course assignments",
)
async def list_own_courses(
    user: ProfessorUser,
    professor_service: ProfessorServiceDep,
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PaginatedResponse[AssignedOfferingItem]:
    return await professor_service.list_assigned_offerings(
        user_id=user.id, page=page, size=size
    )


@router.get(
    "/sessions",
    response_model=PaginatedResponse[SessionListItem],
    summary="List own sessions",
)
async def list_sessions(
    user: ProfessorUser,
    service: SessionServiceDep,
    professor_service: ProfessorServiceDep,
    date_from: datetime | None = Query(default=None, alias="from"),
    date_to: datetime | None = Query(default=None, alias="to"),
    offering_id: int | None = Query(default=None, gt=0),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PaginatedResponse[SessionListItem]:
    professor_id: int = await professor_service.resolve_professor_id(user_id=user.id)

    return await service.list_professor_sessions(
        professor_id=professor_id,
        date_from=date_from,
        date_to=date_to,
        offering_id=offering_id,
        page=page,
        size=size,
    )


@router.get(
    "/sessions/history",
    response_model=PaginatedResponse[SessionHistoryItem],
    summary="Session history with counts and rates",
)
async def session_history(
    user: ProfessorUser,
    service: SessionServiceDep,
    professor_service: ProfessorServiceDep,
    offering_id: int | None = Query(default=None, gt=0),
    section: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    sort_dir: str | None = Query(default=None),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PaginatedResponse[SessionHistoryItem]:
    professor_id: int = await professor_service.resolve_professor_id(user_id=user.id)

    return await service.get_session_history(
        professor_id=professor_id,
        offering_id=offering_id,
        section=section,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        size=size,
    )


@router.post(
    "/sessions",
    response_model=SessionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Open a new attendance session",
)
async def create_session(
    payload: SessionCreate,
    user: ProfessorUser,
    service: SessionServiceDep,
    professor_service: ProfessorServiceDep,
) -> SessionRead:
    professor_id: int = await professor_service.resolve_professor_id(user_id=user.id)

    return await service.create_session(
        professor_id=professor_id, payload=payload
    )


@router.get(
    "/sessions/active/{session_id}",
    response_model=SessionActiveResponse,
    summary="Live session detail with dual timers",
)
async def get_active_session(
    session_id: int,
    user: ProfessorUser,
    service: SessionServiceDep,
    professor_service: ProfessorServiceDep,
) -> SessionActiveResponse:
    professor_id: int = await professor_service.resolve_professor_id(user_id=user.id)

    return await service.get_active_session(
        session_id=session_id, professor_id=professor_id
    )


@router.post(
    "/sessions/{session_id}/close",
    response_model=SessionCloseResponse,
    summary="Manually close session scanning",
)
async def close_session(
    session_id: int,
    user: ProfessorUser,
    service: SessionServiceDep,
    professor_service: ProfessorServiceDep,
) -> SessionCloseResponse:
    professor_id: int = await professor_service.resolve_professor_id(user_id=user.id)

    return await service.close_session(
        session_id=session_id, professor_id=professor_id
    )


@router.get(
    "/attendance",
    response_model=PaginatedResponse[ProfessorAttendanceItem],
    summary="Query attendance records with filters",
)
async def professor_attendance(
    user: ProfessorUser,
    service: SessionServiceDep,
    professor_service: ProfessorServiceDep,
    course_id: int | None = Query(default=None, gt=0),
    offering_id: int | None = Query(default=None, gt=0),
    section: str | None = Query(default=None),
    session_id: int | None = Query(default=None, gt=0),
    status: ValidationStatus | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    sort_dir: str | None = Query(default=None),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PaginatedResponse[ProfessorAttendanceItem]:
    professor_id: int = await professor_service.resolve_professor_id(user_id=user.id)

    return await service.get_professor_attendance(
        professor_id=professor_id,
        course_id=course_id,
        offering_id=offering_id,
        section=section,
        session_id=session_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        size=size,
    )
