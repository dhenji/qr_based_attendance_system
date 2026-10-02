from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.exceptions import RequestValidationError

from api.deps import ExcuseServiceDep, require_role
from features.auth.model import User
from features.excuse.schema import (
    BulkExcuseRequest,
    BulkExcuseResponse,
    EditExcuseRequest,
    ExcuseActionResponse,
    ExcuseRequestRead,
    ExcuseReviewRequest,
    ProfWithEvidenceRequest,
    QuickExcuseRequest,
    RevokeExcuseResponse,
)
from shared.enums import UserRole
from shared.pagination import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PaginatedResponse,
)

# Excuse professor routes under the shared /professor mount point.
# session/router.py owns /professor/courses, /professor/sessions/* and
# /professor/attendance; professor/router.py owns /professor/profile*.
# THIS module owns /professor/sessions/{session_id}/attendance/{student_id}/excuse,
# /professor/sessions/{session_id}/excuse-all-absent and
# /professor/excuse-requests*. Inner paths must not collide with the above.
#
# DO NOT change this prefix and DO NOT mount this router a second time.
router = APIRouter(prefix="/professor")

ProfessorUser = Annotated[User, Depends(require_role(UserRole.PROFESSOR))]


@router.post(
    "/sessions/{session_id}/attendance/{student_id}/excuse",
    response_model=ExcuseActionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Quick-excuse or excuse with evidence for one student",
)
async def excuse_student(
    session_id: int,
    student_id: int,
    request: Request,
    user: ProfessorUser,
    service: ExcuseServiceDep,
) -> ExcuseActionResponse:
    # One route covers both professor paths: a body carrying
    # `attachment_urls` is Path B (prof with evidence), otherwise Path A
    # (quick-excuse). The key is inspected by presence (not truthiness) so a
    # Path B payload with an empty list still validates as Path B and returns
    # a 422 instead of silently dropping its evidence intent. Malformed JSON
    # raises the standard FastAPI 422 list envelope (never a 500).
    try:
        body: Any = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        raise RequestValidationError(
            errors=[
                {
                    "loc": ("body",),
                    "msg": "Invalid JSON body",
                    "type": "value_error.jsondecode",
                }
            ]
        )

    if not isinstance(body, dict):
        raise RequestValidationError(
            errors=[
                {
                    "loc": ("body",),
                    "msg": "JSON body must be an object",
                    "type": "type_error.dict",
                }
            ]
        )

    if "attachment_urls" in body:
        payload_with_evidence = ProfWithEvidenceRequest.model_validate(body)
        return await service.excuse_with_evidence(
            user_id=user.id,
            student_id=student_id,
            session_id=session_id,
            payload=payload_with_evidence,
        )

    payload_quick = QuickExcuseRequest.model_validate(body)
    return await service.quick_excuse(
        user_id=user.id,
        student_id=student_id,
        session_id=session_id,
        payload=payload_quick,
    )


@router.patch(
    "/sessions/{session_id}/attendance/{student_id}/excuse",
    response_model=ExcuseRequestRead,
    summary="Update reason or notes on an existing excuse",
)
async def edit_student_excuse(
    session_id: int,
    student_id: int,
    payload: EditExcuseRequest,
    user: ProfessorUser,
    service: ExcuseServiceDep,
) -> ExcuseRequestRead:
    return await service.edit_excuse(
        user_id=user.id,
        student_id=student_id,
        session_id=session_id,
        reason=payload.reason,
        review_notes=payload.review_notes,
    )


@router.delete(
    "/sessions/{session_id}/attendance/{student_id}/excuse",
    response_model=RevokeExcuseResponse,
    summary="Revoke excuse and restore the prior status",
)
async def revoke_student_excuse(
    session_id: int,
    student_id: int,
    user: ProfessorUser,
    service: ExcuseServiceDep,
) -> RevokeExcuseResponse:
    return await service.revoke_excuse(
        user_id=user.id,
        student_id=student_id,
        session_id=session_id,
    )


@router.post(
    "/sessions/{session_id}/excuse-all-absent",
    response_model=BulkExcuseResponse,
    summary="Excuse all still-absent students in one session",
)
async def excuse_all_absent(
    session_id: int,
    payload: BulkExcuseRequest,
    user: ProfessorUser,
    service: ExcuseServiceDep,
) -> BulkExcuseResponse:
    return await service.bulk_excuse_all_absent(
        user_id=user.id,
        session_id=session_id,
        payload=payload,
    )


@router.get(
    "/excuse-requests",
    response_model=PaginatedResponse[ExcuseRequestRead],
    summary="List excuse requests across the professor's sessions",
)
async def list_excuse_requests(
    user: ProfessorUser,
    service: ExcuseServiceDep,
    status: str | None = Query(default=None),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PaginatedResponse[ExcuseRequestRead]:
    return await service.list_for_professor(
        user_id=user.id,
        status=status,
        page=page,
        size=size,
    )


@router.post(
    "/excuse-requests/{rid}/review",
    response_model=ExcuseRequestRead,
    summary="Approve or reject a pending student excuse request",
)
async def review_excuse_request(
    rid: int,
    payload: ExcuseReviewRequest,
    user: ProfessorUser,
    service: ExcuseServiceDep,
) -> ExcuseRequestRead:
    return await service.review_excuse(
        user_id=user.id,
        request_id=rid,
        payload=payload,
    )
