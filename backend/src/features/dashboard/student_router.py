from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from api.deps import DashboardServiceDep, require_role
from features.auth.model import User
from features.dashboard.schema import StudentDashboardResponse
from shared.enums import UserRole

# The student dashboard needs attendance *and* schedule, so it cannot live in
# either slice without one of them depending on the other. It therefore gets its
# own router here (see the module docstring in service.py).
#
# Prefix baked in below; mounted with no prefix= argument in api/router.py. This
# shares the /student mount point with `student/router.py` and
# `attendance/router.py` — `/dashboard` is unique among them, so inner paths do
# not collide. DO NOT mount this router a second time.
router = APIRouter(prefix="/student")

StudentUser = Annotated[User, Depends(require_role(UserRole.STUDENT))]


@router.get(
    "/dashboard",
    response_model=StudentDashboardResponse,
    summary="Compliance, today's classes and recent scans for the student",
)
async def student_dashboard(
    user: StudentUser,
    service: DashboardServiceDep,
) -> StudentDashboardResponse:
    # Identity comes from the token; there is no student parameter to spoof.
    return await service.student_dashboard(user_id=user.id)