from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from api.deps import DashboardServiceDep, require_role
from features.auth.model import User
from features.dashboard.schema import AdminDashboardResponse
from shared.enums import UserRole

# Sibling of student_router.py and professor_router.py in this slice; see the
# module docstring in service.py for why the three dashboards are not owned by
# the features they aggregate.
#
# Prefix baked in below; mounted with no prefix= argument in api/router.py. This
# shares the /admin mount point with `system/router.py`, which owns
# `/admin/system/*`, `/admin/backups*` and `/admin/audit-logs`; `/dashboard` is
# unique among them. DO NOT mount this router twice.
router = APIRouter(prefix="/admin")

AdminUser = Annotated[User, Depends(require_role(UserRole.ADMIN))]


@router.get(
    "/dashboard",
    response_model=AdminDashboardResponse,
    summary="Roster sizes, today's scan volume, sync backlog and recent scans",
)
async def admin_dashboard(
    _: AdminUser,
    service: DashboardServiceDep,
) -> AdminDashboardResponse:
    return await service.admin_dashboard()