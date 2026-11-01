# 09 — Dependencies and Data Flow

## Dependency graph (simplified)

```
admin analytics page ──► analytics/service.ts ──► /admin/analytics/*
                                                    │
                                                    ▼
                                           analytics/router.py
                                                    │
                                                    ▼
                                           AnalyticsService
                                             ├─ _offerings_stmt (course/model)
                                             ├─ _scoped_sessions (session/model)
                                             ├─ _enrollments_by_offering (enrollment/model)
                                             ├─ _tallies_for_sessions (attendance/model)
                                             ├─ attendance_rates (shared/rates)
                                             ├─ group_by_cohort (shared/cohorts)
                                             ├─ run_risk_batch (analytics/batch)
                                             └─ StudentRiskScore / Staging (analytics/model)
```

## Transformations

- Scope filters → offering ids → sessions → enrollments → attendance tallies →
  rates (compliance/participation).
- Trends bucket by `_bucket_key` on `created_at`/`timestamp`.
- Risk features → heuristic decision table → risk level + synthetic probability.

## Error paths

- 422 `validation_error` (semester required with offering_id on refresh).
- 403 admin guard (`require_role(UserRole.ADMIN)`).
- 429 rate limit on refresh-risk (1/60s).
- Empty scope returns empty items, not errors.
