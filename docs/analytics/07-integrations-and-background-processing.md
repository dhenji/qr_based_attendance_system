# 07 — Integrations and Background Processing

## Nightly risk batch

- `core/scheduler.py` owns APScheduler; job body
  `analytics/batch.py::run_scheduled_risk_batch` (02:00, `RISK_BATCH_CRON`),
  commits its own transaction.
- `RISK_BATCH_WORKERS` shards scoring; `RISK_BATCH_CHUNK_SIZE` batches.
- `RISK_BATCH_DRY_RUN` writes staging instead of live scores.

## Staging and promote

- `risk-staging` lists dry-run rows; `risk-staging/promote` copies staged
  rows into live scores, scoped by student/offering/semester/program/year/
  course (ADR-085).

## CSV export

- `POST /admin/analytics/export` renders course comparison as CSV
  (`EXPORT_FILENAME = "analytics-course-comparison.csv"`).

## Email
Not used by analytics; see `shared/email.py` for the single delivery path.
