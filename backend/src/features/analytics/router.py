from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from api.deps import AnalyticsServiceDep, require_role
from features.analytics.schema import (
    AnalyticsExportRequest,
    AtRiskResponse,
    CourseComparisonResponse,
    CourseOptionsResponse,
    OverviewResponse,
    PromoteStagingResponse,
    RefreshRiskResponse,
    RiskStagingResponse,
    TrendGranularity,
    TrendResponse,
)
from features.auth.model import User
from shared.constants import SEMESTER_MAX_LENGTH
from shared.enums import RiskLevel, SessionType, UserRole
from shared.pagination import DEFAULT_PAGE, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from shared.rate_limit import rate_limit

# Prefix baked in here; mounted without a prefix argument in api/router.py.
# This module owns /admin/analytics ONLY.
router = APIRouter(prefix="/admin/analytics")

AdminUser = Annotated[User, Depends(require_role(UserRole.ADMIN))]

EXPORT_FILENAME = "analytics-course-comparison.csv"

# Course search needle for the filter-rail picker; a course code or name is
# far shorter than this, so it only bounds abusive input.
COURSE_SEARCH_MAX_LENGTH = 100


@router.get(
    "/overview",
    response_model=OverviewResponse,
    summary="Institution-wide attendance totals and average rates",
)
async def get_overview(
    _: AdminUser,
    service: AnalyticsServiceDep,
    program_id: int | None = Query(default=None, gt=0),
    year_level_id: int | None = Query(default=None, gt=0),
    semester: str | None = Query(default=None, max_length=SEMESTER_MAX_LENGTH),
    course_ids: list[int] | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    session_type: SessionType | None = Query(default=None),
) -> OverviewResponse:
    return await service.get_overview(
        program_id=program_id,
        year_level_id=year_level_id,
        semester=semester,
        course_ids=course_ids,
        date_from=date_from,
        date_to=date_to,
        session_type=session_type.value if session_type is not None else None,
    )


@router.get(
    "/course-comparison",
    response_model=CourseComparisonResponse,
    summary="Per-course compliance and participation rates",
)
async def get_course_comparison(
    _: AdminUser,
    service: AnalyticsServiceDep,
    program_id: int | None = Query(default=None, gt=0),
    year_level_id: int | None = Query(default=None, gt=0),
    semester: str | None = Query(default=None, max_length=SEMESTER_MAX_LENGTH),
    course_ids: list[int] | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    session_type: SessionType | None = Query(default=None),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> CourseComparisonResponse:
    return await service.get_course_comparison(
        program_id=program_id,
        year_level_id=year_level_id,
        semester=semester,
        course_ids=course_ids,
        date_from=date_from,
        date_to=date_to,
        session_type=session_type.value if session_type is not None else None,
        page=page,
        size=size,
    )


@router.get(
    "/course-options",
    response_model=CourseOptionsResponse,
    summary="Courses with at least one offering in the selected scope",
)
async def get_course_options(
    _: AdminUser,
    service: AnalyticsServiceDep,
    program_id: int | None = Query(default=None, gt=0),
    year_level_id: int | None = Query(default=None, gt=0),
    semester: str | None = Query(default=None, max_length=SEMESTER_MAX_LENGTH),
    q: str | None = Query(default=None, max_length=COURSE_SEARCH_MAX_LENGTH),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> CourseOptionsResponse:
    return await service.list_course_options(
        program_id=program_id,
        year_level_id=year_level_id,
        semester=semester,
        query=q,
        limit=limit,
    )


@router.get(
    "/trends",
    response_model=TrendResponse,
    summary="Attendance rates bucketed by day, week, or month",
)
async def get_trends(
    _: AdminUser,
    service: AnalyticsServiceDep,
    program_id: int | None = Query(default=None, gt=0),
    year_level_id: int | None = Query(default=None, gt=0),
    semester: str | None = Query(default=None, max_length=SEMESTER_MAX_LENGTH),
    course_ids: list[int] | None = Query(default=None),
    granularity: TrendGranularity = Query(default="daily"),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    session_type: SessionType | None = Query(default=None),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> TrendResponse:
    return await service.get_trends(
        program_id=program_id,
        year_level_id=year_level_id,
        semester=semester,
        course_ids=course_ids,
        granularity=granularity,
        date_from=date_from,
        date_to=date_to,
        session_type=session_type.value if session_type is not None else None,
        page=page,
        size=size,
    )


@router.get(
    "/at-risk",
    response_model=AtRiskResponse,
    summary="Students flagged by the risk batch, highest probability first",
)
async def get_at_risk(
    _: AdminUser,
    service: AnalyticsServiceDep,
    program_id: int | None = Query(default=None, gt=0),
    year_level_id: int | None = Query(default=None, gt=0),
    semester: str | None = Query(default=None, max_length=SEMESTER_MAX_LENGTH),
    course_ids: list[int] | None = Query(default=None),
    risk_level: RiskLevel | None = Query(default=None),
    q: str | None = Query(default=None, max_length=100),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> AtRiskResponse:
    return await service.get_at_risk(
        program_id=program_id,
        year_level_id=year_level_id,
        semester=semester,
        course_ids=course_ids,
        risk_level=risk_level,
        q=q,
        page=page,
        size=size,
    )


@router.post(
    "/refresh-risk",
    response_model=RefreshRiskResponse,
    summary="Synchronously recalculate risk scores for a scope",
)
async def refresh_risk(
    _: AdminUser,
    service: AnalyticsServiceDep,
    student_id: int | None = Query(default=None, gt=0),
    offering_id: int | None = Query(default=None, gt=0),
    semester: str | None = Query(default=None, max_length=SEMESTER_MAX_LENGTH),
    _rate_limited: None = Depends(rate_limit(1, 60)),
) -> RefreshRiskResponse:
    return await service.refresh_risk(
        student_id=student_id,
        offering_id=offering_id,
        semester=semester,
    )


@router.get(
    "/risk-staging",
    response_model=RiskStagingResponse,
    summary="Review staged dry-run risk scores before promoting",
)
async def get_risk_staging(
    _: AdminUser,
    service: AnalyticsServiceDep,
    program_id: int | None = Query(default=None, gt=0),
    year_level_id: int | None = Query(default=None, gt=0),
    semester: str | None = Query(default=None, max_length=SEMESTER_MAX_LENGTH),
    course_ids: list[int] | None = Query(default=None),
    risk_level: RiskLevel | None = Query(default=None),
    q: str | None = Query(default=None, max_length=100),
    unpromoted_only: bool = Query(default=False),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> RiskStagingResponse:
    return await service.list_staged(
        program_id=program_id,
        year_level_id=year_level_id,
        semester=semester,
        course_ids=course_ids,
        risk_level=risk_level,
        q=q,
        unpromoted_only=unpromoted_only,
        page=page,
        size=size,
    )


@router.post(
    "/risk-staging/promote",
    response_model=PromoteStagingResponse,
    summary="Copy staged dry-run scores into live risk scores",
)
async def promote_risk_staging(
    _: AdminUser,
    service: AnalyticsServiceDep,
    student_id: int | None = Query(default=None, gt=0),
    offering_id: int | None = Query(default=None, gt=0),
    semester: str | None = Query(default=None, max_length=SEMESTER_MAX_LENGTH),
    program_id: int | None = Query(default=None, gt=0),
    year_level_id: int | None = Query(default=None, gt=0),
    course_ids: list[int] | None = Query(default=None),
) -> PromoteStagingResponse:
    return await service.promote_staged(
        student_id=student_id,
        offering_id=offering_id,
        semester=semester,
        program_id=program_id,
        year_level_id=year_level_id,
        course_ids=course_ids,
    )


@router.post(
    "/export",
    summary="Download per-course analytics as a CSV file",
)
async def export_analytics(
    payload: AnalyticsExportRequest,
    _: AdminUser,
    service: AnalyticsServiceDep,
) -> StreamingResponse:
    content: str = await service.export_course_comparison(
        format=payload.format,
        program_id=payload.program_id,
        year_level_id=payload.year_level_id,
        semester=payload.semester,
        course_ids=payload.course_ids,
        date_from=payload.date_from,
        date_to=payload.date_to,
        session_type=payload.session_type,
    )

    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={EXPORT_FILENAME}"},
    )
