# 06 — Data Access and Persistence Layer

## Models

- `features/analytics/model.py::StudentRiskScore` → `student_risk_scores`
  (student_id, offering_id, semester, risk_probability, risk_level, features
  JSONB, computed_at, computed_day). UNIQUE(student_id, offering_id, semester,
  computed_day).
- `features/analytics/model.py::StudentRiskScoreStaging` →
  `student_risk_scores_staging` (same shape + promoted_at).
- Reads join `Student`, `Program`, `YearLevel`, `CourseOffering`, `Course`,
  `Enrollment`, `Session`, `Attendance`.

## Queries

- Overview/course comparison: offerings via `_offerings_stmt`, sessions via
  `_scoped_sessions`, enrollments via `_enrollments_by_offering`, tallies via
  `_tallies_for_sessions`.
- At-risk: joins risk score → student → year level → program → offering →
  course, filtered by scope, ordered by probability desc
  (`analytics/service.py:551`).
- Staging: same shape as at-risk, plus `promoted_at` filter.

## SQLite shims
Same as attendance: JSONB→JSON, BigInteger→INTEGER, aware-UTC DateTime,
`PRAGMA foreign_keys=ON`.
