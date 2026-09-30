# Decision Log (ADR Format)

> All decisions below were explicitly confirmed by the project owner on **2026-08-25**.
> Status: **Accepted** — do not re-litigate.

---

## 2.1 Data Model / Academic Structure

### ADR-001: Academic Hierarchy — Program → Year Level → Course

- **Decision (D1):** Introduce hierarchy **Program → Year Level → Course** with strict FK constraints (NOT NULL in target schema, cascade/restrict rules per §6).
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** The current flat `courses` table cannot express program-specific year structures or term definitions. A hierarchical model enables per-program-per-year term structures and proper course ownership.
- **Consequences:** Requires new tables `programs` and `year_levels`; `courses` gains `program_id` and `year_level_id` FKs. In the target schema, `students` uses `year_level_id` FK directly (no legacy `course` string).
> **Superseded by D44** — program/year-level FKs moved from `courses` to `course_offerings`; hierarchy is now Program → Year Level → CourseOffering (course templates carry no program/year FKs).

### ADR-002: Course = Subject; Section on Students Only

- **Decision (D2):** `course == subject` (one subject), and a student has **one section**, stored on `students` only — NOT on enrollments. Section changes only via admin action (e.g., promotion-style update).
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Enrollments represent course-taking; section is a student-cohort property. This avoids duplication and keeps section management centralized.
- **Consequences:** `students.section` retained; `enrollments` has no section field.

### ADR-003: Term Structure Per Program Per Year

- **Decision (D3):** Term structure is **per-program-per-year**: each `year_levels` row owns its own `term_structure` JSONB. Example reality: BSCS Y1/Y2 = 2 semesters; BSCS Y3 = 1st, 2nd + Midyear; BSCS Y4 = 2 semesters. Other programs define their own.
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Different programs and year levels have different academic calendars. A single global term table is insufficient.
- **Consequences:** `year_levels.term_structure` JSONB stores `{"terms": [{"code": "...", "label": "..."}, ...]}`. Enrollment `semester` validated against this.

### ADR-004: Course Scheduling Metadata

- **Decision (D4):** Courses gain scheduling metadata: `units`, `sessions_per_week`, `session_duration_hours`, `semester_weeks`, structured schedule fields (`schedule_days`, start/end time), `classroom_name`, GPS coords. These feed analytics and at-risk prediction.
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Current `courses.schedule` is a free-text string. Structured fields enable expected-session calculation for risk scoring and conflict detection.
- **Consequences:** `courses` table gains 9+ new columns. Expected sessions formula: `semester_weeks × sessions_per_week`.
> **Superseded by D44** — scheduling/classroom/window metadata moved to `course_offerings`; `courses` keeps only `units` + `session_duration_hours`.

### ADR-005: Enrollment Gains Semester

- **Decision (D5):** Enrollment gains `semester` (term code validated against the year level's term structure).
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Needed to scope enrollments to a specific term within a year level's structure.
- **Consequences:** `enrollments.semester` NOT NULL in target schema; validated via application logic against `year_levels.term_structure`.

### ADR-006: Courses Shared Across Programs/Year Levels

- **Decision (D6):** A course can be taken by multiple programs/year levels (e.g., a BSCS 1st-year subject also taken by BSIT 1st year). Filters everywhere must support program/year slicing of the same course.
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** General education (GE) courses are shared. Analytics must slice the same course by cohort.
- **Consequences:** `courses` has `program_id` + `year_level_id` (owning program/year), but enrollments from other programs/years can reference it. Filters in reports must join through enrollments to get student's program/year.
> **Superseded by D44** — sharing now happens via multiple `course_offerings` per course instead of cross-program/year enrollments on a single course.

---

## 2.2 Professor Assignment

### ADR-007: Course↔Professor Many-to-Many with Effectiveness Dates

- **Decision (D7):** Course↔Professor is many-to-many via `course_professors` with `is_primary`, plus **time-bounded effectiveness**: `effective_from`, `effective_to` (nullable = ongoing), `semester`, `assigned_by`, `assigned_at`.
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Professors change mid-semester; history must be preserved. A simple FK on `sessions` or `courses` loses attribution history.
- **Consequences:** New table `course_professors` with composite PK `(course_id, professor_id, effective_from)`. Service layer must reject overlapping effectiveness ranges for same `(course_id, professor_id)`.
> **Superseded by D45** — PK changed to `(offering_id, professor_id, effective_from)`.

### ADR-008: Professor Changes Mid-Semester — History Preserved

- **Decision (D8):** Professors CAN be changed entirely mid-semester: end old assignment (`effective_to` = day before), open new one. History is never rewritten; old sessions stay attributed to the original professor.
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Real-world handover scenarios. Audit integrity requires immutable attribution.
- **Consequences:** Session creation reads active assignment at `created_at`; `course_professors` row at that time determines professor of record.

### ADR-009: Assistants Supported via Secondary Assignments

- **Decision (D9):** Assistants are supported (secondary assignments). Any professor with an active assignment for course+semester may open sessions.
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Multiple professors may teach the same course (primary + assistants).
- **Consequences:** `course_professors.is_primary` distinguishes primary; both can open sessions if effective range covers current date and semester matches.

### ADR-010: Absent Professor, Class Activities — No Special Feature

- **Decision (D10):** Rare real-world case "prof is absent but class does activities" needs no special feature — session runs normally; live monitoring is optional.
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Edge case; existing session flow handles it.
- **Consequences:** No new fields or workflows.

---

## 2.3 Sessions & Attendance

### ADR-011: Session Creation — Locked Course vs Selector

- **Decision (D11):** Opening a session **from My Courses locks the course** (no selector). Opening from Dashboard "New Session" allows choosing among the professor's active assignments.
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** UX optimization — common case (professor opens session for their course) should be frictionless.
- **Consequences:** Two session-create entry points with different UI; same backend endpoint with optional `offering_id` (required for locked variant).

### ADR-012: Session Duration & Expiry — System-Time Based

- **Decision (D12):** Session duration is **system-time based**. Example: class scheduled 7:00–8:30; prof arrives 7:10 and sets duration 15 min → scan window ends 7:25. Class still ends at scheduled 8:30 (system time). `expires_at = min(created_at + duration_minutes, scheduled_end_time)`.
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Prevents sessions from running past scheduled class end. Professor sets intended scan duration; system enforces hard ceiling at scheduled end.
- **Consequences:** `sessions` gains `duration_minutes`, `scheduled_start_time`, `scheduled_end_time`, `expires_at` (app-computed, D49). Dual timers in live view.

### ADR-013: Present/Late Windows Per Session

- **Decision (D13):** Present/Late windows per session: scans within `present_window_minutes` → `present`; within `late_window_minutes` after that → `late`; scanning closes at duration expiry; no-scan students become `absent` when the session expires. Constraint: `present_window_minutes + late_window_minutes ≤ duration_minutes`.
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Configurable grace periods. Late window starts after present window ends.
- **Consequences:** `sessions` gains `present_window_minutes`, `late_window_minutes` with CHECK constraint. Status determined at scan time by comparing `scanned_at` to `session.created_at`.

### ADR-014: Late Policy Defaults on Course

- **Decision (D14):** Late policy defaults live on the **course** (`default_present_window_minutes`, `default_late_window_minutes`) and are overridable per session.
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Reduces repetitive configuration; professors can override for specific sessions.
- **Consequences:** `courses` gains two default window columns; session create pre-fills from course.
> **Superseded by D44** — late-policy defaults (`default_present_window_minutes`, `default_late_window_minutes`) moved to `course_offerings`; sessions pre-fill from the offering.

### ADR-015: Expanded Validation Status Enum

- **Decision (D15):** Validation status enum expands to: `present`, `late`, `absent`, `excused`, `pending`, `rejected`. Rejection reasons include duplicate, geofence, liveness, face mismatch, not enrolled, `session_expired` (DB/API identifiers defined in §6: `duplicate`, `outside_geofence`, `liveness_failed`, `face_mismatch`, `not_enrolled`, `session_expired`).
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Current enum (`valid`, `pending`, `rejected`) is insufficient for compliance reporting and excuse workflow.
- **Consequences:** Migration must map existing values: `valid → present`, keep `pending`, `rejected → rejected` (with reason). New `ValidationStatus` enum in code.

### ADR-016: Offline Scans — Server Validates `scanned_at`

- **Decision (D16):** Offline scans are stored with device `scanned_at`; on sync the server validates `scanned_at` against the session window. Expired-window offline scans → `rejected` with reason `session_expired`.
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Prevents clock manipulation. Offline queue items carry client timestamp; server is authority.
- **Consequences:** `sync_queue.record_data` must include `scanned_at`. Sync endpoint validates and sets rejection reason.

### ADR-017: Classroom Override — Session-Level Optional

- **Decision (D17):** Classroom override is **session-level optional** (`sessions.classroom_*` fields override offering defaults when set); geofence uses session coords if overridden, else offering coords.
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Room changes happen; course default is fallback.
- **Consequences:** `sessions` gains `classroom_name`, `classroom_lat`, `classroom_lng` (nullable). Geofence logic checks session override first.

### ADR-018: Session Entry — Code or QR

- **Decision (D18):** Session entry for students supports BOTH: typing the 6–8 char session code OR scanning the projected session QR. Session QR payload is JSON: `{"v":1,"code":"A7X-9K2M","offering":123,"radius":30,"pw":5,"lw":10}` (versioned for future migration).
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Accessibility — not all students can scan QR reliably. Versioned payload enables future fields.
- **Consequences:** Student app has two entry modes (manual code input / QR scan). Verify-code endpoint returns session config bundle.

### ADR-019: Student ID-Card QR — Student Number Only

- **Decision (D19):** Student ID-card QR contains **the student number only** (e.g., `24-2111`). Course context always comes from the verified session, never from the QR.
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Simplifies ID card printing; security — course context bound to active session.
- **Consequences:** QR payload is just `student_id` string. Scan flow: verify session first, then scan ID QR.

---

## 2.4 Excuse Workflow

### ADR-020: Excused Attendance — First-Class Status

- **Decision (D20):** Excused attendance is a first-class status with a mandatory reason and audit trail (`excused_by`, `excused_at`).
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Compliance reporting treats excused as present. Audit trail required for disputes.
- **Consequences:** `attendance_records` gains `original_status`, `excuse_reason`, `excused_by`, `excused_at`, `excuse_type`, `excuse_request_id`.

### ADR-021: Three Excuse Initiation Paths

- **Decision (D21):** Three initiation paths, all persisted in `excuse_requests`:
  - (a) **Prof quick-excuse** — prof marks absent/late student excused with reason;
  - (b) **Prof-initiated with evidence** — prof holds physical proof (e.g., excuse letter) and files/approves immediately, attaching evidence;
  - (c) **Student-initiated request** — student submits reason + evidence upload; professor approves/rejects.
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Covers all real-world excuse scenarios with different evidence burdens.
- **Consequences:** New table `excuse_requests` with `initiated_by` (`professor`|`student`), `initiated_via` (`quick`|`prof_with_evidence`|`request`). State machine: `pending` → `approved`|`rejected`.

### ADR-022: Excuse Overrides Scanned Status

- **Decision (D22):** Excusing overrides the scanned status: if a late-scanning student is excused, final status = `excused` (treated as present for compliance), while `original_status` preserves what actually happened (audit).
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Compliance rates count excused as present; audit needs truth.
- **Consequences:** `attendance_records.validation_status` becomes `excused`; `original_status` stores prior value (`late`/`absent`/`rejected`).

### ADR-023: Bulk Excuse All Absent

- **Decision (D23):** Bulk action: professors can **"Excuse All Absent"** for a session (typical use: cancelled class).
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Common workflow for cancelled classes.
- **Consequences:** Endpoint `POST /professor/sessions/{id}/excuse-all-absent` with reason. Idempotent — only affects currently `absent` records.

### ADR-024: Excuse Evidence — S3-Compatible Storage

- **Decision (D24):** Excuse evidence attachments are stored in S3-compatible storage (Supabase Storage / R2 / S3; local filesystem in dev). DB stores URL references only. Same storage backend as backups.
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Binary files don't belong in DB. Shared infrastructure with backups.
- **Consequences:** `excuse_requests.attachment_urls` JSONB array. Env vars for storage config mirror backup config.

---

## 2.5 Cancelled Classes / Security Posture

### ADR-025: No "Mark All Present" or Security-Disabled Sessions

- **Decision (D25):** NEVER implement "mark all present" or sessions with security disabled. Cancelled class = either **no session opened**, or session opened and **Excuse All** applied.
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Security posture — attendance must reflect reality. Excuse All provides audit trail for cancelled classes.
- **Consequences:** No "disable security" flag. UI never offers "mark all present".

### ADR-026: Remote/Online Classes — Relaxed Geofence, Liveness Mandatory

- **Decision (D26):** Remote/online classes (if ever needed) use a relaxed/large geofence but **liveness remains mandatory**.
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Anti-spoofing is non-negotiable. Geofence can be widened for remote.
- **Consequences:** Geofence radius configurable per session; liveness challenge always runs.

---

## 2.6 Student Scan Flow & Face

### ADR-027: Strict 5-Step Sequential Scan Flow

- **Decision (D27):** Scan flow is strictly sequential:
  1. Enter/scan session code → verify → fetch session config
  2. Scan student-ID QR → resolve student number → fetch student record incl. enrolled face embedding + enrollment check for the session's course + duplicate-scan check
  3. GPS geofence validation runs alongside steps 2–3 (Haversine vs radius)
  4. Face liveness challenge (fixed sequence: blink → turn left → turn right) then embedding comparison vs fetched embedding(s) (cosine similarity ≥ threshold)
  5. Success writes attendance record (status present/late by window timing; pending if offline)
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Security requires ordered verification. Each step gates the next.
- **Consequences:** Student app has 5 sub-screens (`/student/scan/step/[1-5]`). Offline mode queues at step 5.

### ADR-028: Face Embedding — Admin-Enrolled, 3 Photos, Encrypted

- **Decision (D28):** Face embedding: **admin-enrolled** via a dedicated admin section (NOT bundled into CSV import). Enrollment captures **3 photos** (front, left, right); server generates 128-d embeddings (face-api.js-compatible), stores encrypted (`students.face_embedding BYTEA`) + `face_enrolled_at` + `face_embedding_version`.
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Privacy — biometric enrollment is admin-supervised. 3 angles improve accuracy. Encryption at rest required.
- **Consequences:** `students` gains `face_embedding BYTEA`, `face_enrolled_at`, `face_embedding_version`. Admin face-enrollment UI separate from student import.

### ADR-029: Embedding Distribution — Pull-on-Login

- **Decision (D29):** Embedding distribution to student devices is **pull-on-login** (client checks version and downloads if newer; cached encrypted in IndexedDB). No push/WebSocket infra.
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Simplicity — no real-time infrastructure. Devices fetch on login.
- **Consequences:** Endpoint `GET /student/me/face-embedding` with version gating. Client caches in IndexedDB encrypted via WebCrypto.

### ADR-030: Offline Verification — Local Compare, Scores Sync

- **Decision (D30):** Offline verification compares against cached embedding locally; only scores/evidence sync to server.
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Embedding never leaves device in offline mode. Server re-verifies on sync? No — server trusts client score but validates liveness evidence.
- **Consequences:** Offline queue item includes `face_match_score`, `liveness_evidence`. Server validates evidence, not embedding.

### ADR-031: Fixed Liveness Sequence — Blink → Left → Right

- **Decision (D31):** Liveness sequence is **fixed** (blink → left → right), MediaPipe Face Mesh WASM client-side, EAR + PnP heuristics graded server-side. Sibling-confusion risk is acknowledged as a known limitation, not solved (per instructor: treated as future assignment).
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Deterministic sequence simplifies implementation and grading. Sibling confusion accepted as known gap.
- **Consequences:** Client implements fixed 3-step challenge. Server grades EAR (eye aspect ratio) + PnP (head pose). Review queue for borderline scores.

### ADR-032: Student Profile — Read-Only Identity

- **Decision (D32):** Student profile is **read-only** (identity data admin-managed); students may only change password/security settings (same rule as professors).
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Data integrity — student identity (name, student_id, program, year, section) managed by admin.
- **Consequences:** Student profile UI shows read-only fields + password/MFA/security question settings.

---

## 2.7 Analytics & Reporting

### ADR-033: Admin Analytics & Reports — Unified, Cascading Filters

- **Decision (D33):** Admin **merges Reports (4.8) and Analytics (4.7)** into one "Analytics & Reports" page with tabs: Overview, Course Comparison, Trends, At-Risk, Export. Cascading filters: Program → Year → Term → Courses (multi). Granularity: daily / weekly / monthly.
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Unified view reduces navigation; cascading filters enable cohort slicing.
- **Consequences:** Single route `/admin/analytics` with 5 tabs. Filter rail persistent on left.

### ADR-034: Per-Course Comparison — Slice by Program/Year

- **Decision (D34):** Per-course comparison must slice by program and year level (same subject across cohorts), within term (semester) durations. Daily-average becomes a Trends view supporting day/week/month granularity.
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Same course (e.g., "Math 101") taken by BSCS Y1 and BSIT Y1 — must compare side by side.
- **Consequences:** Course Comparison tab groups by course, shows multiple bars per course (one per program/year cohort).

### ADR-035: At-Risk Heuristic Thresholds — Daily Batch Job

- **Decision (D35):** At-risk prediction starts as **heuristic thresholds** (env-configurable):
  - `absence_rate > 0.30 → high`; `> 0.15 → medium`
  - `streak ≥ 3 consecutive misses → high`
  - `sync-lag pending ≥ 5 → medium`
  - `trend slope < −0.05/week → medium`
    Expected sessions derive from course metadata: `semester_weeks × sessions_per_week` (e.g., 3 units ≈ 2 meetings/week × 1.5 h). Runs as a **daily batch job** (nightly), writing `student_risk_scores`. Manual refresh endpoint exists (admin-only). ML (logistic regression) is a later upgrade, same feature vector.
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Rule-based first; ML later. Thresholds configurable via env for tuning.
- **Consequences:** New table `student_risk_scores`. Nightly job (Celery/APScheduler). Features: `expected_sessions`, `absence_rate`, `max_streak`, `sync_lag`, `trend_slope`.

### ADR-036: Two Rate Metrics — Compliance & Participation

- **Decision (D36):** Two rate metrics everywhere: **Compliance Rate** = present / total (DEFAULT display) and **Participation Rate** = (present + late + excused) / total (toggle/option).
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Compliance is strict (on-time only); participation is inclusive.
- **Consequences:** All reports/charts default to Compliance; toggle for Participation. Excused counts as present for Participation.

### ADR-037: Professor Reports — All Courses Aggregate + Per-Course Comparison

- **Decision (D37):** Professor reports add an **All Courses** aggregate tab (daily/weekly/monthly across all assigned courses) plus per-course comparison with program/year filters.
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Professors teaching multiple courses need holistic view.
- **Consequences:** `/professor/reports` has 3 tabs: All Courses, Per-Course Comparison, Trends.

---

## 2.8 Admin System Settings

### ADR-038: Academic Structure Updates Replace Promotion

- **Decision (D38):** Remove "Year + Section Promotion" (grade-dependent; inappropriate for attendance-only system). Replace with **Academic Structure Updates**: bulk edit flows into Program Management (add/rename year levels, adjust term structures, move courses) — manual, intentional, audited.
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Promotion implies grade progression; this system is attendance-only. Structural changes should be deliberate.
- **Consequences:** Admin nav: "Programs" replaces "Courses". System Settings gets "Academic Structure Updates" block linking to Program Management. Audit log captures all structural changes.

### ADR-039: Full Encrypted Backups — Everything by Default

- **Decision (D39):** Backup = **full database dump of EVERY table — nothing excluded by default** (pg_dump custom format, compressed) **encrypted AES-256-GCM** with key from env; plus separate "Analytics Export" (aggregated CSV/PDF). Storage: local volume (dev) / S3-compatible (prod) via `BACKUP_STORAGE_TYPE`. Retention: last 30 daily + 12 monthly. All backups logged in `backup_log`.
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Compliance requires full recoverability. Encryption mandatory. Optional opt-in to skip ephemeral `otp_codes`.
- **Consequences:** New table `backup_log`. Backup pipeline: `pg_dump -Fc` → gzip → AES-256-GCM encrypt → upload → log → prune. Key rotation via version header.

### ADR-040: Admin Nav Restructure

- **Decision (D40):** Admin nav becomes: Dashboard · Students · Professors · **Programs** (was Courses) · **Analytics** (merged Reports+Analytics) · Audit Logs · System Settings. Existing screens 4.13 Liveness Review, 4.14 Admin Users remain.
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Reflects new hierarchy and merged analytics.
- **Consequences:** Route changes: `/admin/programs/*`, `/admin/analytics`. Old `/admin/courses` removed (functionality moved under Programs).

---

## 2.9 Misc

### ADR-041: Frontend Chart Library — Chart.js

- **Decision (D41):** Frontend chart library: **Chart.js** (+ date adapter) wrapped in a reusable Svelte component.
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Lightweight, works with Svelte 5 runes, good date-axis support.
- **Consequences:** Component `charts/ChartCanvas.svelte` wraps Chart.js.

### ADR-042: Buildings/Campuses Table — Deferred to v2

- **Decision (D42):** Buildings/campuses table deferred to v2. MVP uses classroom name + lat/lng on courses/sessions.
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Scope control. Classroom coords on course/session sufficient for MVP geofence.
- **Consequences:** No `buildings` or `campuses` tables in target schema.

### ADR-043: Multi-Angle Enrollment — 3 Photos

- **Decision (D43):** Multi-angle enrollment reduced to 3 photos (front/left/right) — chosen over 1 or 5.
- **Date:** 2026-08-25
- **Status:** Accepted
- **Context:** Balance of accuracy (3 angles) vs capture burden.
- **Consequences:** Face enrollment UI captures exactly 3 photos. Embedding blob stores mean + 3 per-angle vectors.

---

## 2.10 Schema Evolution (Superseding)

### ADR-044: Course Offerings — Decouple Course from Program/Year/Schedule

- **Decision (D44):** Introduce a `course_offerings` table (course_id FK, program_id FK, year_level_id FK, semester, academic_year, sessions_per_week, semester_weeks, schedule_days, schedule_start_time/end_time, classroom_name/lat/lng, default_present_window_minutes, default_late_window_minutes, is_active, timestamps, UNIQUE(course_id, program_id, semester, academic_year)). `courses` becomes a pure template (course_code, course_name, units, session_duration_hours, is_active, timestamps).
- **Date:** 2026-09-10
- **Status:** Accepted
- **Context:** A course can be offered by multiple programs AND taken at multiple year levels with differing schedules/classrooms per offering (e.g., CS101 in BSCS MWF 9am vs BSIT TTh 2pm). Single program_id/year_level_id FKs on courses forced 1:1 and broke sharing.
- **Supersedes:** D1 (FK placement — program_id/year_level_id move to course_offerings), D4 (scheduling metadata — only units + session_duration_hours stay on courses; the rest move to course_offerings), D6 (sharing mechanism — via multiple offerings per course instead of cross-program enrollments), D14 (late policy defaults live on course_offerings, pre-fill sessions from offering).
- **Consequences:** Migration Step 3 creates course_offerings and strips courses down; enrollments/sessions reference offering_id.

### ADR-045: Professor Assignments & Risk Scores Reference Course Offerings

- **Decision (D45):** `course_professors` FK changes from `course_id` to `offering_id` (PK(offering_id, professor_id, effective_from)); `student_risk_scores` FK changes from `course_id` to `offering_id` (UNIQUE(student_id, offering_id, semester, computed_day)).
- **Date:** 2026-09-10
- **Status:** Accepted
- **Context:** Assignments and risk are scoped to a specific offering (program + year + semester), not the course template.
- **Supersedes:** D7 (composite PK now on offering_id), D17 (classroom defaults now come from offering), D35 (risk scores keyed by offering).
- **Consequences:** Step 4 and Step 8 migrations use offering_id.

### ADR-046: Session Professor FK References Professors Table

- **Decision (D46):** `sessions.professor_id` references `professors.id`, not `users.id`.
- **Date:** 2026-09-11
- **Status:** Accepted
- **Context:** A session is opened by a specific professor (not a generic user). `CourseProfessor.professor_id` already targets `professors.id`; sessions should follow the same pattern for consistency. This gives direct access to professor name/department without an extra join through `users`.
- **Consequences:** The session `professor` relationship returns a `Professor` instance. The logged-in user (JWT) resolves to a professor record via `Professor.user_id` before session creation. `database-er.md` FK notation and cardinality table updated. `migration-strategy.md` Step 6 includes retargeting the `professor_id` FK from `users.id` to `professors.id`.

### ADR-047: Backup Status Enum — Started/Completed/Failed

- **Decision (D47):** `BackupStatus` enum values are `started`, `completed`, `failed` (replacing the earlier implied `success`/`failed` pairing).
- **Date:** 2026-09-13
- **Status:** Accepted
- **Context:** A backup run spends time in a non-failed, in-flight state before finishing; `started` lets the backup UI/log distinguish running vs done vs failed.
- **Supersedes:** D39's implied `success`/`failed` status values.
- **Consequences:** `backup_log.status` stores `started` | `completed` | `failed`. Implemented in `src/shared/enums.py` `BackupStatus`.

### ADR-048: Face-Match Threshold ≥ 0.70; Session Status Computed DTO-Only

- **Decision (D48):** Face-match pass threshold is **`FACE_MATCH_THRESHOLD = 0.70`** (config default — supersedes the earlier 0.75 pass band). Session lifecycle `status` (`active`/`closed`) is **computed in the DTO layer only**; it is not a stored column (`active` = `expires_at > now()`).
- **Date:** 2026-09-13
- **Status:** Accepted
- **Context:** Threshold tuned to reduce false rejects; session lifecycle state is fully derivable from `sessions.expires_at`, so persisting a separate status column would risk drift.
- **Consequences:** `face_match_score >= 0.70` passes (below → `face_mismatch` rejection); `FACE_REVIEW_BAND_LOW` (0.65) still flags borderline scans for manual review. `sessions.status` (`active`/`closed`) is derived during serialization.

### ADR-049: Session expires_at Computed in Application Layer

- **Decision (D49):** `sessions.expires_at` is computed in the application service layer (Python) instead of as a PostgreSQL `GENERATED ALWAYS AS ... STORED` column.
- **Date:** 2026-09-13
- **Status:** Accepted
- **Context:** PostgreSQL persisted computed columns require IMMUTABLE expressions. `timestamptz + interval` is classified as STABLE (timezone-dependent), causing `generation expression is not immutable` error on `alembic upgrade head`.
- **Consequences:**
  - `expires_at` becomes a regular `DateTime(timezone=True)` nullable column
  - Model exposes `@property computed_expires_at` — single source of truth for the formula
  - Service layer sets `expires_at = session.computed_expires_at` at session creation
  - Simpler migrations, portable across databases, easier to test
- **Supersedes:** Part of D12 (the STORED column implementation detail)

### ADR-050: student_risk_scores uses computed_day DATE column

- **Decision (D50):** `student_risk_scores` unique index uses a plain `computed_day DATE` column instead of `date(computed_at)` expression.
- **Date:** 2026-09-14
- **Status:** Accepted
- **Context:** PostgreSQL `date(timestamptz)` is STABLE, not IMMUTABLE. Expression indexes require IMMUTABLE functions. Using `date(computed_at)` in a unique index causes `functions in index expression must be marked IMMUTABLE`.
- **Consequences:**
  - `computed_day` is a regular `DATE NOT NULL` column, set by the service layer: `risk_score.computed_day = risk_score.computed_at.date()`
  - Unique index becomes `UNIQUE(student_id, offering_id, semester, computed_day)` — plain column, no expression
  - Same pattern as D49: move computation to application layer, store result as regular column

### ADR-051: Auth Phase 2 — Token Transport & MFA Login Gating

- **Decision (D51):** Refresh token travels in the `TokenResponse` body (not
  httpOnly cookie); cookie form (`httpOnly; Secure; SameSite=Strict`) is Phase 10
  scope behind same-origin HTTPS. When `user.mfa_enabled`, `POST /auth/login`
  returns `{mfa_pending: true, preauth_token}` (5-min, no access) and
  `POST /auth/mfa/verify` exchanges `{preauth_token, code}` for the full token
  pair. Forgot-password is OTP-only (`OtpPurpose.FORGET_PASSWORD`) per test-plan
  SH-AU-5; the wireframe 4-step flow (Turnstile + security question, 3-attempt
  cap) is deferred.
- **Date:** 2026-09-16
- **Status:** Accepted
- **Context:** Cross-origin frontend + HTTP local dev make Secure httpOnly cookies
  impossible (security-model.md:79); T6's 15-min access + MFA + lockout covers
  body-refresh risk. MFA must gate login to stay meaningful (wireframes:102,
  proposal:565). Docs conflicted on forgot-password — aligned to test-plan.
- **Consequences:** `TokenResponse` includes `refresh_token` (client keeps in
  memory); `preauth` JWT type, 5-min expiry; `security_question_*` columns stay
  reserved; api-contracts auth table gains `/otp/request`, `/refresh`,
  `/change-password`.
- **Supersedes:** httpOnly-cookie detail of security-model.md:79 (re-scoped to
  Phase 10).

### ADR-052: Security Question in Auth Recovery

- **Decision (D52):** Supersede D51's security-question deferral. Implement the
  wireframe 4-step forgot-password flow (wireframes.md:152-260): email → mandatory
  security question (Argon2id-hashed answer, 3-attempt cap then lock) → OTP via
  `OtpPurpose.FORGET_PASSWORD` → new password. The security question is set at claim
  registration (`/auth/register`) and updatable later via `/auth/security-question`
  (authenticated). No migration — `users.security_question_hash` and
  `users.security_answer_hash` columns already exist. Cloudflare Turnstile on step 1
  remained deferred at ADR-052 time (no `shared/captcha.py`); it is now
  implemented separately in ADR-053.
- **Date:** 2026-09-16
- **Status:** Accepted
- **Context:** D51 deferred the security question because the OTP-only path matched
  test-plan SH-AU-5 and the Turnstile requirement. Now that the feature is being
  implemented, the wireframes are authoritative for the recovery UX. Since registration
  requires a security question (every user has one), the mandatory gate never leaves a
  user without a recovery path. D51's OTP-only note is superseded for the security-
  question step; the rest of D51 (refresh-token body transport, MFA preauth gating)
  remains unchanged.
- **Consequences:** Implements the service, router, and registration changes in the
  Phase 2 auth slice. `api-contracts.md` gains three endpoints
  (`/auth/forgot-password`, `/auth/forgot-password/verify`, `/auth/security-question`);
  test-plan SH-AU-5 now includes the security-question step; security-model.md is
  updated. No schema or enum changes.
- **Supersedes:** security-question deferral portion of D51 (security-model.md:81).

### ADR-053: Turnstile Captcha Implemented (Key-Gated)

- **Decision (D53):** Implement Cloudflare Turnstile on `POST /auth/login` and
  forgot-password step 1 (wireframes.md:82, 156, 1904) in Phase 2,
  superseding the "deferred" notes in D51/D52/security-model.md:81. Verification
  lives in `shared/captcha.py` (`verify_turnstile_token`); when
  `TURNSTILE_SECRET_KEY` is empty (local/dev/test) it is a pass-through no-op, so
  the code ships without credentials and enforcement turns on purely via env
  (production-checklist.md:129-138). Optional `turnstile_token` fields on
  `LoginRequest` / `ForgotPasswordStep1Request`; never block the flow when captcha
  is disabled.
- **Date:** 2026-09-17
- **Status:** Accepted
- **Context:** The roadmap placed Turnstile at Phase 10 as a production-checklist
  item, but the guarded endpoints are Phase 2 and the roadmapped Phase-10 item
  already covers provisioning (site/secret keys). Writing siteverify code at
  deployment time was awkward; the key-gated design lets Phase 2 own the code and
  Phase 10 own the credentials. Rate limiting + lockout (D25) remain
  the always-on bot protection.
- **Consequences:** Adds `shared/captcha.py`,
  gateway calls in the auth router, and schema fields; `api-contracts.md` notes
  the turnstile_token fields; `security-model.md:81` no longer defers Turnstile;
  production-checklist rows are unchanged (provisioning). No migration, no new
  config field.
- **Supersedes:** Turnstile-deferral portions of D51 (security-model.md:81) and
  D52 (ADR-052 consequences).

### ADR-054: MFA Backup Codes

- **Decision (D54):** Add single-use backup codes for MFA (wireframes.md:291-292
  "Generate Backup Codes", 1.6:325 "Use a backup code") in Phase 2. New
  `mfa_backup_codes` table (user_id FK, Argon2id `code_hash`, `created_at`,
  `used_at`); endpoints `POST /auth/mfa/backup-codes` (10 new codes returned in
  plaintext exactly once), `GET /auth/mfa/backup-codes` (summary), and a
  backup-code branch in `/auth/mfa/verify`. Codes are single-use, hashed, never
  stored in plaintext; generating a new set invalidates unconsumed codes.
- **Date:** 2026-09-17
- **Status:** Accepted
- **Context:** MFA TOTP was implemented (2.2/2.3) with no recovery path if the
  authenticator app is lost. The wireframes explicitly require backup codes. This
  is the one new table introduced by the Phase-2 alignment (follow the alembic
  import rule: add `features.auth.model` to `alembic/env.py` + one autogenerate
  revision).
- **Consequences:** One new table + migration; two new auth endpoints; `/auth/mfa/verify`
  accepts backup codes; `api-contracts.md` auth table updated; test coverage
  added in Phase 9 (test_auth.py). Security question (ADR-052) remains the
  password-recovery path; backup codes are MFA-recovery only.
- **Supersedes:** (none).

### ADR-055: Stateful Service Classes Are a Sanctioned Exception

- **Decision (D55):** Allow a service to be implemented as a class when it is
  stateful — when `__init__` builds per-request collaborators that every method
  would otherwise re-derive: composed `BaseCRUD` handles, settings, rate
  limiters. `AuthService` (`features/auth/service.py`) and `AdminService`
  (`features/admin/service.py`) are the clear cases; `CourseProfessorService`
  (`features/course_professor/service.py`) is retained as a borderline one
  (below). Module-level `async def` functions remain the default for everything
  else. The class is constructed per request in `api/deps.py` and reached through
  an annotated dependency (`AuthServiceDep`, `AdminServiceDep`) that receives
  `_get_db` — so the transaction boundary is unchanged and the session is still
  request-scoped.
- **Date:** 2026-09-26
- **Status:** Accepted
- **Context:** `coding-standards.md` §1.6 mandated module-level functions with
  `AsyncSession` as the first parameter and no service classes. All three Phase 1/2 services were implemented as classes
  anyway. The mandate is not arbitrary: it exists to keep services free of
  hidden state and to make the session dependency obvious at the call site.
  Measured against that intent, the three differ in how well they justify
  themselves. `AuthService.__init__` builds five `BaseCRUD` handles plus a
  settings object, and its methods reach for them constantly — as module
  functions every signature and call site would carry five extra arguments, which
  is a real readability cost, so the class earns its place. `AdminService` is the
  same shape with three handles. `CourseProfessorService` is the weakest case:
  its `__init__` stores only the session and it exposes a single `check_overlap`
  query, so a module-level function would be a near-exact drop-in. It is kept as
  a class because converting it would be a purely cosmetic change to
  contract-tested code, not because it needs the form.
- **Consequences:** `coding-standards.md` §1.6 records the exception and keeps
  module-level functions as the default, so new slices are unaffected, and the
  line calling `course_professor/service.py` "legacy" is corrected to
  "sanctioned". No ADR reverses the "no hidden state" intent: a service class
  must not cache anything across requests, and its `__init__` may only build
  per-request handles. Reviewers should prefer module-level functions unless
  `__init__` genuinely has collaborators to compose — a session alone does not
  qualify, so a new single-method service should be written as a function even
  though this one is not.
  > **Amended by ADR-058** — the "prefer a function" default is unchanged for
  > non-CRUD slices, but CRUD slices under `/admin/*` are now required to take the
  > class form with a `<Feature>ServiceDep`. Read this paragraph together with
  > ADR-058 rather than as a per-slice judgement call.
- **Supersedes:** the "no service classes" clause of `coding-standards.md` §1.6.

### ADR-056: Recovery Security-Question Storage and Enumeration Hardening

- **Decision (D56):** Three related corrections to the ADR-052 recovery flow.
  **(a) Storage.** `users.security_question_hash` stores the question **in
  readable plaintext**; only `users.security_answer_hash` is Argon2id-hashed.
  The column name is retained for schema compatibility despite holding no hash.
  **(b) Step-1 non-enumeration.** `POST /auth/forgot-password` returns a
  deterministic decoy question drawn from `SECURITY_QUESTION_POOL` for unknown
  emails instead of a null question, and always reports `set: true`.
  **(c) Step gating.** Forgot-password step 2 now returns a short-lived signed
  `type="recovery"` grant (`recovery_token`, 5-minute expiry) and a
  `forget_password` OTP cannot be minted without it.
- **Date:** 2026-09-26
- **Status:** Accepted
- **Context:** ADR-052 mandated a 4-step recovery flow and said the answer is
  "Argon2id-hashed", but the docs were internally inconsistent.
  `security-model.md` and `database-er.md` implied the *question* was hashed
  too, while `wireframes.md:195` and `api-contracts.md:1052` require step 1 to
  return the question so the user can read it at step 2. A hash cannot satisfy
  that, so one of the two requirements had to give. Independently, the original
  step 1 returned `{question: null, set: false}` for unknown emails and the real
  question for known ones, which `api-contracts.md:1064` explicitly forbids
  ("responds identically for unknown emails to avoid enumeration") — same shape,
  different content, so still enumerable. Separately, nothing enforced that step 2
  had been passed: step 3 (`/auth/otp/request` with `purpose=forget_password`) was
  ungated and step 4 accepted the OTP alone, so the "mandatory" security-question
  gate and its 3-attempt cap could both be skipped by anyone with inbox access.
- **Rationale for (a):** the answer is the secret, not the question. The question
  is non-secret by design — it is displayed to the user and is drawn from a small
  preset pool in the settings UI (`wireframes.md:292-294`). Hashing it would
  protect nothing and would make step 2 impossible, so the plaintext question is
  accepted as a documented exception and the misleading column name is called out
  in `database-er.md` instead.
- **Rationale for (b):** the decoy is keyed with an HMAC of the normalized email
  over `SECURITY_QUESTION_POOL`, so it is **deterministic, not random**. A random
  decoy would itself become a reliable enumeration oracle, because repeated
  requests to one address would return different questions while a real account's
  question stays fixed; it would also change under a legitimate user who retried
  after a typo. `set` is now always `true` because ADR-052 made the question
  mandatory at registration, so the "no question on file" population is empty in
  greenfield and the field was only a leak channel. Users who mistype their email
  now get three identical `security_answer_invalid` errors instead of a "no
  question on file" message, which is no worse and closes the oracle.
- **Rationale for (c):** possession of the `forget_password` OTP is what
  authorises step 4, so minting the OTP is the only point the gate must be
  enforced — this keeps `/auth/reset-password` unchanged. The grant carries a
  `type` claim and is therefore already rejected by the access-token dependency,
  so it cannot be replayed for API access. A bad or mismatched grant returns the
  generic `invalid_credentials` 400 rather than a distinct error, so the gate is
  not itself probeable.
- **Consequences:** `RecoveryGrantResponse` is a new response schema and
  `/auth/forgot-password/verify` returns 200 instead of 204; `api-contracts.md`
  and `security-model.md` are updated to match. `users.security_question_hash` is
  annotated in `database-er.md` as readable-by-design. The `set` field of
  `SecurityQuestionResponse` no longer carries information. Rejected at the gate
  is reported with the generic message to preserve non-enumeration.
- **Deferred:** sending the question by email instead of returning it would close
  the enumeration surface completely, since step 1's response could then be a
  constant. That is the stronger design and is worth revisiting, but it changes
  the step-2 screen in `wireframes.md:184-209`, so it is out of scope here.
- **Supersedes:** the "stored hashed" claim for the security question in
  `security-model.md:104`.

### ADR-057: Phase 3 Admin Routing, Enrollment Mount, and Archive Delete

- **Decision (D57):** Four routing and deletion decisions for the Phase 3
  `/api/admin/*` mounts, made during Phase 1/2 verification after the original
  Phase 3 plan was found to conflict with the routers already mounted.
  **(a) No re-mounting of student/professor routers.** Admin student and professor
  CRUD go in NEW modules `features/student/admin_router.py`
  (`APIRouter(prefix="/admin/students")`) and `features/professor/admin_router.py`
  (`APIRouter(prefix="/admin/professors")`). The existing
  `features/student/router.py` (`/student`) and `features/professor/router.py`
  (`/professor`) stay mounted and keep their prefixes.
  **(b) `features/enrollment/router.py` stays permanently unmounted.** Bulk-enroll
  and the offering roster read are routes of the offerings router, since the
  contract nests both under `/admin/offerings/{oid}`. The stub is retained for
  slice-count parity and carries a comment saying so.
  **(c) Face enrollment becomes its own slice**, `features/face_enrollment/` at
  `/admin/face-enrollment`, with no `model.py` and no migration.
  **(d) Archive hard delete gains a has-records guard** returning
  `409 student_has_records` / `409 professor_has_records`; the RESTRICT foreign
  keys are left alone.
- **Date:** 2026-09-26
- **Status:** Accepted
- **Context:** Phase 3 is the first phase to add routers under `/api/admin/*`,
  and the original plan's wording was written before the Phase 1/2 routers were
  mounted, so it no longer matched the code. Four concrete failures would follow
  from implementing it literally. (1) It says to mount "the student,
  professor ... routers" — but `student/router.py` and `professor/router.py` are
  already mounted, and because paths inside a router are relative to its own
  prefix, mounting them again under `/api/admin` would publish
  `/api/admin/profile`, `/api/admin/schedule`, `/api/admin/courses` and
  `/api/admin/sessions`, none of which the contract defines. (2) It also says to
  mount the `enrollment` router, but the contract has no enrollment mount point
  at all; both enrollment endpoints are nested under offerings. (3) It calls face
  enrollment "additions to the student feature", yet
  `/admin/face-enrollment` is a third mount point that fits neither the student
  router nor the admin student router. (4) Its permanent delete checks only
  `is_active`, but `enrollments`, `attendance_records` and `excuse_requests`
  all reference `students.id` with `ondelete="RESTRICT"` (as does `sessions` ->
  `professors`), so deleting almost any real archived student raises a PostgreSQL
  FK violation and returns 500 — a state the contract does not document.
- **Rationale for (a):** the router-per-mount-point rule from ADR-055's sibling
  guidance already covers this, but the plan named the wrong module, and the
  failure is silent — FastAPI raises no error for a duplicated mount, it just
  serves the wrong paths. Guard comments in the two mounted modules and the
  explicit six-router mount list in `src/api/router.py` make the intent
  unmissable.
- **Rationale for (b):** inventing `/api/enrollments` would create an undocumented
  surface that no contract, wireframe, or test covers. Deleting the stub was
  rejected because the 14-slice layout is referenced in `AGENTS.md` and
  `project-structure.md`; an inert, clearly-commented stub is the lower-cost
  option.
- **Rationale for (c):** a slice with no model is already precedented —
  `course_professor` owns only a join table's logic, and Phase 3's face work is
  entirely derived from `Student.face_embedding`/`face_enrolled_at`/
  `face_embedding_version`. Because there is no model, no
  `import features.face_enrollment.model` line is added to `alembic/env.py`.
  Enrollment status is read as `face_embedding IS NULL`, because archiving a
  student is a revocation step: it sets `face_embedding = NULL` and bumps
  `face_embedding_version`.
- **Rationale for (d):** relaxing the FKs to `CASCADE` would make the delete
  succeed by destroying `attendance_records` — unacceptable for an attendance
  system, where those rows are the audit trail. An honest 409 tells the admin why
  the record cannot be removed; the RESTRICT constraints stay as the last line of
  defence even if the guard is bypassed.
- **Consequences:** `course/router.py` gains `prefix="/admin/courses"` and documents
  its sibling `course/offering_router.py`; `enrollment/router.py`, `student/router.py`
  and `professor/router.py` carry "do not re-mount" comments. Phase 3 needs **no
  migration** — every column it reads already exists. The new
  `student_has_records` / `professor_has_records` error codes are added to
  `api-contracts.md` in the ADMIN Endpoints archive-delete sections, which
  documented only `409 not_archived`.
- **Deferred:** `scan_count`, `course_count`, `year_level_count`, `terms_count` and
  `enrolled_count` are all computed per request. At Phase 3 volumes this is fine,
  but if the offerings or admin student lists grow large these become N+1 sources
  and should move to a cached aggregate (the `shared/cache.py` helper already
  exists) or a materialised view. Note `terms_count` reads the `"terms"` key of
  the `term_structure` JSONB column, whose shape is `{terms: [{code, label}]}`.
- **Supersedes:** the original Phase 3 routing plan for `/api/admin/*` — the
  router list, the "additions to the student feature" placement of face
  enrollment, and the archive-delete guard — as realised in `src/api/router.py`
  and the archive-delete error codes in `api-contracts.md` §ADMIN Endpoints.

### ADR-058: Admin CRUD Slice Template

- **Decision (D58):** The `/api/admin/*` CRUD slices of Phase 3 are built from one
  template instead of restating the shape per slice.
  **(a) Service classes are the standing form for CRUD slices.** A slice whose job is
  create/read/update/archive for one or two models (`program`, `course`,
  student-admin, professor-admin) implements `class <Feature>Service` whose `__init__`
  takes the request `AsyncSession` and builds one `BaseCRUD` handle per model it
  touches, and is reached through an annotated `<Feature>ServiceDep` in
  `api/deps.py`. It is a rule about the slice family, not a judgement call to
  re-argue per slice. Non-CRUD slices keep module-level functions.
  **(b) Each slice carries a `constants.py`.** Slice-specific field bounds live
  there; the list-query bounds (`DEFAULT_PAGE`, `DEFAULT_PAGE_SIZE`, `MAX_PAGE_SIZE`,
  `SEARCH_MAX_LENGTH`) live in `shared/pagination.py` and are imported rather than
  restated per slice. `features/admin/constants.py` re-exports the four so the existing
  admin routes keep their imports.
  **(c) A list endpoint may add one optional filter the contract omits.** Programs
  gets `?search=` (ilike over `code`/`name`) for the wireframe 4.5a search box. It
  must be optional, default `None`, length-capped, and recorded in
  `api-contracts.md`; a *required* undocumented parameter is not allowed.
  **(d) A soft archive touches only its own row.** `DELETE /admin/programs/{id}` sets
  `programs.is_active = False` and nothing else.
  **(e) Derived aggregates are computed per request in Python**, one query per parent
  row, with the N+1 accepted at Phase 3 volumes (already deferred by ADR-057).
  **(f) A slice is not mounted in its own session** — `api/router.py` is edited once,
  by the mount session.
- **Date:** 2026-09-26
- **Status:** Accepted
- **Context:** The Phase 3 work plan gave two conflicting instructions about service
  form. Its phase header said to copy `AdminService` ("class-based `AdminService`
  holding a `BaseCRUD` per model"), which describes a class, while ADR-055 and
  `coding-standards.md` §1.6 recorded module-level functions as the default for new
  slices and told new slices to prefer functions. Five sibling slices (3.1-3.5) were
  about to be implemented by five different sessions, so leaving the choice open would
  have produced a different answer in each one and a codebase split down the middle.
  The same header also listed a `constants.py` only in passing, said nothing about the
  wireframe search box, and inherited a contract sentence that cannot be implemented.
- **Rationale for (a):** ADR-055's criterion — a class earns its place when `__init__`
  builds per-request collaborators every method would otherwise re-derive — is met by
  every one of these slices: each composes `BaseCRUD` handles for the models it
  touches. Generalising the rule from "judge each slice" to "CRUD slices take this
  form, other slices take the other form" makes the choice mechanical, and ADR-055's
  default is preserved everywhere it actually applies. `CourseProfessorService` stays a
  class as ADR-055 already retained it; the new rule does not require reverting it,
  because ADR-055 explicitly declines cosmetic changes to contract-tested code.
- **Rationale for (b):** pagination limits apply to every list route in the app, so they
  do not belong to a feature slice. The first draft of this ADR pointed at
  `features/admin/constants.py` — where the bounds already lived — on the reasoning that
  reusing them beat writing three copies of `MAX_PAGE_SIZE` that could drift apart. That
  was half right: it avoided the duplication and made the `admin` slice the de-facto shared
  module for a cross-cutting concern, which is the wrong dependency direction and would have
  been repeated by all five Phase 3 slices. Moving the four bounds to `shared/pagination.py`
  — next to `PaginatedResponse` and `paginate_query`, which already speak that vocabulary —
  and re-importing them in `admin/constants.py` gives one home, zero route edits, and no
  feature-to-feature import. `NAME_MIN_LENGTH` / `NAME_MAX_LENGTH` were deliberately left in
  `admin/constants.py`: they are not cross-cutting yet, and promoting them is the trigger for
  a `shared/constants.py` rather than something to do pre-emptively. The same review removed
  `shared/dependencies.pagination_params`' private `le=100` ceiling, which silently
  disagreed with admin's 200 — the two constants now have one value.
- **Rationale for (c):** the wireframes show a search box on the Programs table that
  the contract's query line omits. Dropping the filter would have left the documented
  screen unbuildable; adding it as a required parameter would have invented a contract.
  One optional, documented filter is the smallest thing that satisfies both, and the
  cap reuses `SEARCH_MAX_LENGTH` so a `?search=` cannot become an unbounded `ilike`.
- **Rationale for (d):** `api-contracts.md:146` said the program archive "cascades
  year-levels/courses inactive", but that sentence predates D44: `year_levels` has no
  `is_active` column, and `courses` is a decoupled template with no program FK at all
  (the program FK lives on `course_offerings`). The only implementable action is
  flipping the program's own flag, and archiving the program's offerings was rejected
  because the contract never says so and an admin who archives a program to hide it
  from a picker would not expect the term's offerings to disappear. The contract line is
  corrected rather than implemented, because writing a cascade would be inventing
  behaviour the schema cannot express.
- **Rationale for (e):** the aggregates are `COUNT`/`len` over related rows, computed
  per request. Building a grouped aggregate query now would add JSONB shape assumptions
  (the `{"terms": [...]}` key) to SQL before the first data exists to justify them, and
  a materialised view needs a backfill plus a refresh path. ADR-057 already deferred this
  to the point where the lists grow; the trigger for revisiting is unchanged — a cached
  aggregate via `shared/cache.py`, or a materialised view.
- **Consequences:** `coding-standards.md` gains §1.8 (the template) and rewritten
  §1.5-§1.7;   `AGENTS.md`'s service-class and Phase 3 rows follow it; the Phase 3 header
  in the work plan states the same rules; and
  `api-contracts.md`'s Programs section gains `?search=`, the aggregate-derivation note,
  and a corrected archive description. `api/deps.py` gains one `_get_<feature>_service`
  plus one `<Feature>ServiceDep` alias per slice. No migration, and no change to
  ADR-055's default outside the CRUD family.
- **Deferred:** `terms_count` and `course_count` remain per-request; the revisit
  trigger is the same as ADR-057's, plus one more — once every Phase 3 slice ships,
  the derived-aggregate code is a candidate for a single shared helper, since the shape
  (count + page + per-row aggregates) is identical across slices.
- **Extends:** ADR-055 (service classes) and ADR-057 (Phase 3 routing, aggregates,
  archive semantics). ADR-055's module-level default continues to govern every
  non-CRUD slice.
- **Supersedes:** the stale "cascades year-levels/courses inactive" sentence in
  `api-contracts.md` §Programs, and the implicit permission to re-decide service form
  per Phase 3 slice in the work plan.

### ADR-059: Face Enrollment Takes the Class Form

- **Decision (D59):** The `face_enrollment` slice implements
  `class FaceEnrollmentService` — `__init__` takes the request `AsyncSession` plus
  an optional `Settings` (falling back to `get_settings()`) — reached through
  `FaceEnrollmentServiceDep` in `api/deps.py`, with the long method names kept
  (`get_face_enrollment_status`, `enroll_face`, `revoke_face_enrollment`).
- **Date:** 2026-09-27
- **Status:** Accepted
- **Context:** ADR-055 allows a class when `__init__` composes per-request
  collaborators every method would otherwise re-derive (its examples: composed
  `BaseCRUD` handles, settings, rate limiters), and ADR-058 kept module-level
  functions as the default for non-CRUD slices. The slice was first sketched in
  the functional form, but every one of its methods reads request-scoped settings
  (upload size caps, the stub embedding version), so the functional form threaded
  a settings argument through every signature and call site — the same readability
  cost ADR-055 accepted for `AuthService` — while every mounted admin router
  already speaks the `*ServiceDep` form.
- **Rationale:** the class earns its place under ADR-055's own criterion: settings
  composition, not the session alone, is what qualifies it. Keeping the long
  method names preserves the slice's public vocabulary and keeps the router and
  tests a mechanical call-shape change. Generalising further (e.g. re-deciding
  other non-CRUD slices) is out of scope: this is a per-slice exception taken at
  explicit direction, and the module-function default stands everywhere else.
- **Consequences:** `coding-standards.md` §1.6 drops `face_enrollment` from the
  module-function examples and records the exception; `AGENTS.md`'s service-class
  row follows. `api/deps.py` gains `_get_face_enrollment_service` plus the
  `FaceEnrollmentServiceDep` alias. No migration, no mount change, no contract
  change.
- **Extends:** ADR-055 (service classes) and ADR-058 (admin CRUD slice template).
  ADR-055's module-level default continues to govern the remaining non-CRUD
  slices (`shared/csv_import.py` and any future ones).
- **Supersedes:** the application of ADR-058 (a)'s "non-CRUD slices keep
  module-level functions" clause to `face_enrollment` only.

### ADR-060: Contract Conformance Audit — Pagination Default and `overlapping_assignment` Status

- **Decision (D60):** Two §1.8/`api-contracts.md` conformance corrections, both
  resolved in the contract's favour: `shared/pagination.py`'s `DEFAULT_PAGE_SIZE`
  becomes `20` (was `50`), and `OverlappingAssignmentException` becomes `409`
  (was `422`).
- **Date:** 2026-09-30
- **Status:** Accepted
- **Context:** An audit of all 12 mounted routers (78 operations, 57 paths)
  against §1.8 of `coding-standards.md` and `api-contracts.md` confirmed the
  structural rules hold: every collection route is declared `""` rather than
  `"/"`, all 45 `/admin/*` routes carry a role guard (`/admin/users` on
  `SUPER_ADMIN` per the contract, the other 42 on `ADMIN` — 62 role-guarded
  routes in total, plus 15 under `/auth` and `/health`), all 14 paginated routes
  source their bounds from `shared.pagination` with `ge=1` / `le=MAX_PAGE_SIZE`,
  404s fold the id into the message, and 409s reuse existing class names. Two
  value-level drifts survived that check. `DEFAULT_PAGE_SIZE` was `50` while
  `api-contracts.md` documents `?page=1&size=20` in 14 places, so every list
  endpoint defaulted to 2.5× the documented page size; the frontend already sends
  `20` and no test pinned the constant. `OverlappingAssignmentException` inherited
  `CourseProfessorDomainException` (422) while the contract documents
  `409 overlapping_assignment` — and §1.9 lists it among the 409 class-name-reuse
  examples. `api-contracts.md` is the source of truth for both, so the code moves.
- **Rationale:** For the status, follow the convention every other 409 in the
  codebase already uses (`ProgramCodeExistsException`, `YearLevelHasCoursesException`):
  keep the slice's `DomainException` parent and set `status_code` explicitly,
  rather than re-parenting onto `DatabaseException`. `CourseProfessorDomainException`
  has no other subclass, so nothing else moves. For the page size, the constant is
  a single named value reached through 6 slice `constants.py` re-exports and 14
  routers, so one edit propagates everywhere — the ADR-058 re-export shape is
  exactly what makes this a one-line fix.
- **Consequences:** One literal in `shared/pagination.py`; the OpenAPI default for
  `size` becomes `20` across all 14 paginated endpoints. `course_professor/exceptions.py`
  gains an explicit `status_code: int = 409` and a corrected docstring. No new
  exception classes, no role-guard changes, no router path changes, no migration,
  no OpenAPI response-shape change (`{items, total, page, size}` is unchanged — only
  the default window moved). `test_offering_service.py` asserts only `exc.code`, so
  the status change is test-safe. Two `size: 50` values remain in mock-fixture
  response bodies in `frontend/src/lib/api/endpoints.ts` — cosmetic, since wire
  requests already send `20`.
- **Deferred:** Three groups of contract-documented behavior remain unimplemented
  and are reported rather than fixed, since closing them would mean adding new
  exception classes: face enrollment's `400 no_face_detected`, `400 multiple_faces`,
  and `422 quality_too_low` (contract line 333 — detection runs client-side via
  MediaPipe, so the backend has no detector to fail); bulk enroll's
  `422 validation_error` (line 309 — per-row errors are folded into the 201 body
  instead); and the three admin reset-password endpoints
  `POST /admin/users/{id}/reset-password`,
  `POST /admin/students/{id}/reset-password`, and
  `POST /admin/professors/{id}/reset-password` (lines 674-676 — only
  `/auth/reset-password` ships).
- **Extends:** ADR-058 (whose §1.9 states the 404 fold-the-id and 409-reuse-the-name
  rules this audit checked) and ADR-059.
