# Glossary

> Every term and enum value used in the QR-Based Attendance System, with 1–2 sentence definitions and references to where they appear in the database schema (§6) or API contracts.

---

## Core Domain Terms

### Session

A single class meeting instance opened by a professor. Carries a unique HMAC-derived **session code**, configurable scan windows, duration, and optional classroom override. Stored in `sessions` table. Routes: `POST /professor/sessions`, `GET /professor/sessions/active/{id}`.

### Session Code (HMAC)

A 6–8 character code derived from an HMAC of the session ID + secret, used by students to join a session. Verified via `POST /student/sessions/verify-code`; the current professor UI displays this code rather than a QR image.

### Session QR

A versioned JSON payload returned by the session-open API: `{"v":1,"code":"A7X-9K2M","offering":123,"radius":30,"pw":5,"lw":10}`. The payload is **not signed**, and the current professor UI does not render it as a QR image; the scan page posts raw decoded text as the session code. Version `v` enables future migration.

### Enrollment (Course-Taking)

A record linking a `student` to a `course_offering` for a specific `academic_year` and `semester`. Validated against the student's `year_level.term_structure`. Stored in `enrollments` table. Unique constraint on `(student_id, offering_id, academic_year)`.

### Term / Term Structure

A named academic period (e.g., "1st Semester", "Midyear") defined per **program per year level** in `year_levels.term_structure` JSONB: `{"terms": [{"code": "1st_sem", "label": "1st Semester"}, ...]}`. Enrollment `semester` must match one of these codes.

### Year Level

A row in `year_levels` belonging to a `program`, with `year_number` (1..N), `label` (e.g., "1st Year"), `sort_order`, and its own `term_structure`. FK: `program_id → programs`. Unique on `(program_id, year_number)`.

### Program

An academic program (e.g., "BSCS", "BSIT", "BSECE") in `programs` table. Has `code` (UK), `name`, `description`, `total_years`, `is_active`. Owns multiple `year_levels`.

### Course (= Subject)

A reusable subject template stored in `courses` with `course_code` (UK), `course_name`, `units`, `session_duration_hours`. The course itself has **no** program/year-level/scheduling/classroom/window columns — those live on `course_offerings`.

### CourseOffering

A concrete instance of a `course` offered by a `program` to a `year_level` for a specific `semester`/`academic_year`. Stored in `course_offerings` with FKs to `courses`, `programs`, `year_levels`, plus scheduling metadata (`sessions_per_week`, `semester_weeks`, `schedule_days`, `schedule_start_time`, `schedule_end_time`), classroom defaults (`classroom_name`, `classroom_lat/lng`), and late-policy defaults (`default_present_window_minutes`, `default_late_window_minutes`). Unique on `(course_id, program_id, semester, academic_year)`. Enrollments, sessions, professor assignments, and risk scores reference the offering.

### Section

A student-cohort identifier (e.g., "A", "B") stored on `students.section` only — **not** on enrollments. Changed only via admin action (D2). Used for filtering rosters and reports.

### Compliance Rate

**Default display metric**: `present / total_expected_sessions`. Excludes late, excused, absent. Used in all reports unless toggled.

### Participation Rate

**Alternative metric**: `(present + late + excused) / total_expected_sessions`. Toggled via UI. Excused counts as present.

### Present Window / Late Window

Per-session minute windows measured from `session.created_at`:

- **Present window**: scans within `present_window_minutes` → status `present`
- **Late window**: scans within the next `late_window_minutes` → status `late`
  Constraint: `present_window_minutes + late_window_minutes ≤ duration_minutes` (CHECK on `sessions`).

### Duration Expiry

The hard ceiling for scanning: `expires_at = min(session.created_at + duration_minutes, scheduled_end_time)`. After this, no scans accepted; offline scans with `scanned_at` past expiry → `rejected (session_expired)`.

### Scheduled End

The offering's scheduled class end time (`course_offerings.schedule_end_time`) copied to `sessions.scheduled_end_time` at session creation. Forms the ceiling for `expires_at`.

### Geofence

Circular GPS boundary centered on classroom coordinates (offering default from `course_offerings` or session override) with `classroom_radius_meters`. Validation uses Haversine distance. The shipped client captures GPS after the liveness challenge, and the server re-checks it on submit.

### Liveness

Anti-spoofing challenge requiring the student to perform a fixed sequence: **blink → turn left → turn right**. Implemented via MediaPipe Face Mesh WASM client-side; EAR (Eye Aspect Ratio) + PnP (Perspective-n-Point) head pose graded server-side.

### EAR (Eye Aspect Ratio)

Metric computed from facial landmarks to detect eye closure (blink). Part of liveness grading.

### PnP (Perspective-n-Point)

Head-pose estimation from facial landmarks to detect left/right turns. Part of liveness grading.

### Embedding

A 128-dimensional face vector reserved by the schema. The current build stores a zero-filled placeholder in `students.face_embedding` (`_stub_embedding_blob`); real vector generation and encryption are **not implemented**, and no scan reads it. Versioned via `face_embedding_version`.

### Evidence Bundle

JSON object attached to an attendance record containing `liveness_evidence{blink_detected, head_turn_left, head_turn_right, ear_samples, pnp_evidence}`, the GPS `accuracy`, and a `review` flag. Stored in `attendance_records.liveness_evidence JSONB`; `face_match_score`, `scanned_via`, and the timestamp are separate columns. Used for audit and server-side re-validation on sync.

### Excuse Request

A record in `excuse_requests` representing one of three initiation paths (D21):

- `quick`: professor marks absent/late student excused with reason
- `prof_with_evidence`: professor uploads evidence and approves immediately
- `request`: student submits reason + evidence; professor reviews
  State machine: `pending` → `approved` | `rejected`.

### At-Risk Score

Daily-computed heuristic risk level (`low`|`medium`|`high`) per student per offering per semester, stored in `student_risk_scores`. Features: `absence_rate`, `max_streak`, `sync_lag`, `trend_slope`. Thresholds from env vars (D35).

### Sync Queue

Offline-first queue in `sync_queue` table. Client writes pending attendance records (with `record_data` JSON including `scanned_at`, evidence bundle) when offline. Background sync retries with exponential backoff. Server validates `scanned_at` against session window (D16).

### Claim-Based Registration

Account activation flow where a student/professor enters their official email → receives OTP → sets password → links to pre-existing `students`/`professors` record via `user_id` FK. Handled by `/auth/register` + `/auth/otp/*` (Phase 2, see api-contracts § Shared Auth Endpoints).

---

## Enum Values (from §6 Target Schema)

### ValidationStatus (`attendance_records.validation_status`)

| Value      | Meaning                                                    |
| ---------- | ---------------------------------------------------------- |
| `present`  | Scanned within present window                              |
| `late`     | Scanned within late window                                 |
| `absent`   | No scan by session expiry                                  |
| `excused`  | Excused via any path (counts as present for Participation) |
| `pending`  | Offline queued, not yet synced                             |
| `rejected` | Failed validation (see rejection reasons)                  |

### Rejection Reasons (stored in `liveness_evidence.rejection_reason` or inferred)

| Value              | Meaning                                    |
| ------------------ | ------------------------------------------ |
| `duplicate_scan`   | Student already scanned for this session   |
| `outside_geofence` | GPS distance > radius                      |
| `liveness_failed`  | Liveness challenge failed (EAR/PnP)        |
| `face_mismatch`    | Submitted `face_match_score` < 0.65 (no cosine comparison exists) |
| `not_enrolled`     | Student not enrolled in session's offering |
| `session_expired`  | `scanned_at` > `expires_at` (offline sync) |

### UserRole (`users.role`)

| Value         | Meaning                                                 |
| ------------- | ------------------------------------------------------- |
| `super_admin` | Full system access including admin user management      |
| `admin`       | Program management, analytics, backups, face enrollment |
| `professor`   | Session management, attendance, excuses, reports        |
| `student`     | Scan attendance, view history/schedule, request excuses |

### OtpPurpose (`otp_codes.purpose`)

| Value             | Meaning                    |
| ----------------- | -------------------------- |
| `claim`           | Account claim registration |
| `forget_password` | Password reset             |

### SyncStatus (`attendance_records.sync_status`)

| Value     | Meaning                            |
| --------- | ---------------------------------- |
| `synced`  | Successfully written to server     |
| `pending` | Queued locally or in transit       |
| `failed`  | Sync rejected (reason in evidence) |

### QueueStatus (`sync_queue.status`)

| Value        | Meaning                      |
| ------------ | ---------------------------- |
| `pending`    | Awaiting sync attempt        |
| `processing` | Sync in progress             |
| `done`       | Synced successfully          |
| `failed`     | Exhausted retries / rejected |

### ExcuseRequest Status (`excuse_requests.status`)

| Value      | Meaning                                              |
| ---------- | ---------------------------------------------------- |
| `pending`  | Awaiting professor review (student-initiated)        |
| `approved` | Excuse granted → attendance status becomes `excused` |
| `rejected` | Excuse denied; original status stands                |

### ExcuseRequest InitiatedBy (`excuse_requests.initiated_by`)

| Value       | Meaning                                 |
| ----------- | --------------------------------------- |
| `professor` | Prof-initiated (quick or with evidence) |
| `student`   | Student-initiated request               |

### ExcuseRequest InitiatedVia (`excuse_requests.initiated_via`)

| Value                | Meaning                                 |
| -------------------- | --------------------------------------- |
| `quick`              | Prof quick-excuse (no evidence upload)  |
| `prof_with_evidence` | Prof files with evidence, auto-approved |
| `request`            | Student submits request                 |

### ExcuseType (`attendance_records.excuse_type`)

| Value                | Meaning                       |
| -------------------- | ----------------------------- |
| `quick`              | From prof quick-excuse        |
| `prof_with_evidence` | From prof with evidence       |
| `request_approved`   | From approved student request |

### RiskLevel (`student_risk_scores.risk_level`)

| Value    | Meaning                    |
| -------- | -------------------------- |
| `low`    | Below all thresholds       |
| `medium` | Meets one medium threshold |
| `high`   | Meets any high threshold   |

### BackupKind (`backup_log.kind`)

| Value       | Meaning                                |
| ----------- | -------------------------------------- |
| `full`      | Full pg_dump of all tables (encrypted) |
| `analytics` | Aggregated CSV/PDF export              |

### BackupStorageBackend (`backup_log.storage_backend`)

| Value   | Meaning                                                  |
| ------- | -------------------------------------------------------- |
| `local` | Local filesystem (`BACKUP_LOCAL_DIR`)                    |
| `s3`    | S3-compatible (`BACKUP_S3_BUCKET`, `BACKUP_S3_ENDPOINT`) |

### ScannedVia (`attendance_records.scanned_via`)

| Value         | Meaning                    |
| ------------- | -------------------------- |
| `qr_camera`   | Default value; the SPA does not send `scanned_via` |
| `manual_code` | Student typed session code |

