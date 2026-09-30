from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from api.deps import AuthServiceDep, ProfessorServiceDep, require_role
from features.auth.model import User
from features.auth.schema import ChangePasswordRequest
from features.professor.schema import MessageResponse, ProfessorProfileRead
from shared.enums import UserRole

# ALREADY MOUNTED at /api/professor (see api/router.py). Professor-facing
# self-service routes only: profile (+ password change).
#
# NOTE: `features/session/router.py` shares this same /professor mount point —
# several routers may share a prefix, but their inner paths must not collide:
# session owns /professor/courses, /professor/sessions/* and
# /professor/attendance; THIS module owns /professor/profile*.
#
# DO NOT change this prefix and DO NOT mount this router a second time.
# Admin professor CRUD (/admin/professors) belongs to a SEPARATE module,
# `professor/admin_router.py` with `APIRouter(prefix="/admin/professors")`.
# Mounting THIS router under /api/admin would also expose /api/admin/profile,
# which the contract does not define there.
router = APIRouter(prefix="/professor")

ProfessorUser = Annotated[User, Depends(require_role(UserRole.PROFESSOR))]


@router.get(
    "/profile",
    response_model=ProfessorProfileRead,
    summary="Read-only self profile",
)
async def get_profile(
    user: ProfessorUser,
    service: ProfessorServiceDep,
) -> ProfessorProfileRead:
    return await service.get_self_profile(user_id=user.id)


@router.patch(
    "/profile/password",
    response_model=MessageResponse,
    summary="Change own password",
)
async def update_profile_password(
    payload: ChangePasswordRequest,
    user: ProfessorUser,
    auth_service: AuthServiceDep,
) -> MessageResponse:
    await auth_service.change_password(
        user, payload.current_password, payload.new_password
    )

    return MessageResponse(message="Password updated")
