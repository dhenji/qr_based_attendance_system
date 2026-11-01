# 04 — Application and Service Layer

## AttendanceService scan pipeline

`backend/src/features/attendance/service.py::submit_scan`:

1. Idempotency cache check (`_cached_response`).
2. `_resolve_scan_parties`:
   - `_get_active_session` (active/expired/not-started checks).
   - `_get_active_student` (resolve by `user_id`, compare `student_number`).
   - `_require_enrollment`.
   - `_require_no_duplicate`.
3. `_require_face_enrollment` (face_embedding not null).
4. Generate embedding from `live_face_image` (MobileFaceNet) or
   `live_face_embedding`; cosine similarity vs enrolled.
5. Score vs `review_low` (0.65) → raise `FaceMismatchException` if below.
6. Unless benchmark mode: `_validate_geofence`, `_validate_liveness`.
7. `_decide_scan_outcome` (score bands + status).
8. `_persist_scan` (write row + sync queue if stale).

## FaceEnrollmentService

`backend/src/features/face_enrollment/service.py`:

- `enroll_face` validates 3 photos via `assess_image_bytes`, generates
  `FACEEMB1` embedding via `generate_embedding_from_images`, bumps version,
  records audit.
- `revoke_face_enrollment` clears blob, nulls enrolled_at, bumps version.
- Content type is not trusted; decoding verifies format.

## Review resolution

`resolve_review` loads pending review (evidence.review == true), approves
(restores computed present/late) or rejects, removes review flag, stores note
in evidence, writes audit row.
