from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from shared.enums import UserRole

from api.deps import DashboardServiceDep, ProfessorServiceDep, require_role
from features.auth.model import User
from features.dashboard.schema import ProfessorDashboardResponse

# Sibling of student_router.py and admin_router.py in this slice; see the module
# docstring in service.py for why the three dashboards are not owned by the
# features they aggregate.
#
# Prefix baked in below; mounted with no prefix= argument in api/router.py. This
# shares the /professor mount point with `professor/router.py` and
# `session/router.py`; `/dashboard` is unique among them. DO NOT mount twice.
router = APIRouter(prefix="/professor")

ProfessorUser = Annotated[User, Depends(require_role(UserRole.PROFESSOR))]


@router.get(
    "/dashboard",
    response_model=ProfessorDashboardResponse,
    summary="Today's sessions plus the term attendance rate",
)
async def professor_dashboard(
    user: ProfessorUser,
    service: DashboardServiceDep,
    professor_service: ProfessorServiceDep,
) -> ProfessorDashboardResponse:
    # Two service deps is the reports/router.py:47 pattern: resolve the claimed
    # professor row with one service, aggregate with the other.
    professor_id: int = await professor_service.resolve_professor_id(user_id=user.id)
    return await service.professor_dashboard(professor_id=professor_id)
