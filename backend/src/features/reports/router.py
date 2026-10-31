from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from api.deps import ProfessorServiceDep, ReportsServiceDep, require_role
from features.analytics.schema import TrendGranularity
from features.auth.model import User
from features.reports.schema import (
    AllCoursesResponse,
    ProfessorExportRequest,
    ReportMetric,
    ReportsComparisonResponse,
    ReportsTrendResponse,
)
from shared.constants import SEMESTER_MAX_LENGTH
from shared.enums import SessionType, UserRole
from shared.pagination import DEFAULT_PAGE, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

# Prefix baked in here; mounted without a prefix argument in api/router.py.
#
# This module shares the /professor mount point with `features/session/router.py`
# (which owns /professor/courses, /professor/sessions/* and
# /professor/attendance) and `features/professor/router.py` (which owns
# /professor/profile*). THIS module owns /professor/reports/* ONLY — inner
# paths must not collide with the above.
#
# DO NOT change this prefix and DO NOT mount this router a second time.
router = APIRouter(prefix="/professor")

ProfessorUser = Annotated[User, Depends(require_role(UserRole.PROFESSOR))]

REPORTS_EXPORT_FILENAME = "professor-attendance-export.csv"


@router.get(
    "/reports/all-courses",
    response_model=AllCoursesResponse,
    summary="Bucketed attendance across the professor's assigned courses",
)
async def reports_all_courses(
    user: ProfessorUser,
    service: ReportsServiceDep,
    professor_service: ProfessorServiceDep,
    granularity: TrendGranularity = Query(default="daily"),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    session_type: SessionType | None = Query(default=None),
) -> AllCoursesResponse:
    professor_id: int = await professor_service.resolve_professor_id(
        user_id=user.id
    )

    return await service.get_all_courses(
        professor_id=professor_id,
        granularity=granularity,
        date_from=date_from,
        date_to=date_to,
        session_type=session_type.value if session_type is not None else None,
    )


@router.get(
    "/reports/comparison",
    response_model=ReportsComparisonResponse,
    summary="Per-course rates across the professor's assigned courses",
)
async def reports_comparison(
    user: ProfessorUser,
    service: ReportsServiceDep,
    professor_service: ProfessorServiceDep,
    program_id: int | None = Query(default=None, gt=0),
    year_level_id: int | None = Query(default=None, gt=0),
    semester: str | None = Query(default=None, max_length=SEMESTER_MAX_LENGTH),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    session_type: SessionType | None = Query(default=None),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> ReportsComparisonResponse:
    professor_id: int = await professor_service.resolve_professor_id(
        user_id=user.id
    )

    return await service.get_comparison(
        professor_id=professor_id,
        program_id=program_id,
        year_level_id=year_level_id,
        semester=semester,
        date_from=date_from,
        date_to=date_to,
        session_type=session_type.value if session_type is not None else None,
        page=page,
        size=size,
    )


@router.get(
    "/reports/trends",
    response_model=ReportsTrendResponse,
    summary="Per-course rate series across the professor's assigned courses",
)
async def reports_trends(
    user: ProfessorUser,
    service: ReportsServiceDep,
    professor_service: ProfessorServiceDep,
    course_ids: list[int] | None = Query(default=None),
    metric: ReportMetric = Query(default="compliance"),
    granularity: TrendGranularity = Query(default="daily"),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    session_type: SessionType | None = Query(default=None),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> ReportsTrendResponse:
    professor_id: int = await professor_service.resolve_professor_id(
        user_id=user.id
    )

    return await service.get_trends(
        professor_id=professor_id,
        course_ids=course_ids,
        metric=metric,
        granularity=granularity,
        date_from=date_from,
        date_to=date_to,
        session_type=session_type.value if session_type is not None else None,
        page=page,
        size=size,
    )


@router.post(
    "/reports/export",
    summary="Download attendance rows for the professor's courses as CSV",
)
async def export_professor_reports(
    payload: ProfessorExportRequest,
    user: ProfessorUser,
    service: ReportsServiceDep,
    professor_service: ProfessorServiceDep,
) -> StreamingResponse:
    professor_id: int = await professor_service.resolve_professor_id(
        user_id=user.id
    )
    content: str = await service.export_attendance(
        professor_id=professor_id,
        course_id=payload.course_id,
        date_from=payload.date_from,
        date_to=payload.date_to,
        format=payload.format,
        include=payload.include,
        statuses=payload.statuses,
        session_type=payload.session_type,
    )

    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={REPORTS_EXPORT_FILENAME}"
        },
    )
