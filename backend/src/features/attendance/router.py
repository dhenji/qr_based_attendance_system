from typing import Annotated

from fastapi import APIRouter, Depends, Header

from api.deps import AttendanceServiceDep, require_role
from features.attendance.constants import (
    IDEMPOTENCY_KEY_MAX_LENGTH,
    SCAN_RATE_LIMIT_MAX_CALLS,
    SCAN_RATE_LIMIT_WINDOW_SECONDS,
)
from features.attendance.schema import ScanRequest, ScanResponse
from features.auth.model import User
from shared.enums import UserRole
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
