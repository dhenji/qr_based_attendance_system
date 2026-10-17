from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from features.analytics.schema import TrendGranularity
from shared.enums import ValidationStatus
from shared.pagination import DEFAULT_PAGE, DEFAULT_PAGE_SIZE

ReportMetric = Literal["compliance", "participation"]

ExportFormat = Literal["csv", "pdf"]

ExportInclude = Literal["student_id", "name", "timestamp", "gps", "liveness"]

DEFAULT_EXPORT_INCLUDE: list[ExportInclude] = [
    "student_id",
    "name",
    "timestamp",
    "gps",
    "liveness",
]


class AllCoursesItem(BaseModel):
    date: date
    total_sessions: int
    total_students: int
    compliance_rate: float
    participation_rate: float


class AllCoursesResponse(BaseModel):
    items: list[AllCoursesItem] = Field(default_factory=list)
    avg_compliance: float = 0.0
    avg_participation: float = 0.0


class ReportsComparisonItem(BaseModel):
    course_id: int
    course_code: str
    program_id: int
    year_level_id: int
    # Server-resolved cohort identity, so the client labels a row from the row
    # itself instead of guessing a cohort by course id (two cohorts of one
    # course share that id). Empty only for a dangling program/year reference.
    program_code: str = ""
    year_level_label: str = ""
    compliance_rate: float
    participation_rate: float
    total_sessions: int


class ReportsComparisonResponse(BaseModel):
    items: list[ReportsComparisonItem] = Field(default_factory=list)
    total: int = 0
    page: int = DEFAULT_PAGE
    size: int = DEFAULT_PAGE_SIZE


class ReportsTrendItem(BaseModel):
    date: date
    course_id: int
    course_code: str
    rate: float


class ReportsTrendResponse(BaseModel):
    items: list[ReportsTrendItem] = Field(default_factory=list)
    total: int = 0
    page: int = DEFAULT_PAGE
    size: int = DEFAULT_PAGE_SIZE


class ProfessorExportRequest(BaseModel):
    course_id: int | None = Field(default=None, gt=0)
    date_from: datetime | None = None
    date_to: datetime | None = None
    format: ExportFormat = "csv"
    include: list[ExportInclude] = Field(
        default_factory=lambda: list(DEFAULT_EXPORT_INCLUDE)
    )
    statuses: list[ValidationStatus] | None = None

    @model_validator(mode="after")
    def _check_range(self) -> ProfessorExportRequest:
        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_from > self.date_to
        ):
            raise ValueError("date_from must not be after date_to")

        return self


__all__ = [
    "AllCoursesItem",
    "AllCoursesResponse",
    "DEFAULT_EXPORT_INCLUDE",
    "ExportFormat",
    "ExportInclude",
    "ProfessorExportRequest",
    "ReportMetric",
    "ReportsComparisonItem",
    "ReportsComparisonResponse",
    "ReportsTrendItem",
    "ReportsTrendResponse",
    "TrendGranularity",
]
