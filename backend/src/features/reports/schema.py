from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from features.analytics.schema import TrendGranularity
from shared.pagination import DEFAULT_PAGE, DEFAULT_PAGE_SIZE

ReportMetric = Literal["compliance", "participation"]


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


__all__ = [
    "AllCoursesItem",
    "AllCoursesResponse",
    "ReportMetric",
    "ReportsComparisonItem",
    "ReportsComparisonResponse",
    "ReportsTrendItem",
    "ReportsTrendResponse",
    "TrendGranularity",
]
