from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from api.deps import SessionServiceDep, StudentServiceDep, require_role
from features.auth.model import User
from features.session.schema import VerifyCodeRequest, VerifyCodeResponse
from features.student.schema import FaceEmbeddingResponse, ScheduleResponse
from shared.enums import UserRole

# ALREADY MOUNTED at /api/student (see api/router.py). Student-facing routes
# only: profile, schedule, attendance scan/history, excuse requests, face status.
#
# DO NOT change this prefix and DO NOT mount this router a second time.
# Admin student CRUD (/admin/students) belongs to a SEPARATE module,
# `student/admin_router.py` with `APIRouter(prefix="/admin/students")`. Routes
# inside a router are relative to its own prefix, so mounting THIS router under
# /api/admin would also expose /api/admin/profile, /api/admin/schedule and
# /api/admin/attendance, none of which the contract defines. One APIRouter per
# (feature, mount point).
#
# This module shares the /student mount point with `features/attendance/router.py`
# (which owns /student/attendance/*). Inner paths must not collide: session
# verification lives here, scan/history live there.
router = APIRouter(prefix="/student")

StudentUser = Annotated[User, Depends(require_role(UserRole.STUDENT))]


@router.post(
    "/sessions/verify-code",
    response_model=VerifyCodeResponse,
    summary="Verify a typed session code or scanned session QR",
)
async def verify_session_code(
    payload: VerifyCodeRequest,
    user: StudentUser,
    service: SessionServiceDep,
) -> VerifyCodeResponse:
    _ = user  # role gate only; no student scoping needed for verify
    return await service.verify_code(code=payload.code)


@router.get(
    "/me/face-embedding",
    response_model=FaceEmbeddingResponse,
    responses={204: {"description": "Embedding current, no update needed"}},
    summary="Pull face embedding if client copy is stale",
)
async def pull_face_embedding(
    user: StudentUser,
    service: StudentServiceDep,
    current_version: int = Query(default=0, ge=0),
) -> FaceEmbeddingResponse | Response:
    result: FaceEmbeddingResponse | None = await service.get_face_embedding(
        user_id=user.id, current_version=current_version
    )

    if result is None:
        return Response(status_code=204)

    return result


@router.get(
    "/schedule",
    response_model=ScheduleResponse,
    summary="Student class schedule from enrolled offerings",
)
async def student_schedule(
    user: StudentUser, service: StudentServiceDep
) -> ScheduleResponse:
    return await service.get_schedule(user_id=user.id)
