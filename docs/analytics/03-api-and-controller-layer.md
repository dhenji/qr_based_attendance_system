# 03 — API and Controller Layer

## Router

`backend/src/features/analytics/router.py` → prefix `/admin/analytics`, guarded
by `require_role(UserRole.ADMIN)` (admin + super_admin).

## Rate limit

- `refresh-risk`: `rate_limit(1, 60)` (`analytics/router.py:193`).

## Endpoint table

| Method | Path | Purpose |
|---|---|---|
| GET | `/admin/analytics/overview` | Totals + avg rates |
| GET | `/admin/analytics/course-comparison` | Cohort rates (paginated) |
| GET | `/admin/analytics/course-options` | Courses with in-scope offerings |
| GET | `/admin/analytics/trends` | Bucketed rates (daily/weekly/monthly) |
| GET | `/admin/analytics/at-risk` | Stored risk rows (paginated) |
| POST | `/admin/analytics/refresh-risk` | Synchronous recalculation |
| GET | `/admin/analytics/risk-staging` | Staged dry-run rows |
| POST | `/admin/analytics/risk-staging/promote` | Promote staged to live |
| POST | `/admin/analytics/export` | CSV course comparison |
