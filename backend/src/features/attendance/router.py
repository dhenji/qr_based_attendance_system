from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse

from api.deps import AttendanceServiceDep, require_role
from core.config import get_settings
from shared.constants import SEMESTER_MAX_LENGTH
from shared.enums import UserRole, ValidationStatus
from shared.pagination import DEFAULT_PAGE, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from shared.rate_limit import rate_limit
from features.attendance.constants import (
    HISTORY_SORT_BY_MAX_LENGTH,
    HISTORY_SORT_DIR_MAX_LENGTH,
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

# Prefix baked in here; mounted without a prefix argument in api/router.py.
#
# This module shares the /student mount point with
# `features/student/router.py` (which owns /student/sessions/verify-code).
# Inner paths must not collide: session verification lives there,
# scan lives here.
router = APIRouter(prefix="/student")

StudentUser = Annotated[User, Depends(require_role(UserRole.STUDENT))]

# Module-level like OVERVIEW_EXPORT_FILENAME in admin_router.py, not constants.py:
# only the backup pipeline keeps its filenames there.
HISTORY_EXPORT_FILENAME = "attendance-history.csv"

_scan_limiter = rate_limit(SCAN_RATE_LIMIT_MAX_CALLS, SCAN_RATE_LIMIT_WINDOW_SECONDS)


async def _scan_rate_limit(request: Request) -> None:
    # Load profile: a single load host shares one IP bucket, so the abuse
    # gate is lifted while benchmarks run and enforced everywhere else.
    if get_settings().benchmark_mode:
        return
    await _scan_limiter(request)


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
    _: None = Depends(_scan_rate_limit)
) -> ScanResponse:
    # `payload.student_number` is checked against the authenticated account
    # rather than used to select the student: any student could otherwise
    # submit - or replay an idempotency key for - somebody else's scan.
    return await service.submit_scan(
        payload=payload,
        user_id=user.id,
        idempotency_key=idempotency_key,
    )


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
    return await service.precheck_scan(
        session_id=payload.session_id,
        user_id=user.id,
        student_number=payload.student_number,
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
    semester: str | None = Query(default=None, max_length=SEMESTER_MAX_LENGTH),
    course_id: int | None = Query(default=None, gt=0),
    status: ValidationStatus | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    sort_by: str | None = Query(default=None, max_length=HISTORY_SORT_BY_MAX_LENGTH),
    sort_dir: str | None = Query(default=None, max_length=HISTORY_SORT_DIR_MAX_LENGTH),
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


@router.get(
    "/attendance/history/export",
    summary="Download the attendance history as CSV",
)
async def export_attendance_history(
    user: StudentUser,
    service: AttendanceServiceDep,
    program_id: int | None = Query(default=None, gt=0),
    year_level_id: int | None = Query(default=None, gt=0),
    semester: str | None = Query(default=None, max_length=SEMESTER_MAX_LENGTH),
    course_id: int | None = Query(default=None, gt=0),
    status: ValidationStatus | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    sort_by: str | None = Query(default=None, max_length=HISTORY_SORT_BY_MAX_LENGTH),
    sort_dir: str | None = Query(default=None, max_length=HISTORY_SORT_DIR_MAX_LENGTH),
) -> StreamingResponse:
    # Same filter set as `/attendance/history`, deliberately including no
    # page/size: the file carries every matching row.
    content: str = await service.export_history_csv(
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
    )

    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={HISTORY_EXPORT_FILENAME}"
        },
    )
