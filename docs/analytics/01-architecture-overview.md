# 01 — Architecture Overview

## Layers and boundaries

- **Presentation** — `frontend/src/routes/admin/analytics/+page.svelte`,
  `frontend/src/lib/features/admin/analytics/*`.
- **API/Controller** — `backend/src/features/analytics/router.py` (prefix
  `/admin/analytics`), `backend/src/api/deps.py`, `backend/src/api/router.py`.
- **Application** — `backend/src/features/analytics/service.py`
  (`AnalyticsService`), `backend/src/features/analytics/batch.py`.
- **Domain** — `shared/rates.py::attendance_rates`, `shared/cohorts.py`,
  risk feature computation + heuristic decision table in
  `analytics/batch.py`/`service.py`, trend bucketing `_bucket_key`
  (`analytics/service.py:56`).
- **Data** — `features/analytics/model.py`, plus attendance/session/course/
  enrollment/program models.
- **Integrations** — `core/scheduler.py`, cron risk batch, staging/promote,
  CSV export.

## Dependency direction

- Router depends on `AnalyticsServiceDep`; services only `flush()`.
- All analytics reads derive scope from `_offerings_stmt`
  (`analytics/service.py:68`); course options use the same predicate so the
  picker can never offer a course with no in-scope offering (ADR-085).
- Cohort key is `(course, program, year level)` via `shared/cohorts.py`;
  do not re-key per feature (ADR-084).
- Rates come from `shared/rates.py`; compliance counts `present` only.

## Cross-cutting rules

- Scope filters: program/year/semester/course_ids/session_type/date range.
- `course_ids` honored by overview/comparison/trends/at-risk/staging and
  promote (ADR-085).
- Risk batch runs 02:00 (`RISK_BATCH_CRON`); refresh-risk is synchronous and
  rate-limited 1/60s (`analytics/router.py:193`).
- Dry-run writes to `student_risk_scores_staging`; promote copies to live.
