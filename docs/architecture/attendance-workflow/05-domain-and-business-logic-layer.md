# 05 — Domain and Business Logic Layer

## Liveness grading

`_validate_liveness_evidence` (`attendance/service.py:166`): fixed
blink → left → right challenge (D31).

- `blink_detected && head_turn_left && head_turn_right` must all be true.
- `ear_samples` non-empty; mean in `[EAR_MEAN_MIN=0.05, EAR_MEAN_MAX=0.5]`
  (`constants.py:27-28`).
- `pnp_evidence` non-empty; if `peak_left_yaw` present must be ≤ -15; if
  `peak_right_yaw` present must be ≥ 15.
- `face_count == 1`.

Schema bounds: `EAR_SAMPLES_MIN_COUNT=1`, `EAR_SAMPLES_MAX_COUNT=100`,
  individual EAR in `[0,1]` (`attendance/constants.py:19-22`, `attendance/schema.py:45-58`).

## Geofence

`_validate_geofence` (`attendance/service.py:591`):

- Skip if `session.geofence_enabled` is false.
- Skip if `session.classroom_lat/lng` is None.
- If GPS is None → raise `OutsideGeofenceException` (missing fix treated as
  outside).
- Haversine distance > `classroom_radius_meters` + reported GPS uncertainty (capped at 50 m) → raise.
- Haversine distance in (radius, radius + uncertainty] → return `True` (ambiguous → admin review).

Benchmark mode skips geofence + liveness (`attendance/service.py:436-439`).

## Status anchor and windows

`_compute_status` (`attendance/service.py:625`): anchor =
`max(session.created_at, session.scheduled_start_time)`; elapsed minutes from
anchor.

- `elapsed ≤ present_window_minutes` → `present`
- `elapsed ≤ present + late` → `late`
- else → `rejected`

`Session.present_window_minutes + late_window_minutes ≤ duration_minutes`
(check constraint `ck_session_window_sum_lte_duration`).

## Score bands

`_is_review_band` (`attendance/service.py:616`): threshold 0.70
(`face_match_threshold`), review low 0.65 (`face_review_band_low`).

- `score < 0.65` → raise `FaceMismatchException`.
- `0.65 ≤ score < 0.70` → review band (status computed value stored as
  `validation_status`, original preserved in `original_status`, evidence
  `review=true`).
- `score ≥ 0.70` → no review.

## Rates

`shared/rates.py::attendance_rates(present, late, excused, enrolled)` →
`(compliance, participation)`, keyword-only, 4-decimal rounding,
`(0.0, 0.0)` for non-positive denominator. Compliance = present/enrolled;
participation = (present+late+excused)/enrolled.
