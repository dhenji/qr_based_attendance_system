# 01 — Architecture Overview

## Layers and boundaries

- **Presentation** — `frontend/src/routes/student/scan/+page.svelte`,
  `frontend/src/lib/features/liveness/*`, `frontend/src/lib/features/sync/*`,
  `frontend/src/lib/shared/utils/geo.ts`.
- **API/Controller** — `backend/src/features/attendance/router.py` (prefix
  `/student`), `backend/src/features/attendance/admin_router.py` (prefix
  `/admin/attendance`), `backend/src/api/deps.py`.
- **Application** — `backend/src/features/attendance/service.py`
  (`AttendanceService`), `backend/src/features/face_enrollment/service.py`
  (`FaceEnrollmentService`).
- **Domain** — liveness grading `_validate_liveness_evidence`
  (`attendance/service.py:166`), geofence `_validate_geofence`
  (`attendance/service.py:591`), score band `_is_review_band`
  (`attendance/service.py:616`), status `_compute_status`
  (`attendance/service.py:625`), identity `_get_active_student`
  (`attendance/service.py:517`), idempotency (`attendance/service.py:212-254`).
- **Data** — `features/attendance/model.py`, `features/session/model.py`,
  `features/student/model.py`.
- **Integrations** — `shared/face_quality.py`, `shared/face_embeddings.py`,
  `shared/face_embedding_generator.py`, `core/config.py`, `shared/audit.py`.

## Dependency direction

- Routers depend on service deps; services only `flush()`.
- Face enrollment quality gates run server-side via
  `shared/face_quality.py::assess_image_bytes`; content type is not trusted
  (`face_enrollment/service.py:41`).
- Embedding generation runs server-side via
  `shared/face_embedding_generator.py::generate_embedding_from_image`.
- Benchmark mode skips geofence + liveness only (`attendance/service.py:436`).

## Cross-cutting rules

- Student identity resolves from the authenticated user; `student_number` is
  comparison-only → 403 `student_number_mismatch`
  (`attendance/service.py:517-550`).
- Review queue keys on `liveness_evidence["review"] == true`, not
  `validation_status` (`attendance/service.py:283-285`).
- Review-band records keep computed status in `validation_status` and original
  in `original_status` (`attendance/service.py:340-346`).
- Idempotency key scoped `user_id:session_id:key`, TTL 900 s, process-local
  (`attendance/service.py:114-254`, `constants.py:30-35`).
- Geofence is skipped when disabled or classroom coords are missing; missing
  GPS is treated as outside (`attendance/service.py:591-611`).
