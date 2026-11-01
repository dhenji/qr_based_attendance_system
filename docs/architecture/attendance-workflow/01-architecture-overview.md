# 01 — Architecture Overview

## Layers and boundaries

The attendance workflow is split into six layers. Dependencies point inward:
presentation and integrations depend on application; application depends on
domain and data; domain and data depend on nothing above.

- **Presentation** — `frontend/src/routes/student/scan/+page.svelte`,
  `frontend/src/lib/features/liveness/*`, `frontend/src/lib/features/sync/*`,
  `frontend/src/lib/shared/utils/geo.ts`.
- **API/Controller** — `backend/src/features/attendance/router.py`,
  `backend/src/features/attendance/admin_router.py`,
  `backend/src/api/deps.py`, `backend/src/api/router.py`.
- **Application** — `backend/src/features/attendance/service.py`
  (`AttendanceService`), `backend/src/features/session/service.py`
  (`SessionService`).
- **Domain** — liveness grading `_validate_liveness_evidence`
  (`attendance/service.py:166`), geofence `_validate_geofence`
  (`attendance/service.py:591`), status `_compute_status`
  (`attendance/service.py:625`), score band `_is_review_band`
  (`attendance/service.py:616`), rates `shared/rates.py:36`.
- **Data** — `backend/src/features/attendance/model.py`,
  `backend/src/features/session/model.py`, SQLAlchemy queries in services.
- **Integrations** — `shared/face_embedding_generator.py`,
  `shared/face_quality.py`, `shared/email.py`, `analytics/batch.py`,
  `core/scheduler.py`.

## Dependency direction

- Routers never touch the DB; they depend on `AttendanceServiceDep`
  (`api/deps.py`).
- Services only `flush()`; commit/rollback is owned by `_get_db`
  (`api/deps.py`).
- Domain helpers are pure functions or methods on the service with no I/O.
- `shared/rates.py::attendance_rates` is the single rate definition; do not
  re-derive per feature (D79/D27).

## Cross-cutting rules

- Student identity resolves from the authenticated user (`Student.user_id`);
  `student_number` is comparison-only → 403 `student_number_mismatch`
  (  `attendance/service.py:517-550`, `attendance/exceptions.py:48`).
- No per-feature `_rates`; compliance counts `present` only
  (`shared/rates.py:45`).
- Review queue keys on `liveness_evidence["review"] == true`, not on
  `validation_status` (`attendance/service.py:283-285`).
- Status is derived (`scheduled`/`active`/`closed`), no status column
  (`session/service.py:148`).
