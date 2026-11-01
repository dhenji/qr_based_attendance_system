# 05 — Domain and Business Logic Layer

## Rates

`shared/rates.py::attendance_rates(present, late, excused, enrolled)` →
`(compliance, participation)`, keyword-only, 4-decimal rounding,
`(0.0, 0.0)` for non-positive denominator. Compliance = present/enrolled;
participation = (present+late+excused)/enrolled.

## Cohorts

`shared/cohorts.py::cohort_key(offering)` = `(course_id, program_id,
year_level_id)`. `group_by_cohort` groups offerings by cohort
(ADR-084). Semester and dates are filter axes, not identity.

## Risk features

Per `(student, offering, semester)` (see `docs/architecture/risk-model.md`):
expected sessions, absence rate, max consecutive streak, sync lag, 4-week trend
slope. Heuristic decision table (first match wins): absence_rate > 0.30 → high;
streak ≥ 3 → high; absence_rate > 0.15 → medium; sync_lag ≥ 5 → medium;
trend_slope < -0.05 → medium; else low.

## Trend bucketing

`_bucket_key` (`analytics/service.py:56`): daily → day; weekly → Monday (date
from ordinal minus weekday); monthly → first day of month.

## Course options

Derived from `_offerings_stmt` (`analytics/service.py:68`), so the picker only
offers courses with at least one in-scope offering (ADR-085).
