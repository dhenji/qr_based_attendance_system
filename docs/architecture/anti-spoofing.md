# Anti-Spoofing — Layered Controls

Code-grounded technical documentation for the anti-spoofing controls in the
attendance workflow. The codebase is the single source of truth; every claim cites
`path:line`.

## Scope

Covers biometric quality/enrollment/matching, liveness challenge, geofence/GPS,
student identity, replay/idempotency protection, review resolution,
benchmark-mode posture, and frontend controls. Does not cover auth/account security
(see `docs/architecture/security-model.md`) or scan storage (see
`docs/architecture/attendance-workflow/`).

This file consolidates the former layered docs 01–09 in order.

## Layer map

| Layer | Components | Key sources |
|---|---|---|
| Presentation | Face liveness UI, QR scan, GPS acquisition/location card, sync queue | `frontend/src/routes/student/scan/+page.svelte`, `frontend/src/lib/features/liveness/*`, `frontend/src/lib/features/sync/*`, `frontend/src/lib/shared/utils/geo.ts` |
| API/Controller | Scan/precheck/review endpoints, rate limit, error envelopes | `backend/src/features/attendance/router.py`, `backend/src/features/attendance/admin_router.py`, `backend/src/api/deps.py` |
| Application | AttendanceService scan pipeline, review resolution, FaceEnrollmentService | `backend/src/features/attendance/service.py`, `backend/src/features/face_enrollment/service.py` |
| Domain | Liveness grading, geofence, score bands, identity comparison, idempotency, staleness | `backend/src/features/attendance/service.py`, `backend/src/shared/face_quality.py` |
| Data | Attendance/session/student/enrollment models, review filter on evidence JSON | `backend/src/features/attendance/model.py`, `backend/src/features/session/model.py`, `backend/src/features/student/model.py` |
| Integrations | MediaPipe quality gates, MobileFaceNet embedding gen, benchmark mode, admin review audit | `backend/src/shared/face_quality.py`, `backend/src/shared/face_embedding_generator.py`, `backend/src/shared/face_embeddings.py`, `backend/src/core/config.py`, `backend/src/shared/audit.py` |

## Related docs

- `docs/architecture/security-model.md` — threat model and controls
- `docs/architecture/face-enrollment.md` — enrollment architecture
- `docs/architecture/data-flow.md` — system-wide flow diagrams
- `docs/architecture/offline-first.md` — offline storage and sync
- `docs/architecture/attendance-workflow/` — attendance scan flow and data layer
- `docs/project/decision-log.md` — D27, D31, D16, D17, ADR-083

Last verified against commit: see `git rev-parse HEAD`.

---

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
  GPS is treated as outside; a position outside the radius but within reported
  GPS uncertainty (capped at `GEOFENCE_UNCERTAINTY_CAP_METERS`, default 50 m) is
  treated as ambiguous and routed to review; GPS fixes with `accuracy = 0.0` are
  rejected at schema validation; the configured cap is exposed once via
  `VerifyGeofence.uncertainty_cap_meters` during session verification; the client
  pre-submit check uses `isWithinGeofenceWithUncertainty`
  (`attendance/service.py:591-620`). The same response also exposes
  `gps_hard_floor_meters` (default 1000 m) and
  `gps_review_accuracy_threshold` (default 100 m), so the client fail-fast and
  accuracy status/review messaging follow backend configuration.

---

# 02 — Presentation Layer

## Liveness UI

- `frontend/src/lib/features/liveness/components/FaceScanner.svelte` — blink +
  head-turn challenge; selfie-mirrored preview; 6-step progress indicator;
  status-tinted instruction hint.
- `frontend/src/lib/features/liveness/components/QRScanner.svelte` — session code
  scan (camera/upload).
- `frontend/src/lib/features/liveness/errors.ts` — `SCAN_ERROR_MESSAGES`,
  `toScanMessage()`.

## GPS flow

- `frontend/src/routes/student/scan/+page.svelte` runs a location check before
  face liveness: `requestBestPosition()` (fast low-accuracy fix first, then
  watchPosition up to 3 fixes, early stop at accuracy ≤ 50 m; abortable via
  `AbortSignal`); shows accuracy, distance, radius, within/outside.
- `frontend/src/lib/shared/utils/geo.ts` — `requestBestPosition`, `calculateDistanceMeters`,
  `getAccuracyStatus`, `isLowAccuracy`. Validates fixes (finite, positive accuracy,
  in-range, not stale), dedups in-flight promises, supports `maxAccuracy`.
- `frontend/src/lib/features/liveness/gps.ts` — `acquireGpsFix` derives
  `high`/`moderate`/`low` status from `VerifyGeofence.gps_review_accuracy_threshold`
  (default 100 m); the fast-first path defaults `fastMaximumAge` to 0.
- `Continue` disabled while locating or outside geofence; low accuracy still
  allows continuation.

## Sync queue

- `frontend/src/lib/features/sync/service.ts` — IndexedDB `attendance_queue`;
  enqueue, drain, backoff, rejected item handling.
- Backoff `min(30s * 2^retry_count, 30 min)`.

## Error display

- Backend codes map via `toScanMessage()`; network errors queue for sync.
- Rejected scan (`result.status === 'rejected'`) shows permitted-time-window
  copy, not raw backend messages.
- Pydantic 422 validation failures (e.g. GPS accuracy out of range, missing
  face frame, out-of-range ear samples) are now surfaced with their specific
  field detail, translated into student-friendly copy instead of a single
  generic message. GPS accuracy is clamped to the backend cap (100000 m) and
  the scan page refuses to submit when no face frame was captured.
- `.error` paragraphs styled as alert banners (`+page.svelte`).

---

# 03 — API and Controller Layer

## Endpoints

- `POST /student/attendance/scan` — submit scan (online or offline replay).
- `POST /student/attendance/precheck` — enrollment + duplicate check.
- `GET /admin/attendance/liveness-review` — flagged review queue.
- `PATCH /admin/attendance/liveness-review/{id}/resolve` — approve/reject.
- `GET/POST/DELETE /admin/face-enrollment/{student_id}` — enrollment status,
  enroll (multipart), revoke.

## Deps and auth

- `_get_db` commits on success / rolls back on exception.
- `require_role(UserRole.STUDENT)` / `UserRole.ADMIN`.
- Scan rate limit: 30 calls / 60 s per IP, lifted under `BENCHMARK_MODE`
  (`attendance/router.py:45-54`).

## Idempotency

- `X-Idempotency-Key` header, max 64 chars (`constants.py:30`).
- Key scoped `user_id:session_id:key`, TTL 900 s, process-local, max 10,000
  entries (`attendance/service.py:114-254`, `constants.py:32-35`).

## Error envelopes

Backend emits AppException dict, FastAPI 422 list, plain-string 401/403;
`client.ts` normalizes all three and retries on 401.

## Error codes

`outside_geofence`, `liveness_failed`, `face_mismatch`, `face_not_enrolled`,
`student_number_mismatch`, `duplicate_scan`, `not_enrolled`, `session_expired`,
`session_not_started`, `review_not_found`, `review_not_pending`.

---

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

---

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
- Uncertainty capped at `GEOFENCE_UNCERTAINTY_CAP_METERS` (default 50 m).
- Accuracy > 100 m → `accuracy_low` review reason (even inside radius).
- Accuracy > 1000 m → 422 `gps_accuracy_too_low`.

## Identity comparison

`_get_active_student` (`attendance/service.py:517`): resolve student by
`Student.user_id`; compare `student_number` case-insensitively; inactive
student → not enrolled.

## Idempotency and staleness

- Key scoped `user_id:session_id:key`, TTL 900 s, process-local.
- `_maybe_record_sync` queues sync row only when
  `(now - scanned_at) > 60 s` (`SYNC_STALE_SECONDS`).
- Replay passes `allow_expired=True`.

---

# 06 — Data Access and Persistence Layer

## Models

- `features/attendance/model.py::Attendance` → `attendance_records`
  (`validation_status`, `original_status`, `liveness_evidence` JSONB,
  `face_match_score` Numeric(5,4), `sync_status`, `scanned_via`).
- `features/session/model.py::Session` → `sessions` (`geofence_enabled`,
  `is_remote`, classroom coords, `expires_at`).
- `features/student/model.py::Student` → `students` (`face_embedding`
  LargeBinary, algorithm, version, enrolled_at).
- Review queue filter: `cast(liveness_evidence["review"], Boolean) == True`
  (`attendance/service.py:283`).

## Transactions

Services only `flush()`; `_get_db` commits/rolls back. Audit rows are
flush-only and roll back with the mutation.

## SQLite shims (tests)

JSONB→JSON, BigInteger→INTEGER, aware-UTC DateTime, `PRAGMA foreign_keys=ON`.

---

# 07 — Integrations and Background Processing

## MediaPipe quality gates

`shared/face_quality.py::assess_image_bytes` decodes bytes and runs detection,
single face, brightness, face size, centering, sharpness, eyes-open gates.
Thresholds: `BRIGHTNESS_MIN/MAX`, `FACE_SIZE_MIN_RATIO`,
`CENTERING_MAX_OFFSET`, `SHARPNESS_MIN_VARIANCE`, `EAR_MIN`.

## Face embedding generation

- `shared/face_embedding_generator.py::generate_embedding_from_image` —
  MobileFaceNet ONNX (512-d) with landmark fallback.
- `shared/face_embeddings.py` — `cosine_similarity`, `serialize_embedding`/
  `deserialize_embedding` (`FACEEMB1`, dims 128/512), `is_stub_embedding`.
- Enrollment uses `generate_embedding_from_images` (front/left/right).

## Benchmark mode

`BENCHMARK_MODE=true` skips geofence + liveness (`attendance/service.py:436`)
and the per-IP scan rate gate (`attendance/router.py:49-53`). Face enrollment
and face match still run.

## Admin review audit

`resolve_review` writes an audit row (`AuditAction.APPROVE/REJECT`,
`AuditEntity.ATTENDANCE_RECORD`) with old/new validation status and note
(`attendance/service.py:1241`).

## Email

Not used in scan anti-spoofing; `shared/email.py` is the single delivery path.

---

# 08 — End-to-End Workflow

## Online scan (anti-spoofing controls)

```mermaid
sequenceDiagram
    participant S as Student Client
    participant API as Server API
    participant DB as Database
    S->>API: POST /student/sessions/verify-code {code}
    S->>API: POST /student/attendance/precheck {session_id, student_number}
    API->>API: Resolve student by user_id; compare number (403 on mismatch)
    API->>DB: Check enrollment + duplicate
    S->>S: GPS check (requestBestPosition) + face liveness (MediaPipe)
    S->>API: POST /student/attendance/scan {session_id, student_number, gps, liveness_evidence, live_face_image, scanned_at}
    API->>API: idempotency → session active/expired → student resolve → enrollment → face enrollment → duplicate → score vs review_low → (unless benchmark) geofence → liveness → score band → status
    API->>DB: INSERT attendance_records (validation_status, original_status, liveness_evidence, face_match_score)
    API-->>S: 200 {id, status, scanned_at, expires_at}
```

## Review flow

Flagged rows (`evidence.review == true`) listed via
`/admin/attendance/liveness-review`. `evidence.review_reason` records why the
row was flagged (`face_review_band` and/or `geofence_uncertainty`), and
geofence-flagged rows carry an `evidence.geofence` context object
(distance/radius/accuracy/uncertainty/classroom coords). The admin page
confirms each decision in a dialog before issuing the PATCH. Resolve approve
restores computed present/late; reject marks rejected. Audit row written.

## Enrollment and revoke

Admin enrolls 3 photos (quality gates + embedding generation) or revokes
(clears blob, bumps version). Revocation invalidates cached device embeddings
via version bump.
```

---

# 09 — Dependencies and Data Flow

## Dependency graph (simplified)

```
scan page (Svelte)
  ├─ liveness/service.ts ──► /student/attendance/scan
  │                              │
  │                              ▼
  │                     attendance/router.py
  │                              │
  │                              ▼
  │                     AttendanceService.submit_scan
  │                       ├─ _get_active_session (session/model)
  │                       ├─ _get_active_student (student/model, identity compare)
  │                       ├─ _require_enrollment (enrollment/model)
  │                       ├─ _require_face_enrollment (student.face_embedding)
  │                       ├─ generate_embedding_from_image (face_embedding_generator)
  │                       ├─ cosine_similarity (shared/face_embeddings)
  │                       ├─ _validate_geofence / _validate_liveness
  │                       ├─ _decide_scan_outcome / _compute_status
  │                       ├─ _write_attendance (attendance/model)
  │                       └─ _maybe_record_sync (sync/model)
  └─ FaceEnrollmentService (admin) ──► assess_image_bytes + generate_embedding_from_images
```

## Transformations

- Client `live_face_image` (base64) → bytes → 512-d embedding (MobileFaceNet)
  → cosine similarity vs enrolled → `face_match_score` Decimal(5,4).
- Liveness evidence JSON stored verbatim in `liveness_evidence`.
- GPS accuracy preserved without rounding on client; server stores lat/lng.
- `scanned_at` preserved verbatim; status computed from
  `max(created_at, scheduled_start_time)`.

## Error paths

- 403 `student_number_mismatch`, `outside_geofence`, `liveness_failed`,
  `face_mismatch`, `face_not_enrolled`.
- 404 `student_not_found`, `session_not_found`, `review_not_found`.
- 409 `duplicate_scan`, `review_not_pending`.
- 422 `session_expired`, `session_not_started`.
- Client maps codes via `toScanMessage()`; network errors queue for sync.

---

# 10 — Result Calculation Methodology

## 10.1 Scan result pipeline

1. Check idempotency cache for `user_id:session_id:key`.
2. Resolve active session and active student.
3. Require enrollment and no duplicate scan.
4. Require face enrollment.
5. Generate the live embedding and calculate cosine similarity.
6. Reject scores below `face_review_band_low`.
7. Unless benchmark mode, validate geofence and liveness.
8. Decide status and review band.
9. Persist the attendance row and optional sync queue entry.

## 10.2 Identity and enrollment

- Student is resolved by `Student.user_id`, never by payload alone.
- `student_number` is compared case-insensitively; mismatch raises
  `student_number_mismatch`.
- Inactive students are treated as not enrolled.
- Enrollment requires an `Enrollment` row for student and offering.
- Duplicate scan checks for any existing `Attendance` row for the same student
  and session.

## 10.3 Active session checks

- Session must exist.
- Unless replaying with an idempotency key, `expires_at` must be in the
  future.
- `scanned_at` must not be after `expires_at`.
- `now` must be at or after `scheduled_start_time`.
- `expires_at = max(scheduled_start_time, created_at) + duration`
  (may extend beyond `scheduled_end_time` for overtime).

## 10.4 Face match score

- Live embedding is generated from `live_face_image` using MobileFaceNet, or
  decoded from `live_face_embedding`.
- Reference embedding is deserialized from `students.face_embedding`.
- `face_match_score = cosine_similarity(reference_embedding, live_embedding)`,
  stored as `Decimal(5,4)`.
- Thresholds:
  - `< 0.65`: `FaceMismatchException`
  - `0.65–0.70`: review band
  - `>= 0.70`: pass
- In the review band, `validation_status` keeps the computed present/late
  status, `original_status` stores that value, and
  `liveness_evidence.review = true`.

## 10.5 Geofence

- Skipped when `geofence_enabled` is false or classroom coordinates are
  missing.
- Missing GPS is treated as outside the geofence.
- Distance uses haversine:
  - `distance_meters = 2 * 6371000 * asin(sqrt(a))`
  - `a = sin(dlat/2)^2 + cos(lat1) * cos(lat2) * sin(dlng/2)^2`
- Scan is rejected when `distance_meters > classroom_radius_meters`.

## 10.6 Liveness grading

Fixed challenge order: blink, turn left, turn right.

- `blink_detected`, `head_turn_left`, and `head_turn_right` must all be true.
- `ear_samples` must be non-empty.
- Mean EAR must be in `[0.05, 0.5]`.
- `pnp_evidence` must be non-empty.
- `face_count` must equal `1`.
- If present, `peak_left_yaw <= -15` and `peak_right_yaw >= 15`.
- Benchmark mode skips geofence and liveness, but not enrollment or face
  match.

## 10.7 Attendance status

- `anchor = max(session.created_at, session.scheduled_start_time)`.
- `elapsed_minutes = (scanned_at - anchor) / 60`.
- `present` if `elapsed_minutes <= present_window_minutes`.
- `late` if `elapsed_minutes <= present_window_minutes +
  late_window_minutes`.
- Otherwise `rejected`.
- Default windows are 5 minutes present and 10 minutes late.

## 10.8 Review band and resolution

- Review rows are selected by `liveness_evidence["review"] == true`.
- `liveness_evidence["review_reason"]` records why the row was flagged:
  `face_review_band` and/or `geofence_uncertainty` (comma-joined when both).
- `liveness_evidence["geofence"]` carries the geofence context for a
  geofence-flagged row: `distance_meters`, `radius_meters`,
  `accuracy_meters`, `uncertainty_meters`, `classroom_lat`,
  `classroom_lng`.
- Approve restores `validation_status` to `original_status`.
- Reject sets `validation_status = rejected`.
- Resolution removes the review flag, stores the reviewer note in evidence,
  and writes an audit row.

## 10.9 Idempotency and sync staleness

- Idempotency key is scoped as `user_id:session_id:key`.
- TTL is 900 seconds.
- Cache is process-local with a maximum of 10,000 entries.
- Expired entries are pruned when the cache exceeds its cap.
- Replay returns the cached response without reprocessing.
- A sync row is queued only when `(now - scanned_at) > 60 seconds`.
- Replay passes `allow_expired = true`.

## 10.10 GPS acquisition and accuracy

- Client acquires up to 3 fixes and stops early when accuracy is `<= 50 m`.
- Accuracy, distance, required radius, and within/outside result are shown
  before scan submission.
- Low accuracy still allows continuation.
- Latitude, longitude, and accuracy are preserved without rounding.
- Server stores GPS values on the attendance row.

## 10.11 Face enrollment quality gates

Each front, left, and right photo must pass `assess_image_bytes`:

- image decodes successfully
- exactly one face is detected
- brightness is in `[40, 220]`
- face area ratio is at least `0.15`
- horizontal and vertical centering offset is at most `0.30`
- sharpness variance is at least `50`
- left and right EAR are greater than `0.2`

Enrollment then generates a 512-dimensional `FACEEMB1` embedding from the
three photos using MobileFaceNet, with landmark fallback. Enrollment and
revocation bump `face_embedding_version`.

## 10.12 Constants and thresholds

- Face match threshold: `0.70`
- Review band low: `0.65`
- EAR mean range: `[0.05, 0.5]`
- Peak yaw: left `<= -15`, right `>= 15`
- Quality gates: brightness `[40, 220]`, face size `>= 0.15`,
  centering `<= 0.30`, sharpness `>= 50`, EAR `> 0.2`
- Geofence default radius: `50 m`
- Present window: `5 minutes`
- Late window: `10 minutes`
- Idempotency TTL: `900 seconds`
- Sync staleness: `60 seconds`
- Scan rate limit: `30 calls / 60 seconds` per IP, lifted in benchmark mode

## 10.13 Libraries and models

- Reference `docs/proposals/models.md` for the full model/library catalog.
- MediaPipe FaceLandmarker (client WASM): face detection and 478 3D landmarks;
  used for EAR, yaw, and face count.
- MobileFaceNet ONNX (`backend/models/mobilefacenet.onnx`, 512-d): server-side
  embedding generation from front/left/right photos and scan-time embedding.
- OpenCV: image decode, brightness, face size, centering, sharpness, and EAR
  quality checks.
- Cosine similarity (`shared/face_embeddings.py`): compares stored and live
  embeddings.
- html5-qrcode: client QR decoding for session codes.
- No trained anti-spoofing model is used; liveness is protocol-based.

## 10.14 Edge cases

- Missing GPS with an active geofence is rejected as outside.
- Geofence is skipped when disabled or classroom coordinates are missing.
- Benchmark mode skips geofence and liveness only.
- Review-band records remain present/late in history while still appearing in
  the review queue.
- Offline replay can succeed after session expiry when an idempotency key is
  present.
- Face enrollment is required even in benchmark mode.
- Rejected liveness evidence stores `reviewed_by`/`reviewed_at` in
  `liveness_evidence` alongside `review_note` and emails the student with the
  rejection reason and retake availability. Retake is allowed only while the
  session is still open and only when all prior attempts for that
  student/session are `rejected`.

