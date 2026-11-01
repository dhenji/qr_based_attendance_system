# 05 — Domain and Business Logic Layer

## Liveness grading

`_validate_liveness_evidence` (`attendance/service.py:166`): fixed
blink → left → right challenge (D31).

- All three booleans must be true.
- `ear_samples` non-empty; mean in `[0.05, 0.5]`.
- `pnp_evidence` non-empty; `peak_left_yaw ≤ -15`, `peak_right_yaw ≥ 15`
  when present.
- `face_count == 1`.

## Face quality gates

`shared/face_quality.py::assess_image_bytes`: decode, detection, single face,
brightness `[40,220]`, face size ≥ 15%, centering ≤ 30%, sharpness ≥ 50,
EAR > 0.2. Used by enrollment.

## Face match score bands

`_is_review_band` (`attendance/service.py:616`): threshold 0.70, review low
0.65.

- `< 0.65` → `FaceMismatchException` (403).
- `0.65–0.70` → review band (evidence.review = true).
- `≥ 0.70` → pass.

## Geofence

`_validate_geofence` (`attendance/service.py:591`):

- Skip if `geofence_enabled` false or classroom coords missing.
- Missing GPS → raise `OutsideGeofenceException`.
- Haversine distance > radius → raise.

## Identity comparison

`_get_active_student` (`attendance/service.py:517`): resolve student by
`Student.user_id`; compare `student_number` case-insensitively; inactive
student → not enrolled.

## Idempotency and staleness

- Key scoped `user_id:session_id:key`, TTL 900 s, process-local.
- `_maybe_record_sync` queues sync row only when
  `(now - scanned_at) > 60 s` (`SYNC_STALE_SECONDS`).
- Replay passes `allow_expired=True`.
