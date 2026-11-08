from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from api.deps import AttendanceServiceDep, require_role
from features.attendance.constants import (
    RECENT_SCANS_DEFAULT_LIMIT,
    RECENT_SCANS_MAX_LIMIT,
    REVIEW_STATUS_MAX_LENGTH,
)
from shared.constants import SEMESTER_MAX_LENGTH
from features.attendance.schema import (
    AttendanceRecordsResponse,
    AttendanceSummaryResponse,
    LivenessReviewItem,
    OverviewResponse,
    RecentScansResponse,
    ResolveReviewRequest,
    ResolveReviewResponse,
)
from features.auth.model import User
from shared.enums import SessionType, UserRole
from shared.pagination import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PaginatedResponse,
)

# This module owns /admin/attendance ONLY.
#
# The attendance feature spans TWO mount points, so it needs TWO routers:
#   attendance/router.py        -> /student            (scan + history)
#   attendance/admin_router.py  -> /admin/attendance   (review queue, this module)
# Do not add admin routes to attendance/router.py — they would register as
# /api/student/... instead of /api/admin/attendance/...
router = APIRouter(prefix="/admin/attendance")

AdminUser = Annotated[User, Depends(require_role(UserRole.ADMIN))]

OVERVIEW_EXPORT_FILENAME = "attendance-overview.csv"


@router.get(
    "/overview",
    response_model=OverviewResponse,
    summary="Per-course attendance overview",
)
async def get_attendance_overview(
    _: AdminUser,
    service: AttendanceServiceDep,
    program_id: int | None = Query(default=None, gt=0),
    year_level_id: int | None = Query(default=None, gt=0),
    semester: str | None = Query(default=None, max_length=SEMESTER_MAX_LENGTH),
    course_id: int | None = Query(default=None, gt=0),
    professor_id: int | None = Query(default=None, gt=0),
    session_type: SessionType | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
) -> OverviewResponse:
    return await service.get_overview(
        program_id=program_id,
        year_level_id=year_level_id,
        semester=semester,
        course_id=course_id,
        professor_id=professor_id,
        session_type=session_type.value if session_type is not None else None,
        date_from=date_from,
        date_to=date_to,
    )



@router.get(
    "/overview/export",
    summary="Download the attendance overview as CSV",
)
async def export_attendance_overview(
    _: AdminUser,
    service: AttendanceServiceDep,
    course_id: int | None = Query(default=None, gt=0),
    professor_id: int | None = Query(default=None, gt=0),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
) -> StreamingResponse:
    content: str = await service.export_overview_csv(
        course_id=course_id,
        professor_id=professor_id,
        date_from=date_from,
        date_to=date_to,
    )

    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={OVERVIEW_EXPORT_FILENAME}"
        },
    )


@router.get(
    "/recent-scans",
    response_model=RecentScansResponse,
    summary="Latest attendance scans",
)
async def get_recent_scans(
    _: AdminUser,
    service: AttendanceServiceDep,
    limit: int = Query(
        default=RECENT_SCANS_DEFAULT_LIMIT, ge=1, le=RECENT_SCANS_MAX_LIMIT
    ),
) -> RecentScansResponse:
    return await service.get_recent_scans(limit=limit)


@router.get(
    "/liveness-review",
    response_model=PaginatedResponse[LivenessReviewItem],
    summary="List flagged liveness reviews",
)
async def list_liveness_review(
    _: AdminUser,
    service: AttendanceServiceDep,
    status: str | None = Query(default=None, max_length=REVIEW_STATUS_MAX_LENGTH),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PaginatedResponse[LivenessReviewItem]:
    return await service.list_liveness_review(status=status, page=page, size=size)


@router.patch(
    "/liveness-review/{record_id}/resolve",
    response_model=ResolveReviewResponse,
    summary="Approve or reject a flagged review",
)
async def resolve_liveness_review(
    record_id: int,
    body: ResolveReviewRequest,
    user: AdminUser,
    service: AttendanceServiceDep,
) -> ResolveReviewResponse:
    # The note rides inside `liveness_evidence` (attendance_records has no
    # dedicated column); the service also writes the audit row.
    return await service.resolve_review(
        record_id=record_id,
        decision=body.decision,
        actor_id=user.id,
        note=body.note,
    )


@router.get(
    "/summary",
    response_model=AttendanceSummaryResponse,
    summary="Aggregate attendance KPIs over the filter set",
)
async def get_attendance_summary(
    _: AdminUser,
    service: AttendanceServiceDep,
    program_id: int | None = Query(default=None, gt=0),
    year_level_id: int | None = Query(default=None, gt=0),
    semester: str | None = Query(default=None, max_length=SEMESTER_MAX_LENGTH),
    course_id: int | None = Query(default=None, gt=0),
    professor_id: int | None = Query(default=None, gt=0),
    session_type: SessionType | None = Query(default=None),
    status: str | None = Query(default=None, max_length=20),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
) -> AttendanceSummaryResponse:
    return await service.get_summary(
        program_id=program_id,
        year_level_id=year_level_id,
        semester=semester,
        course_id=course_id,
        professor_id=professor_id,
        session_type=session_type.value if session_type is not None else None,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )


@router.get(
    "/records",
    response_model=AttendanceRecordsResponse,
    summary="Paginated detailed attendance records",
)
async def get_attendance_records(
    _: AdminUser,
    service: AttendanceServiceDep,
    program_id: int | None = Query(default=None, gt=0),
    year_level_id: int | None = Query(default=None, gt=0),
    semester: str | None = Query(default=None, max_length=SEMESTER_MAX_LENGTH),
    course_id: int | None = Query(default=None, gt=0),
    professor_id: int | None = Query(default=None, gt=0),
    session_type: SessionType | None = Query(default=None),
    status: str | None = Query(default=None, max_length=20),
    student_search: str | None = Query(default=None, max_length=100),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    sort_by: str = Query(default="scanned_at", max_length=30),
    sort_dir: str = Query(default="desc", max_length=4),
) -> AttendanceRecordsResponse:
    return await service.get_records(
        program_id=program_id,
        year_level_id=year_level_id,
        semester=semester,
        course_id=course_id,
        professor_id=professor_id,
        session_type=session_type.value if session_type is not None else None,
        status=status,
        student_search=student_search,
        date_from=date_from,
        date_to=date_to,
        page=page,
        size=size,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


@router.get(
    "/records/export",
    summary="Download detailed attendance records as CSV",
)
async def export_attendance_records(
    _: AdminUser,
    service: AttendanceServiceDep,
    program_id: int | None = Query(default=None, gt=0),
    year_level_id: int | None = Query(default=None, gt=0),
    semester: str | None = Query(default=None, max_length=SEMESTER_MAX_LENGTH),
    course_id: int | None = Query(default=None, gt=0),
    professor_id: int | None = Query(default=None, gt=0),
    session_type: SessionType | None = Query(default=None),
    status: str | None = Query(default=None, max_length=20),
    student_search: str | None = Query(default=None, max_length=100),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
) -> StreamingResponse:
    content: str = await service.export_records_csv(
        program_id=program_id,
        year_level_id=year_level_id,
        semester=semester,
        course_id=course_id,
        professor_id=professor_id,
        session_type=session_type.value if session_type is not None else None,
        status=status,
        student_search=student_search,
        date_from=date_from,
        date_to=date_to,
    )
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=attendance-records.csv"},
    )
