from __future__ import annotations

from fastapi import APIRouter, Query

from shared.pagination import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PaginatedResponse,
)

from api.deps import AdminUser, ExcuseServiceDep
from features.excuse.schema import ExcuseRequestRead

# This module owns /admin/excuses ONLY.
#
# The excuse feature spans THREE mount points, so it needs THREE routers:
#   excuse/professor_router.py  -> /professor  (per-session excuse actions + review queue)
#   excuse/student_router.py    -> /student    (own submit/list/detail)
#   excuse/admin_router.py      -> /admin/excuses (system-wide list, this module)
# Do not add admin routes to the other two — they would register under
# /api/professor/... or /api/student/... instead of /api/admin/excuses/...
router = APIRouter(prefix="/admin/excuses")


@router.get(
    "",
    response_model=PaginatedResponse[ExcuseRequestRead],
    summary="List excuse requests system-wide",
)
async def list_excuses(
    _: AdminUser,
    service: ExcuseServiceDep,
    status: str | None = Query(default=None),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PaginatedResponse[ExcuseRequestRead]:
    return await service.list_for_admin(
        status=status,
        page=page,
        size=size,
    )
