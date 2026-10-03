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
from features.attendance.schema import (
    LivenessReviewItem,
    OverviewResponse,
    RecentScansResponse,
    ResolveReviewRequest,
    ResolveReviewResponse,
)
from features.auth.model import User
from shared.enums import UserRole
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
    course_id: int | None = Query(default=None, gt=0),
    professor_id: int | None = Query(default=None, gt=0),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
) -> OverviewResponse:
    return await service.get_overview(
        course_id=course_id,
        professor_id=professor_id,
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
