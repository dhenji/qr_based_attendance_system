from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from shared.enums import RiskLevel
from shared.pagination import DEFAULT_PAGE, DEFAULT_PAGE_SIZE

TrendGranularity = Literal["daily", "weekly", "monthly"]


class OverviewResponse(BaseModel):
    total_students: int
    total_courses: int
    avg_compliance_rate: float
    avg_participation_rate: float
    total_sessions: int


class CourseComparisonItem(BaseModel):
    course_id: int
    course_code: str
    program_id: int
    year_level_id: int
    compliance_rate: float
    participation_rate: float
    total_sessions: int


class CourseComparisonResponse(BaseModel):
    items: list[CourseComparisonItem] = Field(default_factory=list)
    total: int = 0
    page: int = DEFAULT_PAGE
    size: int = DEFAULT_PAGE_SIZE


class CourseOption(BaseModel):
    course_id: int
    course_code: str
    course_name: str


class CourseOptionsResponse(BaseModel):
    """Courses with at least one offering in the selected scope (#279).

    Backs the analytics filter rail's course picker, so the options offered
    and the rows the reports can show come from the same scope predicate.
    """

    items: list[CourseOption] = Field(default_factory=list)
    total: int = 0


class TrendItem(BaseModel):
    date: date
    compliance_rate: float
    participation_rate: float
    total_sessions: int


class TrendResponse(BaseModel):
    items: list[TrendItem] = Field(default_factory=list)
    total: int = 0
    page: int = DEFAULT_PAGE
    size: int = DEFAULT_PAGE_SIZE


class AtRiskItem(BaseModel):
    student_id: int
    student_name: str
    program: str
    year_level: str
    offering_id: int
    course_code: str
    course_name: str
    absence_rate: float
    max_streak: int
    trend_slope: float
    risk_level: RiskLevel
    computed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AtRiskResponse(BaseModel):
    items: list[AtRiskItem] = Field(default_factory=list)
    total: int = 0
    page: int = DEFAULT_PAGE
    size: int = DEFAULT_PAGE_SIZE


class RefreshRiskResponse(BaseModel):
    processed: int
    high: int
    medium: int
    low: int
    duration_ms: int


class RiskStagingItem(BaseModel):
    student_id: int
    student_name: str
    program: str
    year_level: str
    offering_id: int
    course_code: str
    course_name: str
    absence_rate: float
    max_streak: int
    trend_slope: float
    risk_level: RiskLevel
    computed_at: datetime
    promoted_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class RiskStagingResponse(BaseModel):
    items: list[RiskStagingItem] = Field(default_factory=list)
    total: int = 0
    page: int = DEFAULT_PAGE
    size: int = DEFAULT_PAGE_SIZE


class PromoteStagingResponse(BaseModel):
    promoted: int
    skipped: int
    duration_ms: int


ExportFormat = Literal["csv", "pdf"]


class AnalyticsExportRequest(BaseModel):
    format: ExportFormat = "csv"
    program_id: int | None = None
    year_level_id: int | None = None
    semester: str | None = None
    course_ids: list[int] | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
