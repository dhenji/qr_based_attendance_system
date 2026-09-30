from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from api.deps import AttendanceServiceDep, require_role
from features.attendance.constants import REVIEW_STATUS_MAX_LENGTH
from features.attendance.schema import (
    LivenessReviewItem,
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
    # dedicated column). The prompt also asks for an audit-log row here;
    # there is no audit table until Phase 8, so the decision is recorded on
    # the record itself for now.
    return await service.resolve_review(
        record_id=record_id,
        decision=body.decision,
        actor_id=user.id,
        note=body.note,
    )
