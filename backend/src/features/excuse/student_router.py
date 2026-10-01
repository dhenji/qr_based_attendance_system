from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from api.deps import ExcuseServiceDep, require_role
from features.auth.model import User
from features.excuse.schema import (
    ExcuseRequestRead,
    StudentExcuseRequest,
    StudentSubmitResponse,
)
from shared.enums import UserRole
from shared.pagination import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PaginatedResponse,
)

# Excuse student routes under the shared /student mount point.
# student/router.py owns /student/sessions/verify-code, /student/schedule,
# /student/profile* and /student/me/face-embedding; attendance/router.py owns
# /student/attendance/*. THIS module owns /student/excuse-requests*.
# Inner paths must not collide with the above.
#
# DO NOT change this prefix and DO NOT mount this router a second time.
router = APIRouter(prefix="/student")

StudentUser = Annotated[User, Depends(require_role(UserRole.STUDENT))]


@router.post(
    "/excuse-requests",
    response_model=StudentSubmitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit an excuse request with evidence",
)
async def submit_excuse_request(
    payload: StudentExcuseRequest,
    user: StudentUser,
    service: ExcuseServiceDep,
) -> StudentSubmitResponse:
    # The student is resolved from the bearer token inside the service,
    # never from a body-supplied identifier.
    return await service.submit_student_excuse(
        user_id=user.id,
        payload=payload,
    )


@router.get(
    "/excuse-requests",
    response_model=PaginatedResponse[ExcuseRequestRead],
    summary="List the caller's own excuse requests",
)
async def list_own_excuse_requests(
    user: StudentUser,
    service: ExcuseServiceDep,
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PaginatedResponse[ExcuseRequestRead]:
    return await service.list_for_student(
        user_id=user.id,
        page=page,
        size=size,
    )


@router.get(
    "/excuse-requests/{rid}",
    response_model=ExcuseRequestRead,
    summary="Read one of the caller's own excuse requests",
)
async def get_own_excuse_request(
    rid: int,
    user: StudentUser,
    service: ExcuseServiceDep,
) -> ExcuseRequestRead:
    return await service.get_for_student(
        user_id=user.id,
        request_id=rid,
    )
