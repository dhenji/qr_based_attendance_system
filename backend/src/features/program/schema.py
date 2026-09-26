from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from features.admin.constants import NAME_MAX_LENGTH, NAME_MIN_LENGTH
from features.program.constants import (
    CODE_MAX_LENGTH,
    CODE_MIN_LENGTH,
    DESCRIPTION_MAX_LENGTH,
    TOTAL_YEARS_MAX,
    TOTAL_YEARS_MIN,
)


class ProgramCreate(BaseModel):
    code: str = Field(min_length=CODE_MIN_LENGTH, max_length=CODE_MAX_LENGTH)
    name: str = Field(min_length=NAME_MIN_LENGTH, max_length=NAME_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    total_years: int = Field(ge=TOTAL_YEARS_MIN, le=TOTAL_YEARS_MAX)

    @field_validator("code")
    @classmethod
    def _normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class ProgramRead(BaseModel):
    id: int
    code: str
    name: str
    description: str | None = None
    total_years: int
    is_active: bool
    course_count: int = 0
    year_level_count: int = 0
    terms_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProgramUpdate(BaseModel):
    name: str | None = Field(
        default=None, min_length=NAME_MIN_LENGTH, max_length=NAME_MAX_LENGTH
    )
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    is_active: bool | None = None

    @model_validator(mode="after")
    def _reject_null_on_not_nullable(self) -> "ProgramUpdate":
        for field in ("name", "is_active"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")

        return self


class Term(BaseModel):
    code: str
    label: str


class TermStructure(BaseModel):
    terms: list[Term] = Field(default_factory=list)


class YearLevelRead(BaseModel):
    id: int
    program_id: int
    year_number: int
    label: str
    term_structure: TermStructure
    sort_order: int

    model_config = ConfigDict(from_attributes=True)


class ProgramDetail(ProgramRead):
    year_levels: list[YearLevelRead] = Field(default_factory=list)
