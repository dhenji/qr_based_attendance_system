# 04 — Application and Service Layer

## AnalyticsService

`backend/src/features/analytics/service.py` (`AnalyticsService`). Methods:

- `get_overview(...)` — totals + avg compliance/participation rates.
- `get_course_comparison(...)` — one row per cohort (course × program × year
  level), paginated.
- `list_course_options(...)` — distinct courses with at least one in-scope
  offering.
- `get_trends(...)` — rates bucketed by day/week/month.
- `get_at_risk(...)` — stored risk rows, ordered by probability desc.
- `refresh_risk(...)` — synchronous scoped recalculation.
- `list_staged(...)` / `promote_staged(...)` — dry-run staging review/promote.
- `export_course_comparison(...)` — CSV.

## Batch orchestration

- `features/analytics/batch.py::run_risk_batch(session, targets)` computes
  features and upserts risk rows; used by both cron and refresh.
- Risk batch cron 02:00 (`RISK_BATCH_CRON`); workers sharded via
  `RISK_BATCH_WORKERS`.

## Transactions

Services only `flush()`; `_get_db` commits/rolls back.
