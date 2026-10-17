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

  > **Superseded by ADR-070, 2026-10.** The closing sentence above never
  > held: all 15 `features/*/service.py` modules are service classes, and the
  > tree contains no module-level-function service. What actually governs is
  > the rule of thumb in `coding-standards.md` §1.7 — a class earns its place
  > when `__init__` composes multiple per-request handles (CRUD, settings,
  > limiters) — so (a)'s reasoning extends by the same test to slices it did
  > not name: `AdminService` (3 `BaseCRUD`), `DashboardService` (5 injected
  > services), `ExcuseService` (2 `BaseCRUD`), and `SystemService` /
  > `AttendanceService` (session + `Settings`, ADR-059's shape). ADR-070 widens
  > that test — composing handles is sufficient, not necessary — which settles
  > the last three (`AnalyticsService`, `ReportsService` and
  > `CourseProfessorService`, of which ADR-055 had already flagged the last as a
  > borderline holdover) without needing an exemption for any of them. Clause (b)
  > is unaffected and still accurate: the pagination bounds do live in
  > `shared/pagination.py`, re-exported per slice.
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
  `/auth/reset-password` ships). A fourth: `resolve_review` raises
  `AttendanceDomainException(code="invalid_decision")` inline, with no class in
  `exceptions.py` and no `api-contracts.md` entry, which breaks §1.6's "codes
  come from the contract and are never invented" rule the same way ADR-060
  corrected `overlapping_assignment`. It is left as-is because giving it a class
  would add surface the contract has not asked for, and because the call was
  extracted into `_resolve_approved_status` in the same change that noted it,
  so the next reader sees the fix's scope in one place.
- **Extends:** ADR-058 (whose §1.9 states the 404 fold-the-id and 409-reuse-the-name
  rules this audit checked) and ADR-059.
### ADR-061: Excuse Authorization Is the Teaching Assignment, Not Session Ownership

- **Decision (D61):** Any professor holding an effective `course_professors`
  assignment for the session's offering may act on that session's excuses. The
  `session.professor_id == professor.id` check is removed from every professor
  path in `features/excuse/service.py` — quick-excuse, with-evidence,
  excuse-all-absent, review, edit, and revoke — leaving
  `_require_assignment` as the sole gate. `list_for_professor` is rescoped
  from "sessions this professor owns" to "sessions on offerings this professor
  is currently assigned to".
- **Date:** 2026-10-02
- **Status:** Accepted
- **Context:** The slice contradicted itself. `excuse-workflow.md` §8 (and the
  `request_submitted` copy in `notifications.py`) name the recipient as the
  offering's "assigned professor(s)", and
  `test_submit_also_notifies_a_co_teacher` pins that a co-teacher is mailed;
  the mail then tells the recipient to "Review the request and approve or reject
  it". But `review_excuse` resolved its session through `_get_owned_or_404`, so
  that same co-teacher received `404 session_not_found` on the review route and
  could not act on what they had just been asked to handle. §2.1 and §3 state
  the precondition for all three paths as "professor has active assignment for
  the course", with no ownership clause. D21 assigns the approve/reject decision
  to "professor" without naming which one. The gap was an extra guard nobody
  documented: the decision log had no entry for it, and the requirement's own
  wording contradicted it.
- **Rationale:** Assignment is the term the design docs use, and it is already
  enforced — every method called `_require_assignment` immediately after the
  ownership lookup, so the fix removes a redundant layer rather than a check.
  Ownership is also the wrong invariant for a shared assignment: `sessions`
  records one `professor_id`, so a co-taught session silently belongs to
  whichever professor opened it, and the other is not a second-class professor.
  The alternative — narrowing the recipient list to the session owner — was
  rejected because it would contradict §8 and the existing co-teacher
  notification test, and because a queue scoped to owned sessions would hide
  from an authorized reviewer the very requests they can act on. The list uses
  an `EXISTS` subquery on the assignment rather than a join, since a professor
  can hold several assignments on one offering and a join would repeat every
  request once per row.
- **Consequences:** `_get_owned_or_404` is deleted; `_get_session_or_404` and
  `_require_assignment` remain and are now the whole authorization story for the
  slice. The failure mode for a professor outside the teaching team changes
  from `404 session_not_found` to `403 not_assigned`, which is the more accurate
  answer and the one §2.1 already implies. Any co-teacher can now quick-excuse,
  bulk-excuse, revise and revoke on a shared session, and `excused_by` /
  `reviewed_by` record whoever actually acted, so the audit trail still names a
  real actor. `list_for_professor` returns more rows than before for a
  co-teaching professor, which is the intended effect. No route, schema, enum,
  migration or OpenAPI response-shape change; the exception classes and their
  codes are unchanged.
- **Known asymmetry:** *(resolved by ADR-062.)* `features/session/service.py`
  originally scoped `get_active_session`, `close_session`,
  `list_professor_sessions`, `get_session_history` and `get_professor_attendance`
  to `Session.professor_id == professor.id`, so a co-teacher could act on a
  shared session's excuses but could not open its live view, close it, or find
  it in `GET /professor/sessions`. ADR-062 widens all five on the same
  assignment basis.
- **Testing:** `test_a_coteacher_can_approve_a_request` and
  `test_a_coteacher_sees_the_request_in_their_queue` pin the widened access,
  and `test_an_unassigned_professor_cannot_approve` /
  `test_a_lapsed_assignment_cannot_approve` /
  `test_an_unassigned_professor_sees_an_empty_queue` pin that it is still an
  assignment check — an unassigned or lapsed professor gets `403 not_assigned`
  and no queue entries. All four fail against the ownership-gated code.
- **Extends:** ADR-020 and ADR-021 (the excuse state machine and the three
  initiation paths, neither of which names an owning professor).
### ADR-062: Session Access Is Attribution Plus Teaching Assignment

- **Decision (D62):** `Session.professor_id` is attribution, not authorization.
  All five professor-facing session surfaces in `features/session/service.py` now
  admit a professor who either opened the session or holds a current
  `course_professors` assignment on its offering: `get_active_session`,
  `close_session`, `list_professor_sessions`, `get_session_history`, and
  `get_professor_attendance`. The column is never written, so history stays
  attributed to whoever opened the session. A professor with neither claim gets
  the existing `404 assignment_not_found`.
  The live-action pair (`get_active_session`, `close_session`) resolves through a
  new `_get_scoped_or_404`. The three historical reads (`_sessions_stmt`,
  renamed from `_owned_sessions_stmt`, and `_attendance_stmt`) scope with a
  `Session.professor_id == professor_id OR EXISTS(...)` union.
- **Date:** 2026-10-02
- **Status:** Accepted
- **Context:** This resolves the asymmetry ADR-061 recorded rather than left
  standing, and applies the same reasoning to the slice that was holding it up.
  Three facts made the ownership rule indefensible on its own terms.
  **(a) The column is documented as attribution.** `admin-manual.md` §4.2 says
  "the system attributes each _session_ to the professor who opened it", and D8
  states "History is never rewritten. Sessions opened by Professor Smith remain
  under Professor Smith's name" - a rationale for keeping the column, not for
  gating reads on it. **(b) The contract states no such rule.** None of the five
  endpoints in `api-contracts.md` carries a scope sentence; the only mention
  anywhere in `docs/architecture/` was the compressed role row at
  `security-model.md:94`, which merges "own courses" (assignment-backed) and
  "own sessions" (ownership-backed) into one phrase - plausibly where the drift
  started. **(c) The frontend has always been assignment-scoped and could not
  have implemented ownership anyway.** `GET /professor/courses`, the
  create-session selector ("Your active assignments this term", wireframes.md
  §3.2a), the attendance filters ("Cross-session roster across your courses")
  and the history header ("Past sessions across your courses") are all
  assignment-based, while no professor id appears in any of the six response
  DTOs, so the frontend has no data with which to compare identity. The backend
  was the only party holding a concept nothing else shared.
- **Rationale:** Two different rules for the two kinds of surface, because they
  answer different questions. The live-action pair is about *now*, so ownership
  first and assignment only when that fails is both correct and cheap - the
  common case stays a single row fetch. The historical reads are about the past,
  where the assignment window is the wrong tool: `_require_assignment` is
  anchored to `date.today()`, so scoping on assignment alone would empty a
  professor's own history the day that assignment's `effective_to` passes, which
  is precisely what `Session.professor_id` exists to prevent. Hence a union for
  reads and a fallback for actions. The `EXISTS` is built inline in the calling
  statement rather than as a separate query, both to avoid repeating rows for a
  professor holding several assignments on one offering and to keep the read
  paths at one round-trip each. `close_session` is widened deliberately: the
  Close control is rendered unconditionally (`active/[id]/+page.svelte:309-316`,
  gated only on status) and drawn unconditionally in `wireframes.md` §3.3, and
  since `SessionAlreadyActiveException` is per-offering (`service.py:195-208`,
  with no professor term), a co-teacher running a shared class has no other way
  to end the window they were handed.
- **Divergence from ADR-061:** the excuse slice reports a missing assignment as
  `403 not_assigned` (`ProfessorNotAssignedException`) while this slice reports
  `404 assignment_not_found` (`OfferingAssignmentNotFoundException`). Same
  semantic failure, two codes, in adjacent slices. This is historical accident
  rather than design - the excuse slice needed a 403 and had no class to reuse,
  while the session slice already had `_require_assignment` raising this one and
  `api-contracts.md:323` already documents the code. Reusing it keeps this
  change to zero new exception classes and zero new documented errors.
  Unifying the two is a named follow-up; it was not done here because it would
  churn the excuse slice's just-landed behaviour and its 403 assertions for no
  behavioural gain.
- **Consequences:** `_get_owned_or_404` is deleted. `_sessions_stmt` and
  `_attendance_stmt` become instance methods so they can reach the shared
  `_assigned_offering_clause`. A co-teacher's session list and ledger now agree,
  which is what the frontend's `ensureDirectory()` join needs - it builds a
  `session_id` -> offering directory from `listSessions()` and joins the ledger
  onto it, so widening only one of the pair would have left rows rendering as
  em dashes. Two OpenAPI summaries no longer say "own". No route, schema, enum,
  migration or response-shape change; 65 paths and 89 operations before and
  after. `ProfessorProfileRead.session_count` and the professor archive
  hard-delete guard (`professor/service.py:392-402, 448-455`) remain
  ownership-scoped, which is correct: a profile total should describe the
  professor's own sessions, and the archive guard is a safety check.
- **Testing:** `test_a_coteacher_can_close_a_shared_session`,
  `test_get_active_session_admits_a_coteacher` and
  `test_a_coteacher_sees_the_shared_sessions` pin the widening - the last
  fails against the previous code. `test_get_active_session_rejects_a_professor_outside_the_team`,
  `test_close_session_rejects_a_professor_outside_the_team`,
  `test_a_lapsed_assignment_cannot_close_a_session` and
  `test_session_list_excludes_a_professor_outside_the_team` pin that it is still
  an assignment check. `test_past_sessions_stay_visible_after_an_assignment_ends`
  and `test_a_lapsed_assignment_stops_showing_shared_history` pin the union
  boundary in both directions and are the guards against replacing ownership
  with assignment instead of widening it.
- **Extends:** ADR-061 (whose Known-asymmetry bullet this resolves) and D8.

---

## 8.1 Background Jobs

### ADR-063: The API Process Owns the Nightly Cron Jobs

- **Decision (D63):** The nightly risk batch and the nightly full backup are
  scheduled inside the FastAPI process by APScheduler, started and stopped by
  the application lifespan. Each job body is a thin adapter in the feature that
  owns the work, and each adapter owns its own transaction.
- **Date:** 2026-10-03
- **Status:** Accepted
- **Context:** `RISK_BATCH_CRON` has been in `core/config.py` since the
  analytics slice landed, and the backup pipeline's own docstrings have
  anticipated a scheduler job, but nothing actually fired either one — both ran
  only when an admin triggered them by hand. `risk-model.md` §5 and
  `monitoring.md` §3-4 both describe nightly automation and both document a
  backup-freshness SLO that nothing could satisfy. The deployment plan is a
  single API process, so an external worker (Celery, a cron-on-the-host) would be
  a second moving part to operate for two jobs.
- **Rationale:**
  - **Two wrappers, not two bare calls.** `run_risk_batch` and
    `SystemService.run_backup` only ever `flush()`; the request dependency
    commits on the way out. A cron run has no request, so each adapter opens
    `database.get_session()` (which commits nothing) and commits itself.
    Calling the service functions directly from a job would silently discard
    every row it wrote — the worst possible failure mode, since the job would
    log a healthy-looking summary.
  - **Adapters live in their features, the scheduler does not.**
    `core/scheduler.py` imports nothing from `features` or `shared`, preserving
    the stdlib → third-party → core → shared → features ordering. The job bodies
    sit next to the code they run (`analytics/batch.py`,
    `system/service.py`) and `main.py` — which already imports every feature via
    `api.router` — wires them together.
  - **A failed job must not take the scheduler down.** Both adapters catch,
    log and return. A night is lost either way; the process dying would lose
    tomorrow as well.
  - **A malformed cron raises at boot.** The trigger is built during
    `register()`, so a typo in `RISK_BATCH_CRON` fails where an operator is
    watching the log, rather than becoming a cron that silently never fires.
  - **The unconfigured backup is skipped, not failed.** With no
    `BACKUP_ENCRYPTION_KEY` the pipeline cannot succeed. Letting it fail would
    write a `failed` `backup_log` row every night until someone noticed, and the
    real failures would drown in the noise. The adapter preflights and logs one
    CRITICAL line instead, leaving `run_backup` itself untouched so a manual
    trigger still fails loudly and visibly on its row.
- **Known limitations, stated rather than inherited:**
  - **Process-local, single instance.** Neither the in-flight set nor the backup
    lock crosses processes, exactly like the scan idempotency store and the rate
    limiter. Running more than one worker process would fire every job once per
    process. `Dockerfile.dev` passes no `--workers`, so this holds today; a
    shared job store or a Postgres advisory lock is the fix and is not in place.
  - **The nightly backup needs system binaries.** The pipeline shells out to
    `pg_dump`, `gzip` and `openssl`. The dev image installs none of them, and
    the sample production `Dockerfile` in `deployment-workflow.md` installs no
    system packages at all, so on that image the nightly backup fails with
    `backup_failed`. The image belongs to the deployment work, not here; noted
    in `production-checklist.md`.
  - **`SCHEDULER_TIMEZONE` defaults to UTC**, which is what a container without
    a configured `TZ` already was. `risk-model.md` says "02:00 server time", so
    this is a clarification, not a change. An unresolvable zone warns and falls
    back rather than failing the boot: a cron that never fires is a silent
    data-loss bug, and a slim image may ship without the tz database.
- **Divergence from the backup endpoint:** `POST /admin/backups` declares
  `202 Accepted` but fully awaits the pipeline before responding
  (`features/system/router.py`). Left alone — the scheduled path and the manual
  path share `run_backup`, so making the endpoint fire-and-forget is a contract
  change and a separate decision.
- **Consequences:** One `AsyncIOScheduler` per process, with
  `max_instances=1` (a slow run is skipped, not stacked) and `coalesce=True` (a
  backlog of missed fires collapses into one). `start`/`shutdown` are idempotent
  and `register` replaces by name — `uvicorn --reload` re-enters the lifespan on
  every file save, and APScheduler's `replace_existing` flag does not dedupe
  jobs added before `start()`. Shutdown stops the scheduler with `wait=False`,
  then cancels in-flight job tasks under a bounded timeout, and only then
  disposes the engine: returning first would leave a job holding a connection
  that is about to be closed underneath it. `core/scheduler.py` exposes
  `scheduled_job_running()` for the admin maintenance endpoints' concurrency
  guard; it reports scheduled runs only, so it composes with
  `is_backup_running()` (which also sees manual triggers) rather than replacing
  it. No new route, no new model, no migration: OpenAPI is unchanged at 84 paths
  / 110 operations. `RISK_BATCH_WORKERS` remains unread dead config.
- **Testing:** `tests/features/system/test_scheduler.py` (20 cases) pins job
  registration from both crons, idempotent `start`, teardown emptying
  `get_jobs()`, `SCHEDULER_ENABLED=false` registering nothing, a malformed cron
  raising at registration, timezone fallback, in-flight tracking clearing on
  raise, shutdown cancelling a running job without hanging, the drain refusing
  to cancel its own caller, and both adapters committing their rows — which is
  the assertion that fails against the direct-call version. The retention test
  seeds three rows because pruning deliberately never leaves fewer than two.

## 8.2 Audit Trail

### ADR-064: The Audit Vocabulary Is an Enum, Not a Database Constraint

- **Decision (D64):** `audit_logs.action` and `audit_logs.entity_type` stay
  free-form `String(50)` columns, constrained in code by two `StrEnum`s
  (`shared/enums.py::AuditAction`, `AuditEntity`) that `record_audit` is typed
  against and that the reader endpoint validates filters with. Writes cover
  every sensitive mutation across all slices, and are read through one new
  endpoint, `GET /admin/audit-logs`.
- **Date:** 2026-10-03
- **Status:** Accepted
- **Context:** `audit_logs` and `shared/audit.py::record_audit` landed with the
  academic-structure work, but only `program` and `course` ever called it — six
  call sites each. Everything else the security model calls "logged" was in fact
  recorded nowhere, or only as a comment on the row itself. Two comments and one
  contract note still said "there is no audit table until Phase 8", and
  `api-contracts.md` already promised a `GET /admin/audit-logs` route that no
  router defined. The frontend has a fully-mocked audit page waiting on it.
- **Rationale:**
  - **The helper already existed; only call sites were missing.** `record_audit`
    flushes into the caller's transaction and never commits, which is what makes
    an audit row roll back with the mutation it describes. A rejected mutation
    therefore leaves no trail — correct, and asserted at every call site.
  - **An enum, not a `CheckConstraint`.** A constraint would be stronger, but it
    is a migration and a breaking change against existing rows, and it would
    make adding an action a deploy-order problem. The column stays permissive;
    the enum is the contract. `audit_logs.action` still has **no index**, so an
    `action`-only filter is a sequential scan — fine at MVP volume, and the first
    thing to add if the table grows.
  - **`entity_type` + `entity_id` is not always enough to name a row, so
    `entity_id` is nullable.** `course_professors` has a composite primary key
    and no surrogate id; the `app_setting` rows a settings PATCH writes have no
    id either; and the `import` / `enroll` rows describe a batch rather than a
    row. Those carry their identity in `old_value` / `new_value`.
  - **Batch mutations are aggregated; per-item ones are not.** A roster import
    writes one row with `imported` / `duplicates` / `errors` counts — a 400-line
    upload would otherwise bury every other action in the trail. A bulk excuse
    run writes one row per student, because each excuse is an independently
    revocable entity with its own id.
  - **Snapshots are hand-listed, never serialised generically.** Each slice has a
    `_<entity>_snapshot` static method naming exactly the audited columns. A
    generic model dump would eventually copy a password hash or an encrypted face
    embedding into a table every admin can read; the face snapshots carry
    `face_embedding_version` precisely so the blob never has to be there.
  - **A rejected filter is an error, not an empty page.** Because the columns are
    free-form, an unrecognised `entity_type` would match nothing and read as
    "no such activity" — the one conclusion an audit query must never let a
    reader draw by accident. Hence 422 `invalid_audit_filter` and
    `invalid_audit_date_range`. A *blank* filter is still "no filter", so a
    client that posts its form fields verbatim does not get a 422.
  - **`GET /admin/audit-logs` returns the stored row unaltered** — the same eight
    fields `GET /admin/system/academic-structure` already returns, and
    `AcademicStructureRead` is now a subclass of the new `AuditLogRead` so the
    two cannot drift. Nothing is derived: no `actor_name` join, no `category`
    mapping. `academic-structure` stays pinned to the four structural entity
    types; widening it would change an endpoint that already has consumers.
- **A live defect this surfaced, and fixed:** `AuthService.login` incremented
  `failed_login_attempts`, set `is_locked`, flushed, and then raised
  `InvalidCredentialsException`. `_get_db` rolls back on any exception, so
  **the counter was discarded on every failed login and the lockout threshold
  was never reached** — account lockout did not work at all. No test covered it.
  Lockout bookkeeping now runs through `_lockout_transaction`, which opens its
  own session and commits, the same shape ADR-063 gave the cron adapters. This
  is the one deliberate exception to "services only `flush()`", and it exists
  because the alternative is a security control that silently does nothing.
  `lock`, `login_failed` and `unlock` rows are written there, with
  `performed_by = None` since no actor is authenticated at that point.
- **Known limitations, stated rather than inherited:**
  - **The counter is read-then-written, not atomic.** Two concurrent wrong
    passwords for the same account can lose an increment. The row lock during
    `UPDATE` serialises the writes but not the preceding `SELECT`. Pre-existing
    in shape, but newly reachable now that the counter persists at all; the fix
    is an atomic `SET failed_login_attempts = failed_login_attempts + 1`.
  - **No admin-initiated lockout or password reset is auditable, because neither
    exists.** `api-contracts.md` documents `POST /admin/users/{id}/reset-password`
    and its student and professor equivalents; none is implemented. There is no
    admin unlock route either, anywhere in the contract. `is_locked` is only ever
    cleared by a successful login after the window elapses, or by a completed
    self-service reset. Both gaps need the endpoints first; this decision records
    them rather than inventing the surface.
  - **`change_password` is not audited**, only `reset_password`. The security
    model lists lockout and failed logins but not a self-service password change
    with the current password. Reasonable to revisit alongside the admin routes.
  - **The frontend still mocks the audit page.** Its designed response shape
    (`occurred_at` / `actor_name` / `actor_role` / `category` / `entity` /
    `detail`, in `shared/types/admin.ts`) does not match the stored columns.
    Reconciling it is a frontend change and was deliberately left out of a
    backend slice.
- **Consequences:** OpenAPI 84 → 85 paths, 110 → 111 operations. No new model,
  and no migration of its own — `audit_logs` already exists, from the
  academic-structure work (`f4a9c2b7d103`). One unrelated conformance migration
  (`b1c4e7f0a2d6`) ships alongside it; see ADR-065. 583 tests, up from 531.
- **Testing:** `tests/features/auth/test_login_lockout.py` (12 cases) is the
  regression test for the rollback defect: two of them drive
  `POST /api/auth/login` over HTTP specifically because the service-level tests
  never touch `_get_db`'s rollback and would pass against the broken version.
  `tests/features/system/test_audit_logs_http.py` (26) covers the read contract,
  including that the two audit endpoints stay scoped apart.
  `tests/features/system/test_audit_call_sites_http.py` (14) drives the mutations
  that only exist behind a route. The two pre-existing fake-session suites assert
  their own writes now that those services add audit rows.

## 8.3 Schema Conformance

### ADR-065: The Model Is the Authoritative Schema; Migrations Converge Onto It

- **Decision (D65):** `alembic check` reports no drift, repository-wide, and
  `alembic check` is the only guard that keeps it that way. When a model and an
  already-applied migration disagree, the model is right and a **new forward
  migration** reconciles the database.
- **Date:** 2026-10-03
- **Status:** Accepted
- **Context:** `alembic check` has failed on `app_settings` since Phase 12.0
  landed. Migration `e7f8a9b0c1d2` created the table with a `UniqueConstraint`
  on `key` **and** a separate non-unique index on the same column, while
  `system/model.py` declares `key = mapped_column(String(100), unique=True,
  index=True)` — which in SQLAlchemy means *one* unique index and no separate
  constraint. Three operations were reported: drop the constraint, drop the
  index, recreate the index as unique.
- **Rationale:**
  - **The constraint was the redundant half, not the model.** Postgres already
    implements `UNIQUE` as an index, so the extra `ix_app_settings_key` was dead
    weight *and* non-unique. `key` is load-bearing: `_stored_settings`
    collapses rows with `{row.key: row.value for row in rows}` and seeds missing
    keys, so duplicates would vanish silently into last-write-wins rather than
    raise. Uniqueness is now declared once, by the unique index, and verified
    enforced.
  - **Fixed forward, never by editing an applied revision.** `e7f8a9b0c1d2` has
    run in every environment that has migrated, so rewriting it forks the chain.
    `b1c4e7f0a2d6` converges instead, and its `downgrade()` restores the old
    shape exactly.
  - **Safe on existing data.** The original constraint has enforced uniqueness
    since the table was created, so no duplicate keys can exist and the new
    unique index cannot fail. Postgres DDL is transactional and alembic runs
    each revision in a transaction, so the drop-and-recreate has no window in
    which a concurrent write could slip a duplicate in.
- **Why it went unnoticed, and why no test will catch the next one:**
  `tests/conftest.py` builds the test schema with `Base.metadata.create_all`,
  straight from the models — the migration chain is never exercised by the
  suite at all. A test asserting `app_settings.key` is unique would pass
  identically against both schemas, because both are derived from the same
  model. The suite can detect a *model* bug; it is structurally incapable of
  detecting *migration* drift.
  This is why the rule needs stating. Reading `alembic/versions/` shows a
  constraint and an index; the model shows one unique index; the intuitive move
  is to reconcile by deleting `unique=True` from the model — which the suite
  would not object to, and which would leave two writers racing to insert the
  same key with nothing to stop them. **Fix the migration, never the model.**
- **Consequences:** head is `b1c4e7f0a2d6`, 9 migrations.
  `b1c4e7f0a2d6_converge_app_settings_key_index.py` is the only added migration;
  no model changed, so the 583 tests are unaffected and none of them cover it.
  There is no CI and nothing runs `alembic check` automatically, so the guard is
  manual — recorded in `AGENTS.md` rather than left to memory. **Superseded by
  ADR-069:** the `migrations` job in `.github/workflows/ci.yml` now runs
  `alembic upgrade head && alembic check` against a `postgres:16-alpine` service
  on every push and pull request, so this drift class is caught automatically
  and the rule below is enforced rather than merely documented.

### ADR-066: The Sync Flush Reconciles; It Does Not Resubmit

- **Decision (D66):** `POST /admin/system/sync/flush` confirms each pending
  `sync_queue` entry against the `attendance_records` row it names (id match
  on both sides → `done`, otherwise `failed` with another retry counted)
  instead of replaying the scan through the validation path. `POST
  /admin/system/cleanup` deletes OTP codes older than 7 days and finished
  (`done`/`failed`) queue rows older than 30 days, never touching `pending`
  rows. Both refuse with **409 `maintenance_in_progress`** while the
  maintenance lock, a backup, or a scheduled batch is active, and both write
  one aggregate audit row (`entity_type: maintenance`, `entity_id: null`,
  counts in `new_value`).
- **Date:** 2026-10-04
- **Status:** Accepted
- **Context:** The queue writer (`AttendanceService._maybe_record_sync`)
  persists the attendance row *before* enqueueing, and the payload carries
  ids only — no GPS, liveness evidence, face score, or student number — so a
  `ScanRequest` cannot be rebuilt and a true replay would only meet the
  duplicate guard it was designed to trip. Resubmission was therefore never
  available; reconciliation is the only honest semantics, and it is also the
  idempotent one: a flush interrupted mid-run simply marks the remainder on
  the next press.
- **Rationale:**
  - **Retro-failing valid history would be the inaccuracy.** A student who
    unenrolled after scanning, or a session that has since expired, must not
    fail a scan that was legitimate when taken. Only corruption (orphan,
    mismatch, unparseable payload) fails — everything else is a fact the
    server already accepted.
  - **One audit row per run, per ADR-064's batch rule.** A roster import
    writes one row with counts rather than burying the trail; a flush over a
    large backlog follows the same rule. `maintenance` is the first new
    `AuditEntity` member since the vocabulary was fixed, and it needed no
    migration: the columns are free-form by design (D64).
  - **The guard composes rather than replaces.** `scheduled_job_running()`
    sees scheduled batches only, `is_backup_running()` also sees manual
    triggers, and the new `_MAINTENANCE_LOCK` sees a second maintenance run —
    the same OR-composition the scheduler decision (D63) established.
- **Consequences:** Two new routes (`POST /admin/system/sync/flush`, `POST
  /admin/system/cleanup`), 86 OpenAPI paths, no migration. 11 new tests in
  `tests/features/system/test_maintenance_http.py` (594 total, all passing).
  The prune helper is the implementation the future cleanup-job work reuses.

---

### ADR-067: Test and Benchmark Infrastructure Lives Beside the Suite

- **Decision (D67):** Phase 9's verification assets are three files at
  `backend/` root plus one module inside the suite: the seed is
  `src/tests/seed_data.py` with `backend/test_seed_data.py` as a thin entry
  point; the concurrent-scan load harness is `backend/locustfile.py` with its
  import-safe helpers (`poisson_wait`, `SlotAssigner`, `discover_session_pool`)
  in `backend/bench_timings.py`, which also serves `--batch` / `--backup`
  one-shot timings. Benchmark-only behavior stays gated behind existing config
  (`BENCHMARK_MODE` skips the scan geofence + liveness checks and the per-IP
  scan rate gate; `RISK_BATCH_WORKERS` shards scoring across threads
  order-preservingly), both defaulting off.
- **Date:** 2026-10-04
- **Status:** Accepted
- **Context:** Three findings from the first load runs forced these placements.
  (1) locust calls `wait_time` bound, so a zero-arg wait crashes every virtual
  user on its first tick. (2) A seed that owns its tables outright breaks the
  moment a scheduled batch runs: the risk-score lookup keyed on
  `(student, offering)` multi-matched, because the unique key is
  `(student, offering, semester, computed_day)`. (3) Importing locust into the
  pytest process installs gevent monkey-patching and hangs the entire suite —
  which is also why the harness's unit-testable helpers cannot live in the
  locustfile.
- **Rationale:**
  - **A re-runnable script, not a data migration.** The seed must be
    importable by tests and the harness, re-runnable without duplicating rows,
    and able to provision load fixtures on demand (`--load-fixtures N`). A
    migration is none of those: it runs once, inside the schema history, and
    cannot take a flag. Every write is looked up by its unique column first, so
    re-runs are no-ops and `--reset` is the explicit destructive path.
  - **Benchmarks must not change what they measure.** Gating behind config
    keeps the geofence and rate limiter out of the request path by default and
    leaves production behavior untouched; both paths are covered by tests, so
    the skip is a tested branch rather than an unverified assumption.
  - **Order-preserving parallelism.** `RISK_BATCH_WORKERS` shards the scoring
    loop by chunk and concatenates in input order, so a sharded run scores
    identically to the serial one — verified by a test asserting the two
    summaries match — while the serial path stays the default.
  - **Harness identity is assigned, not derived.** `SlotAssigner` deals slots
    `1..pool_size` exactly once from a locked counter. Deriving a slot from
    `id(user)` collapses CPython's 16-byte-aligned addresses onto a handful of
    residues modulo the pool size, so users shared an identity and rescanned
    each other's sessions as `duplicate_scan`.
- **Consequences:** 2 new backend-root scripts and 1 suite module; the seed's
  load fixtures are the only source of `SEED-LOAD-*` sessions and 30
  `loadtestNN@load.uni.edu` accounts, and their emails must stay on a
  deliverable domain because the login contract validates with `EmailStr`
  (reserved TLDs 422 on every login). `bench_timings.py --backup` needs `pg_dump`
  and an OpenSSL whose `enc` supports AEAD; the 2026-10-04 run recorded the
  backup leg as environment-blocked for exactly that reason. The gevent trap is
  documented in AGENTS.md so the helpers are not "tidied" back into
  `locustfile.py`.

### ADR-068: Biometric Evidence Is Client-Asserted, and the Server Says So

- **Decision (D68):** The liveness challenge and face-match score are computed
  in the client and graded by the server only for internal consistency. The
  server performs no biometric measurement and no embedding comparison. This is
  accepted for the MVP **and written into `security-model.md`**, so the threat
  table describes what the code does rather than what the design intended.
- **Date:** 2026-10-04
- **Status:** Accepted (known gap, explicitly not an oversight)
- **Context:** `security-model.md` claimed for T4 that face verification is a
  "cosine similarity >= 0.7 threshold" and for T1 that "all steps must pass
  server-side". Neither is true of the current code. What actually happens on
  `POST /student/attendance/scan`:
  (1) `liveness_evidence` is a client-supplied body field. The grader
  (`attendance/service.py::_validate_liveness_evidence`) requires three client
  booleans to be true, `ear_samples` non-empty, the *mean* of those
  client-supplied samples inside `[EAR_MEAN_MIN, EAR_MEAN_MAX]` (0.05..0.5), and
  `pnp_evidence` to be a non-empty dict. It is arithmetic and truthiness over
  submitted values, never a measurement.
  (2) `EAR_SAMPLES_MIN_COUNT` is 1, so the whole three-step challenge is
  satisfiable with a single asserted sample in each of the three positions.
  (3) `face_match_score` is a client-supplied float. `face_match_threshold`
  (0.70) and `face_review_band_low` (0.65) are applied to that submitted number,
  so a client asserting 0.99 always passes and is never routed to review.
  (4) There is no embedding comparison anywhere in the backend — no cosine,
  similarity or dot-product code exists — and `face_enrollment` stores a
  zero-filled placeholder via `_stub_embedding_blob`, so there is nothing to
  compare against even in principle today.
  The realistic threat is therefore a modified client, not a photo shown to an
  honest one. T2's MediaPipe challenge is still worth keeping: it stops
  collusion-by-accident and casual coercion, and it is what a future server-side
  pipeline would replace.
- **Alternatives considered:**
  (1) *Server-side MediaPipe/embedding comparison.* Would make T1 and T4 true as
  written, but requires the model pipeline on the server, real (non-stub)
  embeddings, and a re-enrollment of the existing roster. Out of MVP scope.
  (2) *Sign the client evidence.* Stops naive tampering but not a modified
  client, and adds key management for a partial guarantee. Recorded as the
  cheapest real improvement if this gap is ever taken seriously.
  (3) *Delete the biometric steps.* Rejected: they raise the cost of the casual
  attack, which is the attack that actually happens.
- **Consequences:** Steps 1-3 of the scan (session code, student-ID QR, GPS
  geofence) are genuinely server-enforced, and T3/T5/T8 remain accurate because
  those inputs *are* re-validated on sync. Steps 4-5 are an integrity signal
  recorded in the audit trail, not an access control. Anyone reading
  `attendance_records.face_match_score` as a measurement should read
  `security-model.md` *Client-Asserted Biometrics* first. The same placeholder
  is why `api-contracts.md` records `no_face_detected`, `multiple_faces`,
  `quality_too_low` and `invalid_image` as documented-but-never-raised.

### ADR-069: CI Runs Three Gates, and the Migration Check Is the One That Matters

- **Decision (D69):** `.github/workflows/ci.yml` runs on push-to-`main`, on
  every pull request, and on manual dispatch, as three parallel jobs: the
  719-case backend suite on in-memory SQLite, `alembic upgrade head` followed by
  `alembic check` against a `postgres:16-alpine` service container, and
  `npm ci && npm run check` for the frontend typecheck. Python 3.12 and Node 22,
  matching `backend/Dockerfile.dev` and `frontend/Dockerfile.dev`. No coverage
  threshold, no frontend test runner, no linters.
- **Date:** 2026-10-05
- **Status:** Accepted
- **Forward note (2026-10-11):** the counts above are the 2026-10-05 snapshot. The suite is now 760 cases across 56 files and the chain is eleven revisions ending at `c9d4e5f6a7b8` (drops `users.username`, ADR-073).
- **Context:** The suite was strong and entirely unenforced — 719 cases across 49
  files, green on SQLite and Postgres, with no `.github/`, no `Makefile`, no
  `tox.ini`, and no `pyproject.toml`. Every count in the docs was maintained by
  hand. The consequential gap was migration drift: `conftest.py` builds the test
  schema with `Base.metadata.create_all`, straight from the models, so the
  ten-revision chain is never exercised by the suite in **either** direction and
  no test can detect drift (ADR-065). `alembic check` was the only thing that
  could, and it ran by hand — a rule recorded in `AGENTS.md`, which is exactly
  the kind of rule that decays.
- **Why these three and nothing more:**
  (1) *The drift gate is the irreplaceable one.* `alembic/env.py:28` builds
  `Settings()` to read `DATABASE_URL`, and `alembic.command.check()` runs with
  `as_sql=False`, so it takes the online branch and opens a real connection —
  there is no offline form of the check. Automating it requires a service
  container, which is why `migrations` is a separate job rather than a step
  bolted onto `backend`. It raises `AutogenerateDiffsDetected` (non-zero exit) on
  a mismatch, so a red X is unambiguous.
  (2) *No coverage.* `pytest-cov` is installed and `--cov` is deliberately absent
  from `pytest.ini`. A number nobody enforces invites threshold bikeshedding;
  pass/fail is the whole contract.
  (3) *No frontend test job, and no `npm run build`.* There is no frontend test
  framework at all — no `test` script, no vitest/playwright/jest dependency, zero
  `*.test.ts` / `*.spec.ts` files — so `svelte-check` (errors only; warnings
  pass) is the entire automatable gate. `npm run build` was considered and
  dropped: `adapter-auto` on an unrecognised platform only logs a warning and
  returns 0 (`node_modules/@sveltejs/adapter-auto/index.js:158`), so it would
  add a minute and catch nothing `svelte-check` does not.
- **Alternatives considered:**
  (1) *One workflow with `paths:` filters.* Rejected. A filtered job reports as
  skipped on unrelated changes, which parks a required status check in `pending`
  and blocks the PR anyway. Three always-running jobs are cheaper than that
  argument.
  (2) *Two workflows, backend and frontend.* Rejected for the same reason —
  independent workflows duplicate the trigger/concurrency/permissions preamble,
  and a single file keeps the three gates readable side by side.
  (3) *Run the suite on Postgres too* (`TEST_DATABASE_URL=postgresql+asyncpg://…`).
  Deferred, not rejected: it would cover what the SQLite `JSONB` / `BigInteger` /
  aware-`DateTime` shims in `conftest.py` paper over. Worth a follow-up issue;
  it is not needed to catch drift, which the dedicated job already does.
  (4) *SHA-pinned actions.* Not taken. `actions/checkout@v7`,
  `actions/setup-python@v7`, and `actions/setup-node@v7` are the current majors;
  the repo has no other supply-chain pinning convention to match, and a pinned
  SHA with no Dependabot story is its own staleness problem.
- **Consequences:** The drift guard is no longer a habit, so ADR-065's "fix the
  migration, never the model" now has an enforcer behind it — a model edit that
  diverges from an applied revision fails the `migrations` job instead of waiting
  to be noticed. **No job needs a secret.** `conftest.py` *assigns* `DEBUG=true`
  and `JWT_SECRET` before importing `core.config`, so setting them in the
  workflow would be dead config that reads as load-bearing; `migrations` needs
  only `DEBUG=true` (to satisfy `require_jwt_secret_in_prod`) plus a throwaway
  `DATABASE_URL`. `permissions: contents: read` is accurate — nothing writes to
  the repo. Two constraints are load-bearing and easy to break: `PYTHONPATH=src`
  (imports are `features.*`, never `src.features.*`) and running from `backend/`
  (`Settings.env_file` is CWD-relative; `alembic.ini` uses
  `script_location = alembic`). CI **reports**; only required status checks in
  repo settings make it block a merge, and that half is configured GitHub-side,
  not in the repo.

### ADR-070: Composing Handles Earns a Service Class but Is Not Required

- **Decision (D70):** every `features/<slice>/service.py` is a
  `class <Feature>Service`. The rule of thumb in `coding-standards.md` §1.7
  is widened: composing multiple per-request handles (CRUD, settings,
  limiters) in `__init__` is a **sufficient** reason for a class, not a
  necessary one. A
  cohesive operation set with a private helper cluster also earns one, because
  the alternative scatters a cohesive API across module-level functions and
  drops the `*ServiceDep` seam that every router already uses. What does
  **not** justify a class is a thin wrapper with nothing to compose and no
  meaningful seam; nothing in the tree is one.
  **Supersedes ADR-058(a)'s** blanket "Non-CRUD slices keep module-level
  functions."
- **Date:** 2026-10-05
- **Status:** Accepted
- **Context:** The tree settled on class-per-service without ever recording
  the decision, and the written rules ended up describing a codebase that does
  not exist. Measured at the time: **15 of 15** `features/*/service.py` define
  a `class <Feature>Service`, so there is no module-level-function service
  module anywhere; **22 of the 23** mounted routers import a `*ServiceDep`
  (the one exception is `upload/router.py`, a single presigned-URL handler
  with no service); and `api/deps.py:242-257` defines **14** annotated
  service deps.
  Meanwhile ADR-058(a) still ended "Non-CRUD slices keep module-level
  functions" and `coding-standards.md` §1.7 told readers to write
  `async def create_foo(session: AsyncSession, ...)` for everything else —
  naming four slices (`sync`, `excuse`, `analytics`, `system`) of which **all
  four** are classes, and `sync` has no `service.py` at all.
- **Why the old rule was too narrow, not merely untrue:** keying on what each
  `__init__` actually builds, twelve of the fifteen satisfied the original
  test with no exemption needed — `AdminService` (3 `BaseCRUD`),
  `DashboardService` (5 injected services), `ExcuseService` (2 `BaseCRUD`),
  `SystemService` and `AttendanceService` (session + `Settings`), plus the
  five ADR-055/058/059 already named. Only three failed it, all by composing
  nothing but the session: `AnalyticsService` (812 lines, 7 public methods),
  `ReportsService` (595 lines, 3) and `CourseProfessorService` (66 lines, 1).
  Those three are the whole justification for this ADR — few in number, large
  in consequence, because `analytics` and `reports` back a professor's report
  view and the admin risk view, and `DashboardService` composes both.
- **Alternatives considered:**
  (1) *Flatten the three to module-level functions.* Rejected, and it is why
  this ADR exists. It would have deleted two of the fourteen `*ServiceDep`
  annotations and rewritten twelve route handler signatures (8 in
  `analytics/router.py`, 4 in `reports/router.py`), converting 11 public
  methods and 13 private helpers across files totalling 1,473 lines — the two
  large ones behind two live dashboards. Worse, those three would have become
  the **only** service consumers in the repo not using the shared DI seam,
  inverting them from examples into exceptions.
  (2) *Leave ADR-058(a) as written and fix only `coding-standards.md`.*
  Rejected. It leaves the authoritative file asserting the opposite of the
  standards doc, which is how the drift stayed invisible.
  (3) *Annotate ADR-058(a) and stop there.* This is what #177 did as an
  interim measure, and it is insufficient alone: it records that the old
  sentence was wrong but leaves in place the rule that produced three
  unsanctioned services, so the next slice author re-derives the question.
  (4) *Widen the rule and record it.* Taken. It is the smallest change that
  makes the written convention match the tree without ratifying anything the
  code does not already do unanimously.
- **Consequences:** No service, route, schema, or test file changes — the
  three services keep the class form they already had, so this ADR ratifies
  the status quo rather than converting anything. `CourseProfessorService`
  remains the one service with **no** `*ServiceDep`:
  `course/service.py:456` and `professor/service.py:684` each construct one
  ad hoc for a single overlap check, and `system/service.py:823` does the
  same with `AnalyticsService`. Those bypass the DI graph but reuse the
  *same* request session, so they are intra-request collaborator access rather
  than a defect; promoting them into the graph is a separate, optional
  tidy-up. `shared/csv_import.py` is explicitly unaffected and remains the
  counter-example that keeps the widened rule honest: nine module-level
  functions, nothing to compose, no seam needed, imported by three service
  modules and one admin router rather than injected as a service. ADR-055's
  "prefer a function" default and its `CourseProfessorService` holdover note
  stand as written history — this ADR is what settles the question they left
  open.
### ADR-071: Roster Archive Syncs the Login Gate

- **Decision (D71):** archiving a student or professor deactivates the linked
  `users` row (`users.is_active=False`); reactivating restores it (`True`);
  hard-deleting an archived roster row deactivates (never deletes) the linked
  login. **Qualifies ADR-058's** "no cascade to users" for course data only —
  course_professors / sessions / enrollments still do not cascade; the login
  flag does, because every auth gate (`login`, `refresh_token`,
  `_get_active_user`) reads `users.is_active` alone.
- **Date:** 2026-10-10
- **Status:** Accepted
- **Context:** Student Management deactivates via
  `PATCH /admin/students/{id} {is_active:false}` → `StudentService.archive()`,
  which wrote only `students.is_active=False`. `AuthService.login()`
  (`auth/service.py:343-347`) and `_get_active_user()` (`api/deps.py:101-104`)
  check only `users.is_active`, so archived — and hard-deleted-orphaned —
  accounts stayed fully login-capable. Professor archive had the same gap by
  an explicit no-cascade comment. Only `PATCH /admin/users/{id}/deactivate`
  blocked login.
- **Alternatives considered:**
  (1) *Check roster `is_active` on every auth path.* Rejected: adds roster
  lookups to the per-request hot path and keeps two sources of truth to drift.
  (2) *Frontend calls user-deactivate as a second request.* Rejected: leaves
  the API footgun for every other client.
  (3) *Cascade to `users.is_active` (taken).* Reuses the five existing gates
  with no schema change; each cascade writes one `UPDATE/USER` audit row so
  the now dual-writer flag (`AdminService` + roster services) stays
  reconstructible. Last-writer-wins by design: a roster restore re-enables
  the login even after a separate user-ban, so a ban that must survive a
  restore is re-applied afterwards.
- **Consequences:** `StudentService.archive()/reactivate()/hard_delete()` and
  `ProfessorService._archive_row()/reactivate()/update(is_active=True)/
  hard_delete()` sync the linked user (no-op when `user_id` is None or the
  flag already matches). No endpoint, payload, or migration change;
  `alembic check` stays clean. Covered by
  `tests/features/student/test_archive_login.py` and
  `tests/features/professor/test_archive_login.py`.
### ADR-072: Re-creation Reclaims the Deactivated Login

- **Decision (D72):** `AuthService.register()` and `AdminService.create_user()`
  revive an **inactive** `users` row for a freshly created, unclaimed roster
  row instead of failing 409 on the still-taken email. Extends ADR-071, which
  made hard-delete retain (and deactivate) the login for audit joinability but
  left re-creation dead: roster re-create succeeded, then account creation
  failed `user_exists` / `admin_user_email_exists` while login failed
  `invalid_credentials`.
- **Date:** 2026-10-10
- **Status:** Accepted
- **Context:** The retained orphan owns `users.email` (unique), so no second
  row can be minted for a re-hired address. Revival requires proof plus need:
  self-register re-verifies ownership with a fresh CLAIM OTP; admin-create is
  super_admin-only; and both require exactly one live, unclaimed roster match
  for the address — a ban without a roster row stays dead.
- **Alternatives considered:**
  (1) *Delete the `users` row on hard-delete.* Rejected: frees the email but
  orphans audit rows keyed by that user id, the reason retention exists.
  (2) *Distinct "deactivated" error + manual admin fix.* Rejected: leaves the
  user stuck until an admin acts, and still needs a reclaim endpoint.
  (3) *Auto-reclaim (taken).* One auth gate stays single-sourced on
  `users.is_active`; no endpoint, payload, or migration change.
- **Consequences:** Reclaim sets new credentials + role, clears lockout/MFA
  (backup codes stamped `used_at`, never deleted — same rule as `disable_mfa`),
  links the new roster row, and writes one `UPDATE/USER`
  `{is_active:False}→{is_active:True}` row (register records `performed_by`
  null, the anonymous claimant). All eligibility checks precede the first
  write in the caller's flush-only transaction, so a 409 (active dupe,
  ambiguous/none/claimed match, taken username) leaves the orphan inactive,
  the roster unlinked, and the trail untouched. New `409 username_exists`
  code on `/auth/register` (documented in api-contracts.md; the admin
  `admin_user_username_exists` already existed). `login`'s anti-enumeration
  masking is unchanged. Covered by
  `tests/features/auth/test_register_reclaim.py` (10 tests).
  > **Superseded in part by ADR-073 (2026-10-11):** `users.username` no longer
  > exists, so the "taken username" leg of this Consequences list and both the
  > `username_exists` and `admin_user_username_exists` 409 codes are gone. The
  > reclaim 409 set is now `user_exists` / `ambiguous_account` /
  > `unrecognized_email` / `roster_link_impossible`. The reclaim mechanics above
  > are otherwise unchanged and still authoritative.
### ADR-073: Remove `users.username` — Email Is the Whole Identity

- **Decision (D73):** Drop the `users.username` column entirely rather than
  demote it to an optional display field. Login, OTP, forgot-password, rosters
  and profile are all email-keyed already; `username` was a user-picked handle
  carrying its own UNIQUE guard and two 409 codes (`username_exists`,
  `admin_user_username_exists`) but no functional consumer.
- **Date:** 2026-10-11
- **Status:** Accepted
- **Context:** The handle surfaced as a required input on `POST /auth/register`,
  an optional auto-generated field on `POST /admin/users`, an `ilike` search arm
  on `GET /admin/users`, and a column in the audit `new_value`. Nothing keyed on
  it: no login, no join, no token claim. With no production users, a breaking
  change costs nothing and an optional column would keep a maintainable field
  with no reader forever.
- **Alternatives considered:**
  (1) *Make it nullable + optional (display text).* Rejected: dead weight — still
  needs normalization, length constants, a factory default, migration drift
  surface and doc upkeep, to render one string nobody reads.
  (2) *Keep UNIQUE when present.* Rejected: same, plus a partial unique index.
  (3) *Full removal (taken).* One migration, one contract break, gone.
- **Consequences:** `RegisterRequest` loses `username`; `AdminUserCreate` loses
  it (no more `_default_username`); the `UsernameTakenException` /
  `UsernameAlreadyExists` codes disappear, so `/auth/register` and
  `POST /admin/users` 409s narrow to `user_exists` / `admin_user_email_exists`
  / `roster_link_impossible`. Admin user search drops its username arm;
  first/last name and email still search. Forward migration `c9d4e5f6a7b8`
  drops the constraint then the column, per ADR-065 (never edit an applied
  revision). `shared/validators.normalize_username` and the `USERNAME_*`/
  `DEFAULT_USERNAME_MAX_LENGTH` constants go with it. The demo seed and load
  harness key their users by email only. Breaking for any client that still
  posts `username`; there are none in production. Covered by the existing suite
  plus `tests/features/auth/test_register_username.py`, which now pins that a
  stray `username` key on a roster create is still ignored.

### ADR-074: Login-OTP Lockout Split — Per-Email Attempts, Per-IP Failures, Resend Resets the Email

- **Decision (D74):** Split the login-OTP abuse controls into three layers with
  one job each, and make resends reset the per-email budget.
- **Date:** 2026-10-13
- **Status:** Accepted
- **Context:** The shipped OTP gate had two defects, found in manual testing.
  (1) `POST /auth/login/verify` carried a router flood gate of `5/300s` per IP
  that counted *every* request including successes, so 5 wrong codes exhausted
  the IP bucket and switching to a second email still returned 429 — the lock
  appeared to follow the user across accounts. (2) The per-email service cap
  (3 wrong codes) lived in the 15-minute password-lockout window, so a user who
  mistyped 3 times could not verify for 15 minutes even though a resend mints a
  fresh 5-minute code — the lock outlived the credential by 3x.
- **Alternatives considered:**
  (1) *Loosen the router gate only (`5/300s` → `20/60s`).* Rejected alone:
  fixes the phantom cross-email lock but leaves email rotation unbounded.
  (2) *Key the IP limiter per (IP, email).* Rejected: the verify body carries
  the grant, not an email; a client-supplied email field would let a guessing
  client dodge by rotating it.
  (3) *Taken:* per-email 3/300s (423, reset on resend) + per-IP 15 failures/300s
  (429, failure-only, not reset on resend) + router `20/60s` flood gate.
- **Consequences:** `verify_login_otp` takes the client IP; a new
  `FixedWindowLimiter.reset(key)` clears one email's window on resend; the
  423 `retry_after` is now `otp_expires_minutes` (5), superseding the earlier
  15-minute note in the OTP contract. The 429 UI copy is device-aware so the
  two clocks read differently. Recovery keeps its 15-minute lock — security
  answers don't change, so no reset applies there.

### ADR-075: Password Reset Signs the User In (Except MFA)

- **Decision (D75):** `POST /auth/reset-password` returns the session
  (`TokenResponse`) instead of a 204 — the token pair, or `{mfa_pending: true,
  preauth_token}` for MFA-enabled accounts, finished with TOTP exactly like
  login.
- **Date:** 2026-10-13
- **Status:** Accepted
- **Context:** After the mandatory login-OTP work, a recovered user had to sign
  in again with password + OTP on top of the recovery OTP just entered — three
  proofs where the register flow needs one. Anyone who completes recovery
  (security answer + single-use inbox OTP inside a short window) can complete a
  login anyway, so the extra round is friction, not a boundary. The register
  precedent is decisive: inbox OTP plus a brand-new credential already mints a
  session directly, without even a security question.
- **Alternatives considered:**
  (1) *Keep the 204 + re-login (status quo).* Rejected: the password was set
  seconds ago by the same flow, so retyping it proves nothing, and the fresh
  inbox OTP adds nothing over the consumed recovery OTP — except for MFA
  accounts, where TOTP genuinely adds a factor the recovery never sees.
  (2) *Session for everyone including MFA (taken in part).* Rejected for MFA:
  `verify_mfa` is the only writer that flips `mfa_enabled` True and the only
  path back is `disable_mfa`; letting email+security-answer skip TOTP would
  break that invariant for the accounts that opted into it.
  (3) *Taken:* tokens for non-MFA, preauth challenge for MFA (mirrors
  `login()`'s branch). `must_change_password` is False — the password is
  user-chosen, not an admin temp.
- **Consequences:** Frontend `handleStep4` calls one `doResetPassword` action
  (reset + establish, same shape as `doRegister`) and keeps its 1.5 s success
  beat before navigating; MFA accounts land on the login page for TOTP with
  the password they just set — no TOTP UI added to the wizard. Mock
  `mockResetPassword` resolves identity by email like `mockLogin`.

### ADR-077: Lecture/Laboratory as Session Types + Offering Components

- **Decision (D77):** Lecture vs laboratory is a property of sessions and
  offering schedules, not of courses. `sessions.session_type`
  (`lecture`/`lab`, default `lecture`) records each session's kind, and a new
  `offering_components` child of `course_offerings` carries one scheduled
  component per type (days, start/end time, classroom) so a single course can
  mix a Monday laboratory with a Wednesday lecture in distinct rooms.
  Laboratory sessions always enforce the geofence: opening one without
  resolvable coordinates fails with 422 `lab_coordinates_required`
  (payload → matching lab component → offering fallback); lectures keep
  coordinates optional.
- **Date:** 2026-10-15
- **Status:** Accepted
- **Context:** Course Management showed a Type toggle (Lecture/Laboratory)
  that lived only in the frontend: the backend had no column, silently
  dropped the value, and rendered every live row as Lecture. A per-course
  enum could not represent mixed courses anyway, and a per-offering enum
  could not either — an offering holds one schedule and one classroom.
- **Alternatives considered:**
  (1) *`courses.course_type` column.* Rejected: the template is
  type-agnostic (D44) and one enum cannot mix lab Monday with lecture
  Wednesday.
  (2) *`course_offerings.course_type` single enum.* Rejected: same
  single-schedule/single-room limitation; splitting a mixed class into two
  offerings would break the `uq_course_offering` identity and split
  enrollment/attendance/risk, which are all offering-scoped (D45).
  (3) *Taken:* session type + components. Enrollment, professor
  assignments, and risk stay offering-scoped; sessions, history, and the
  ledger expose and filter by type.
- **Consequences:** Forward-only migration backfills existing sessions to
  `lecture` and gives every offering one lecture component mirroring its
  schedule/classroom, so old rows and old callers keep working. Course
  Management drops the stored Type in favour of a derived
  Lecture/Lab/Mixed badge; the professor session-create toggle is wired to
  `session_type`. The offering-level schedule/room columns stay as the
  legacy display default and session fallback, and the service mirrors the
  lone active meeting onto them whenever an offering has exactly one —
  with zero or several meetings there is no single truth to mirror, so the
  columns are left untouched.

### ADR-076: Unenrollment Deletes Only the Link Row

- **Decision (D76):** `DELETE /admin/offerings/{id}/students/{number}`
  removes the `enrollments` row and nothing else. Past attendance, excuse,
  and risk rows keep their student+session identity; future scans are
  blocked by the live enrollment check. No attendance guard (no 409) and no
  `is_active` gate — cleanup on an archived offering must still work.
  Audited as `unenroll` on `enrollment` with the deleted row's PK.
- **Date:** 2026-10-13
- **Status:** Accepted
- **Context:** Mistaken enrollments were unfixable short of deleting the
  student row, which the `student_has_records` guard rightly blocks. Nothing
  FK-references `enrollments.id` (attendance points at students+sessions),
  so the link delete cannot cascade or trip a `RESTRICT`. The ADR-057
  principle — FKs stay `RESTRICT` so the attendance trail is never destroyed
  — is upheld by construction: the trail rows are untouched, and
  `security-model.md` already promised unenrollment is audited.
- **Alternatives considered:**
  (1) *Block with 409 when scans exist (guard).* Rejected: it recreates the
  unfixable-mistake trap for exactly the rows most likely to be mistakes,
  while the trail it claims to protect is preserved anyway.
  (2) *Soft-delete via a status flag on enrollments.* Rejected: `Enrollment`
  has no status column by design, and a flag would need a predicate in every
  read (`_schedule_stmt`, `_roster_stmt`, session overview, dashboards) for
  no benefit over deleting the link.
  (3) *Taken:* hard-delete the link, keep the trail, audit the removal.
- **Consequences:** Roster, schedule, `enrolledCount`, and session overview
  recompute live, so removal takes effect everywhere with no backfill.
  Re-enrolling is a normal bulk-enroll row (the dedupe no longer matches).
  The Enrolled tab gains a per-row Remove with a confirm modal; the roster
  path id is the student string id, matching the row key.

### ADR-075: Reactivate Admin User Accounts

- **Decision (D75):** `PATCH /admin/users/{user_id}/reactivate` restores a
  deactivated account by setting `users.is_active = True`. It is the symmetric
  counterpart to `PATCH /admin/users/{user_id}/deactivate` and is available
  from the User Management page for any inactive account.
- **Date:** 2026-10-15
- **Status:** Accepted
- **Context:** User Management could deactivate accounts but had no way to
  reactivate them. The deactivate modal explicitly stated the action was
  irreversible from the UI. This was inconsistent with Student/Professor
  Management, where archive and reactivate are symmetric toggles on
  `is_active`.
- **Alternatives considered:**
  (1) *Reuse account re-creation (ADR-072) as the reactivate path.* Rejected:
  re-creation resets the password, may change the role, and requires a live
  unclaimed roster row for student/professor accounts. It is a credential
  reset, not a status toggle.
  (2) *Add a generic `PATCH /admin/users/{id}` with an `is_active` payload.*
  Rejected: the existing contract already establishes the
  `/{id}/deactivate` convention; a separate `/{id}/reactivate` keeps the
  route surface explicit and symmetric.
  (3) *Taken:* a dedicated `PATCH /{user_id}/reactivate` route mirroring the
  deactivation route.
- **Consequences:** `AdminService.reactivate_user()` sets `is_active = True`
  and flushes. Password, MFA, lockout state, and role are intentionally
  preserved — reactivation is a status transition, not a credential reset.
  Self-reactivation is rejected with `SelfDeactivationForbidden`. The User
  Management page shows a Reactivate button on inactive rows with a
  confirmation modal. No migration is required. Covered by
  `tests/features/admin/test_user_status.py`.

### ADR-078: Course Units as the Weekly Scheduled-Hours Cap

- **Decision (D78):** `courses.units` is the maximum permitted total of
  scheduled meeting hours per week across an offering's active components.
  Weekly Scheduled Hours = Σ (schedule_end_time − schedule_start_time) ×
  distinct day-letter count of schedule_days. Valid iff the total fits
  `units × 60` minutes. Enforced in `CourseService` on offering creation,
  component add, and component edit against the merged active set (422
  `weekly_hours_exceed_units` carrying scheduled/limit/remaining); the Setup
  Wizard, Offerings create modal, and Offering detail Settings tab show
  limit/scheduled/remaining live and block over-limit submits with the same
  rule. `session_duration_hours` is retained as the default session length —
  the ceiling for present + late windows and the fallback `duration_minutes`
  when a professor opens a session without an override — and is relabeled
  accordingly in the UI.
- **Date:** 2026-10-16
- **Status:** Accepted
- **Context:** Since D77 an offering mixes meetings of different lengths, so
  the template-level scalar could no longer describe the schedule, and
  nothing validated a schedule against `units` at all. The issue (#265)
  proposed treating units as the weekly cap with Mon 07:00–08:30 +
  Tue 13:00–14:30 (3.0h) valid on a 3-unit course and the 3.5h variant
  rejected, all days folding into one total.
- **Alternatives considered:**
  (1) *Delete `session_duration_hours` now.* Rejected: it still budgets the
  attendance windows (`_check_windows`, `ck_session_window_sum_lte_duration`)
  and defaults session expiry; removal needs a migration plus a per-meeting
  window-budget redesign (Phase 2).
  (2) *DB CHECK constraint.* Rejected: the rule is cross-row and needs the
  merged active set; service-level enforcement is the only home.
  (3) *Taken:* units cap in the service + shared frontend breakdown helper
  (`weeklyHoursBreakdown`), grandfathered legacy rows.
- **Consequences:** No schema change, no migration (`alembic check` stays
  green). Grandfathered over-limit offerings stay readable and archivable and
  may only move downward (a schedule-changing write on an over-limit row must
  strictly decrease the total; room/coords-only edits skip the check).
  Duplicate components still 409 before the cap is evaluated. Multi-letter
  day rows count multiplicatively (`MWF` 1h = 3h), matching the pre-existing
  `weeklyMeetingHours` helper. Covered by
  `tests/features/course/test_weekly_hours.py`.

### ADR-079: Course Units as the Exact Weekly Scheduled-Hours Requirement

- **Decision (D79):** `courses.units` is the required — not merely maximum —
  total of scheduled meeting hours per week across an offering's active
  components. Weekly Scheduled Hours = Σ (schedule_end_time −
  schedule_start_time) × distinct day-letter count, compared in whole
  minutes. Offering creation (the payload carries the whole schedule) must
  land exactly on `units × 60`, else 422 `weekly_hours_exceed_units` (over)
  or 422 `weekly_hours_below_units` (short). Component add/edit must land
  exactly or converge: strictly closer to the requirement without crossing to
  the other side, so legacy off-requirement rows and mid-build schedules can
  always be fixed incrementally but can never overshoot or drift. Reads,
  archives, deactivations, and schedule-untouched edits skip the check;
  reactivating an archived component revalidates the merged total.
- **Date:** 2026-10-16
- **Status:** Accepted
- **Context:** D78 introduced units-as-cap, but a cap still permits
  under-scheduled offerings (e.g. 1.5h on a 3-unit course) to save. The
  requirement is exact match: the admin cannot save while the meeting total
  differs from the units hours in either direction.
- **Alternatives considered:**
  (1) *Strict exact-landing on every write, no convergence.* Rejected: it
  strands rows — splitting one exact meeting into two, or rebuilding after
  archiving, passes through a mid-build total no single write could land
  exactly on, leaving no valid next write.
  (2) *Pure distance (closer is enough, crossing allowed).* Rejected: an
  under total could overshoot into over (1.5h + 2.0h = 3.5h is "closer" than
  1.5h was), permitting a save that still mismatches.
  (3) *Taken:* exact on creation, converge-without-crossing on add/edit.
  Steady states (exact rows, fresh payloads) behave strictly; only
  off-requirement rows get the convergence path, which always terminates at
  exact. The frontend mirrors the rule in `weeklyWriteBlocked`
  (`schedule.ts`), so the three admin surfaces block the same writes the
  backend would 422.
- **Consequences:** Supersedes D78's cap semantics; the `over`/`remaining`
  copy becomes over/short/exact. No schema change, no migration (`alembic
  check` stays green). Covered by
  `tests/features/course/test_weekly_hours.py` (exact create both
  directions, multi-day counting, converge/block sequences from both sides,
  reactivation revalidation).

### ADR-080: Sessions-per-Week Auto-Counted from Meeting Days

- **Decision (D80):** `course_offerings.sessions_per_week` is derived, not
  entered: one session per meeting day (the distinct day-letter count summed
  over the active components, so an `MWF` row counts 3). The Setup Wizard,
  Offerings create modal, and offering detail Settings all share one counting
  rule (`weeklySessionCount` on the frontend). The column is re-synced
  server-side (`_sync_sessions_per_week`) after every component
  insert/update/archive and recomputed on offering creation, so the value the
  risk batch reads never drifts from the meetings; the Settings tab shows it
  read-only. Zero active meetings syncs to 0 (internal sync only — the API
  input floor of 1 still applies to client payloads).
- **Date:** 2026-10-16
- **Status:** Accepted
- **Context:** Step 3 counted `meetings.length` (correct only for its
  single-day rows) while detail Settings exposed a free-typed number that
  could disagree with the meetings entirely, and multi-day rows counted 1
  session for 3 days of class.
- **Alternatives considered:**
  (1) *Keep the editable input.* Rejected: it is the drift source — nothing
  kept it consistent with the meetings.
  (2) *Derive everywhere including the risk batch (drop the column's role).*
  Rejected: larger cross-cutting change into analytics for no gain; syncing
  the column at the four existing `CourseService` write points covers every
  path that can change the meetings.
  (3) *Taken:* shared helper + server-side re-sync + read-only display.
- **Consequences:** No schema change, no migration (`alembic check` stays
  green). Stored values on untouched rows keep their old counts until the
  next component write re-syncs them; displays always show the derived
  value, so save/reopen is consistent. Expected-session denominators for
  multi-day-row offerings rise to the true meeting count going forward.
  Covered by the D80 block in
  `tests/features/course/test_weekly_hours.py`.

### ADR-081: Reshape Edits Exempt from the Weekly-Hours Requirement

- **Decision (D81):** Plain component edits (`PATCH
  /admin/offerings/{id}/components/{cid}` changing schedule/room/coords) save
  freely with no weekly-hours check. Exactness is enforced where a complete
  schedule arrives at once (offering creation: must land exactly) and where
  the total only grows (component add and reactivation: must land exactly or
  converge strictly closer without crossing sides). The over/short panels
  stay visible until a reshape converges back to the requirement.
- **Date:** 2026-10-17
- **Status:** Accepted
- **Context:** D79's per-write enforcement froze exact rows: any duration
  change on an exact total moves away from it, so shrinking a meeting to make
  room for a new one was rejected and multi-step reshapes had no valid
  sequence short of archive-everything-and-rebuild. The rule could not see
  multi-step intent.
- **Alternatives considered:**
  (1) *Keep per-write enforcement everywhere.* Rejected: strands exact rows
  and forces destructive archive-rebuilds for ordinary reshapes.
  (2) *Bulk replace-all-meetings endpoint validated atomically.* Rejected
  for now: principled but an order of magnitude more work for the same
  outcome; reconsider if reshapes routinely span many rows at once.
  (3) *Taken:* free edits, strict creation, converging adds/reactivations.
  Never strands — from any total a single minute-precise edit can reach
  exact — while nothing new can be created mismatched and nothing can grow
  away from the requirement.
- **Consequences:** Transient mismatched states can persist if an admin
  walks away mid-reshape; the red panels plus the converging-add rule keep
  pulling toward exact. The detail edit form additionally gates divergent
  saves behind a "Save anyway?" confirm (triggered by the same
  converge-check), so a mismatch never persists by accident — converging
  fixes save straight through. Covered by the reshape tests in
  `tests/features/course/test_weekly_hours.py`.

### ADR-082: Mismatched Offerings Can Neither Go Live Nor Run

- **Decision (D82):** Two gates, no status auto-flips. (1) Activation
  (`PATCH /admin/offerings/{id}` moving `is_active` False → True) requires
  the merged active-component total to equal `courses.units * 60` exactly —
  422 `schedule_mismatch` otherwise, including the zero-meeting case.
  Deactivation, unrelated PATCHes, and already-active rows are unaffected.
  (2) Session opening (`POST /professor/sessions`) requires the same exact
  total — 422 `offering_schedule_mismatch` with professor-safe copy —
  except when no meetings are configured at all, which is exempt as legacy.
  Closing is never gated.
- **Date:** 2026-10-17
- **Status:** Accepted
- **Context:** Weekly-requirement enforcement stopped mismatched schedules
  from being created or grown, but a mismatched offering could still be
  (re)activated and still run attendance. Auto-deactivation was considered
  and rejected: it would fire mid-reshape (punishing the D81 workflow),
  fire on converging fixes, flap student visibility, and attribute a status
  decision to no human.
- **Alternatives considered:**
  (1) *Auto-deactivate on mismatch.* Rejected per above — no good trigger
  exists that doesn't punish legitimate reshapes.
  (2) *Gate only activation.* Rejected as insufficient alone: already-active
  mismatched rows (grandfathered) could still open sessions.
  (3) *Taken:* activation gate + session-open gate. Nothing mismatched can
  be created, grown, activated, or run — while edits, archives, legacy
  reads, and component-less rows keep working, and no system process ever
  flips a status behind an admin's back.
- **Consequences:** No schema change, no migration (`alembic check` stays
  green). The detail Reactivate button disables with a tooltip while the
  live total is off-requirement (backend remains the enforcer); the
  professor open form renders the backend message verbatim, so it is kept
  free of ids and admin jargon. Signs: the admin detail shows an explicit
  "Sessions blocked" row plus the consequence line on Settings, and every
  professor assigned-offering row carries a server-derived `schedule_ok`
  flag (one extra IN-query in the existing enrichment, empty schedules read
  True) driving a badge, a disabled Open button, and a pre-submit warning —
  so professors learn before clicking, not after. Covered by the activation
  tests in `tests/features/course/test_weekly_hours.py`,
  `tests/features/session/test_schedule_requirement.py`, and
  `tests/features/professor/test_schedule_flag.py`.

### ADR-083: Attendance Overview Becomes the Attendance Tab of Analytics & Reports

- **Decision (D83):** Consolidate the two admin attendance surfaces by
  **purpose**, not by page. The per-course snapshot (wireframes 4.6) moves
  from `/admin/attendance` into a seventh **Attendance** tab of
  Analytics & Reports, keeping its own Course ▸ Professor ▸ date filter row
  (the analytics rail's Program → Year → Term axis is a different slice) and
  the server-first CSV export. `/admin/attendance` is retitled
  **Attendance Review** and keeps only the flagged-scan decision queue
  (wireframe 4.12). The admin nav gains a distinct "Attendance Review" entry
  and icon; the dashboard's "Attendance at a glance" strip deep-links to
  `/admin/analytics?tab=attendance`, while its "Open Analytics" button opens
  the default Overview.
- **Date:** 2026-10-17
- **Status:** Accepted
- **Context:** Both surfaces already shared the frontend analytics
  store/service and the `/admin/attendance/overview*` contract, so the split
  was presentational. Reporting (cross-course rates, trends, comparison) and
  workflow (approve/reject flagged scans) are different jobs: the first
  belongs beside the other reporting tabs, the second needs a queue with
  row actions. D33 already merged Reports into Analytics; the overview was
  the last reporting table living outside it.
- **Alternatives considered:**
  (1) *Keep both pages separate.* Rejected: duplicates navigation and forces
  admins to remember which attendance page holds which number.
  (2) *Merge into one interface with sections.* Rejected: buries the
  approve/reject workflow under reporting chrome and mixes two filter axes.
  (3) *Taken:* reporting tab + review page — one route per purpose, shared
  code where it already existed.
- **Consequences:** No API, schema, or migration change (`alembic check`
  stays green). Frontend-only: overview UI extracted to
  `lib/features/admin/analytics/components/AttendanceSnapshot.svelte`; the
  dead `adminScansState` / `initRecentScans` / `getRecentScans` path removed.
  `AttendanceService.get_overview` now derives its compliance rate and
  half-split trend from `shared.rates.attendance_rates`, removing the last
  hand-rolled rate copy in the feature. The comparison tab's cohort-slicing
  fix (live endpoint groups by course, not cohort) and its missing
  `page`/`size` paging were tracked separately and left untouched here, so the
  consolidation is behaviour-preserving; both are resolved in ADR-084 (#277).

### ADR-084: One Cohort Definition for Per-Course Comparison

- **Decision (D84):** Per-course comparison — admin
  `GET /admin/analytics/course-comparison` and professor
  `GET /professor/reports/comparison` — groups by the **(course, program, year
  level)** cohort key, defined once in `shared/cohorts.py::cohort_key` (with
  `group_by_cohort` for the shared grouping). The professor row carries
  server-resolved `program_code` and `year_level_label`, and the client labels
  and program/year-filters from the row instead of a course-id directory join
  that cannot tell two cohorts of one course apart. Comparison paging is made
  explicit rather than left to the default page: both comparison clients
  request one page at the server's `MAX_PAGE_SIZE` and flag truncation when
  `total` exceeds the rows they got.
- **Date:** 2026-10-17
- **Status:** Accepted
- **Context:** D6 and D34 always specified one row per program/year cohort
  ("same subject across cohorts", "multiple bars per course"), and the mock
  endpoints, TS types, and both UIs were built that way. Neither live
  implementation matched: both grouped by `course_id` alone and labelled the
  merged row with `rows[0]`, so a course taught to BSCS Y1 and BSIT Y1 became
  a single blended row labelled with whichever offering the database returned
  first. Mock mode therefore looked correct while live silently averaged
  unrelated cohorts together. The same class of bug had already happened twice
  in this codebase (`shared/rates.py`, four divergent copies), so the fix
  extracts one key rather than patching two services.
- **Alternatives considered:**
  (1) *Fix each service separately.* Rejected: the two copies had already been
  the failure mode; a third would start.
  (2) *Key by offering id.* Rejected: comparison is defined across the
  offerings of a cohort (terms/sections), not per offering.
  (3) *Add `program_code`/`year_level_label` to the admin row too.* Rejected
  as unnecessary: the admin tab already enriches from its loaded program/year
  dropdown sources, which the professor surface lacks.
- **Consequences:** No schema or migration change (`alembic check` stays
  green). Admin comparison rows keep their shape but are now one per cohort;
  professor rows gain two additive response fields. Row counts multiply with
  the cohort count, so both comparison clients bound the request at
  `MAX_PAGE_SIZE` and flag truncation when `total` is larger — comparison is
  still rendered as one chart/table and is not paginated in the UI.
  `shared/cohorts.py` joins `shared/rates.py` and `shared/schedule.py` as a
  single-source-of-truth helper; semester and dates stay filter axes, not key
  members.

