from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query

from api.deps import AttendanceServiceDep, require_role
from features.attendance.constants import (
    IDEMPOTENCY_KEY_MAX_LENGTH,
    SCAN_RATE_LIMIT_MAX_CALLS,
    SCAN_RATE_LIMIT_WINDOW_SECONDS,
)
from features.attendance.schema import (
    HistoryResponse,
    PrecheckRequest,
    PrecheckResponse,
    ScanRequest,
    ScanResponse,
)
from features.auth.model import User
from shared.enums import UserRole, ValidationStatus
from shared.pagination import DEFAULT_PAGE, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from shared.rate_limit import rate_limit

# Prefix baked in here; mounted without a prefix argument in api/router.py.
#
# This module shares the /student mount point with
# `features/student/router.py` (which owns /student/sessions/verify-code).
# Inner paths must not collide: session verification lives there,
# scan lives here.
router = APIRouter(prefix="/student")

StudentUser = Annotated[User, Depends(require_role(UserRole.STUDENT))]


@router.post(
    "/attendance/scan",
    response_model=ScanResponse,
    summary="Submit attendance scan (online or offline-sync replay)",
)
async def submit_scan(
    payload: ScanRequest,
    user: StudentUser,
    service: AttendanceServiceDep,
    idempotency_key: str | None = Header(
        default=None,
        alias="X-Idempotency-Key",
        max_length=IDEMPOTENCY_KEY_MAX_LENGTH,
    ),
    _: None = Depends(
        rate_limit(SCAN_RATE_LIMIT_MAX_CALLS, SCAN_RATE_LIMIT_WINDOW_SECONDS)
    ),
) -> ScanResponse:
    _: StudentUser = user  # role gate only; student resolved by payload.student_number
    return await service.submit_scan(payload=payload, idempotency_key=idempotency_key)


@router.post(
    "/attendance/precheck",
    response_model=PrecheckResponse,
    summary="Pre-check enrollment and duplicate scan before full attendance submission",
)
async def precheck_scan(
    payload: PrecheckRequest,
    user: StudentUser,
    service: AttendanceServiceDep,
) -> PrecheckResponse:
    _: StudentUser = user  # role gate only
    return await service.precheck_scan(
        session_id=payload.session_id, student_number=payload.student_number
    )


@router.get(
    "/attendance/history",
    response_model=HistoryResponse,
    summary="Student attendance history with filters and summary",
)
async def attendance_history(
    user: StudentUser,
    service: AttendanceServiceDep,
    program_id: int | None = Query(default=None, gt=0),
    year_level_id: int | None = Query(default=None, gt=0),
    semester: str | None = Query(default=None, max_length=20),
    course_id: int | None = Query(default=None, gt=0),
    status: ValidationStatus | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    sort_by: str | None = Query(default=None, max_length=20),
    sort_dir: str | None = Query(default=None, max_length=4),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> HistoryResponse:
    return await service.get_history(
        user_id=user.id,
        program_id=program_id,
        year_level_id=year_level_id,
        semester=semester,
        course_id=course_id,
        status=status.value if status is not None else None,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        size=size,
    )
