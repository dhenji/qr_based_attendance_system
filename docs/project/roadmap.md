# Implementation Roadmap — QR Attendance System

> Execution phases for building the system from current state (models + migrations + app shell)
> to full production-ready deployment. Phases are ordered by dependency; later phases build on
> earlier ones. Each phase lists deliverables, key decisions from the
> [Decision Log](./decision-log.md), and prerequisite docs.

---

## Phase 1: Database & Academic Structure

**Goal:** Migrate from the current flat schema to the target hierarchical model (D1–D6).

### Deliverables

- New tables: `programs`, `year_levels`, `course_offerings`, `course_professors`, `excuse_requests`, `student_risk_scores`, `backup_log`
- Strip `courses` to a pure template: retains only `units` + `session_duration_hours` (D4)
- Create `course_offerings` with schedule, classroom, default windows, and program/year-level FKs (D4)
- Expand `sessions` with `offering_id`, duration, windows, scheduled times, classroom override (D12, D14, D17)
- Expand `attendance_records` with excuse fields, face evidence, rejection reasons (D15, D16)
- Expand `students` with face embedding columns (D28)
- Add `offering_id` + `semester` to `enrollments` (D5)
- Enum expansion: `ValidationStatus` gains `excused`, `rejected` (D15)
- Data backfill: `valid` → `present`, `invalid` → `rejected` (migration-strategy.md §0.3)

### Key Decisions

| ID  | Decision                                                           |
| --- | ------------------------------------------------------------------ |
| D1  | Program → Year Level → CourseOffering ← Course hierarchy (courses have no program/year FKs) |
| D2  | Section stored on `students` only, not enrollments                                         |
| D3  | Term structure per-program-per-year (JSONB on `year_levels`)                                |
| D4  | Scheduling metadata, default windows, GPS moved to `course_offerings`; courses keep only units + session_duration_hours |
| D5  | Enrollment gains `semester` + `offering_id` validated against term structure                |
| D6  | Courses shared across programs/year levels via multiple offerings per course                |

### Prerequisite Docs

- [Target Schema](../design/database-er.md) — ERD must match §6 of DOCS_REFACTOR_PLAN.md
- [Migration Strategy](../architecture/migration-strategy.md) — ordered Alembic plan

---

## Phase 2: Auth, Claims & User Management

**Goal:** Complete the auth layer — claim-based registration, MFA, OTP, lockout.

### Deliverables

- `User` model security fields: `security_question_hash`, `security_answer_hash`, `mfa_enable`, `mfa_secret`, `failed_login_attempts`, `must_change_password` (already in migration `996b2fb85c6f`)
- `OtpCodes` table (already migrated)
- `Professor` model (already migrated)
- Claim-based registration flow: email → OTP → password → link to student/professor record
- Forgot-password flow
- MFA setup/verification endpoints
- Account lockout after failed attempts

### Key Decisions

| ID  | Decision                                                                                                  |
| --- | --------------------------------------------------------------------------------------------------------- |
| D25 | No "mark all present" or security-disabled sessions — security posture constrains all auth/session design |
| D26 | Liveness remains mandatory even for remote/relaxed-geofence sessions                                      |
| D32 | Student and professor profiles are read-only (admin-managed)                                              |

### Prerequisite Docs

- [API Contracts](../architecture/api-contracts.md) — auth endpoint schemas
- [Security Model](../architecture/security-model.md) — threat mitigations

---

## Phase 3: Admin — Student & Professor CRUD

**Goal:** Admin portal for managing students, professors, and basic enrollment.

### Deliverables

- Student CRUD: create, import (CSV), edit, archive, reactivate
- Professor CRUD: create, edit, archive
- Bulk CSV import with validation
- Student face enrollment (3-photo capture, embedding generation) (D28, D43)
- Program Management suite (replaces flat Course Management) (D38, D40)
  - Programs list, detail, year-level tabs, term structure editor
  - Year-level course list with CRUD
  - Course detail: overview, professors (effective-dating), enrolled students, settings

### Key Decisions

| ID  | Decision                                                                                    |
| --- | ------------------------------------------------------------------------------------------- |
| D28 | Face enrollment: 3 photos (front/left/right), 128-d embeddings, encrypted BYTEA             |
| D38 | Remove Year+Section Promotion; replace with Academic Structure Updates                      |
| D40 | Admin nav: Dashboard · Students · Professors · Programs · Analytics · Audit Logs · Settings |
| D43 | Multi-angle enrollment reduced to 3 photos                                                  |

### Prerequisite Docs

- [Face Enrollment](../architecture/face-enrollment.md)
- [Wireframes §4.5a–d](../design/wireframes.md) — admin program management screens

---

## Phase 4: Professor — Sessions & Live Monitoring

**Goal:** Professor portal for opening sessions, monitoring scans in real time.

### Deliverables

- Session creation: locked variant (from My Courses) and selector variant (from Dashboard) (D11)
- Session code generation (HMAC) and QR payload (versioned JSON) (D18)
- Duration + present/late windows with live expiry calculation (D12, D13)
- Active session view: dual timers, scan feed, status legend, per-row excuse action (D20, D23)
- Session history with section filters
- My Courses view: program-grouped cards with effective professor indicator

### Key Decisions

| ID  | Decision                                                                 |
| --- | ------------------------------------------------------------------------ |
| D7  | Course↔Professor M2M with `is_primary`, effective dating, semester       |
| D8  | Mid-semester professor replacement via effective_to / new effective_from |
| D9  | Assistants supported (secondary assignments)                             |
| D11 | Opening from My Courses locks course; Dashboard allows selector          |
| D12 | Duration expiry = min(created_at + duration, scheduled_end)              |
| D13 | Present window + late window ≤ duration (CHECK constraint)               |
| D14 | Default windows on course, overridable per session                       |
| D17 | Classroom override at session level                                      |
| D18 | Session QR payload versioned JSON                                        |

### Prerequisite Docs

- [API Contracts](../architecture/api-contracts.md) — professor endpoints
- [Offline-First](../architecture/offline-first.md) — sync algorithm
- [Wireframes §3.2a/b, §3.3](../design/wireframes.md)

---

## Phase 5: Student — 5-Step Scan & Attendance

**Goal:** Student scan flow with offline-first support, liveness, and geofencing.

### Deliverables

- 5-step scan flow (D27):
  1. Session entry (type code or scan session QR)
  2. Student-ID QR scan → resolve student number → fetch record + enrollment check
  3. GPS geofence validation (Haversine)
  4. Liveness challenge (blink → left → right) + embedding comparison (D31)
  5. Result overlay (present/late/rejected/pending)
- Offline queue: pending records stored client-side, synced with exponential backoff (D16)
- `scanned_at` server-side validation on sync
- Embedding pull-on-login (version-gated) (D29)
- Student profile (read-only) with face enrollment status (D32)
- Attendance history with compliance + participation rates (D36)

### Key Decisions

| ID  | Decision                                                                   |
| --- | -------------------------------------------------------------------------- |
| D15 | ValidationStatus: present, late, absent, excused, pending, rejected        |
| D16 | Offline scanned_at validation; expired-window → rejected (session_expired) |
| D19 | Student ID QR contains student number only; course context from session    |
| D27 | Strict 5-step sequential scan flow                                         |
| D29 | Embedding distribution: pull-on-login, version-gated                       |
| D30 | Offline face verification uses cached embedding                            |

### Prerequisite Docs

- [Offline-First](../architecture/offline-first.md)
- [Face Enrollment](../architecture/face-enrollment.md)
- [Wireframes §2.2a–e](../design/wireframes.md)

---

## Phase 6: Excuse Workflow

**Goal:** Three-path excuse system with audit trail.

### Deliverables

- `excuse_requests` table with state machine (pending → approved | rejected)
- Path A: Professor quick-excuse (no evidence)
- Path B: Professor-initiated with evidence (auto-approved)
- Path C: Student-initiated request (submit → professor review)
- Bulk "Excuse All Absent" per session (D23)
- `original_status` preservation on excuse (D22)
- Attachment handling: presigned URLs, S3-compatible storage (D24)

### Key Decisions

| ID  | Decision                                                          |
| --- | ----------------------------------------------------------------- |
| D20 | Excused is first-class status with mandatory reason + audit trail |
| D21 | Three initiation paths (quick, prof_with_evidence, request)       |
| D22 | Excuse overrides scanned status; original_status preserved        |
| D23 | Bulk Excuse All Absent                                            |
| D24 | Attachments in S3-compatible storage; DB stores URL references    |

### Prerequisite Docs

- [Excuse Workflow](../architecture/excuse-workflow.md)
- [API Contracts](../architecture/api-contracts.md) — excuse endpoints

---

## Phase 7: Reports & Analytics

**Goal:** Reporting dashboards for professors and admins, at-risk prediction.

### Deliverables

- Professor reports: All Courses aggregate, Per-Course Comparison, Trends (D37)
- Admin Analytics & Reports: unified page with 5 tabs (D33)
  - Overview, Course Comparison, Trends, At-Risk, Export
- Cascading filters: Program → Year → Term → Courses → Date range → Granularity
- Compliance Rate (default) + Participation Rate toggle (D36)
- At-risk heuristic scoring: daily batch job, `student_risk_scores` table (D35)
- Manual refresh endpoint (admin-only)
- Chart.js wrapper component (D41)

### Key Decisions

| ID  | Decision                                                  |
| --- | --------------------------------------------------------- |
| D33 | Admin merges Reports + Analytics into one page with tabs  |
| D34 | Course comparison sliced by program and year level        |
| D35 | Heuristic thresholds (env-configurable); ML upgrade later |
| D36 | Compliance Rate default; Participation Rate toggle        |
| D37 | Professor reports: All Courses aggregate tab              |

### Prerequisite Docs

- [Risk Model](../architecture/risk-model.md)
- [API Contracts](../architecture/api-contracts.md) — analytics endpoints

---

## Phase 8: System Settings & Backup

**Goal:** Admin system settings, encrypted backup pipeline, academic structure management.

### Deliverables

- System settings page: Academic Structure Updates, Maintenance, env-defaults readout
- Full database backup pipeline (D39):
  - `pg_dump -Fc` → gzip → AES-256-GCM encrypt → upload → log → prune
  - Retention: 30 daily + 12 monthly
  - Storage: local (dev) / S3-compatible (prod)
- Analytics export (CSV/PDF)
- Backup management UI (status, last run, download, trigger)
- Academic structure updates: bulk edit flows (add/rename year levels, adjust terms, move courses) (D38)

### Key Decisions

| ID  | Decision                                                         |
| --- | ---------------------------------------------------------------- |
| D38 | No grade-dependent promotion; manual, audited structural updates |
| D39 | Full dump of every table, encrypted, 30D/12M retention           |

### Prerequisite Docs

- [Backup Strategy](../deployment/backup-strategy.md)
- [Wireframes §4.10](../design/wireframes.md)

---

## Phase 9: Integration Testing & QA

**Goal:** End-to-end testing across all portals, security validation, performance benchmarks.

### Deliverables

- Test plan covering all 43 decisions (test-plan.md)
- Seed data: 3 programs, ~40 students, shared GE course, 6-week history (test-data.md)
- Performance benchmarks: scan latency, concurrent sync, risk batch, backup scaling (performance-benchmarks.md)
- Security audit: threat model validation, bypass attempt testing (security-model.md)
- Offline → online sync integration tests

### Prerequisite Docs

- [Test Plan](../testing/test-plan.md)
- [Test Data](../testing/test-data.md)
- [Performance Benchmarks](../testing/performance-benchmarks.md)
- [Security Model](../architecture/security-model.md)

---

## Phase 10: Deployment & Production Launch

**Goal:** Deploy to production (Supabase → Fly.io → Vercel), validate live system.

### Deliverables

- Supabase PostgreSQL provisioned
- Fly.io backend deployed with migrations (release command)
- Vercel frontend deployed with `PUBLIC_API_URL` pointing to Fly.io
- Production checklist completed (secrets, CORS, Turnstile, SMTP, object storage)
- First admin account seeded
- Monitoring endpoints verified
- Backup pipeline tested in production

### Prerequisite Docs

- [Deployment Workflow](../deployment/deployment-workflow.md)
- [Production Checklist](../deployment/production-checklist.md)
- [Runbooks](../operations/runbooks.md)
- [Monitoring](../operations/monitoring.md)

---

## Phase 11: Operations & Maintenance

**Goal:** Ongoing operational procedures, incident response, monitoring.

### Deliverables

- Incident response playbooks (incident-response.md)
- Runbooks for common ops tasks (runbooks.md)
- Monitoring dashboard: scan success rate, sync backlog, risk batch duration, backup freshness
- Scheduled maintenance windows
- Backup restore drill (quarterly)

### Prerequisite Docs

- [Incident Response](../operations/incident-response.md)
- [Runbooks](../operations/runbooks.md)
- [Monitoring](../operations/monitoring.md)

---

## Dependency Graph

```
Phase 1 (DB Schema)
  └─→ Phase 2 (Auth/Claims)
       └─→ Phase 3 (Admin CRUD)
            ├─→ Phase 4 (Professor Sessions)
            │    └─→ Phase 5 (Student Scan)
            │         └─→ Phase 6 (Excuses)
            │              └─→ Phase 7 (Reports & Analytics)
            └─→ Phase 8 (Settings & Backup)
                     └─→ Phase 9 (Integration Testing)
                          └─→ Phase 10 (Deployment)
                               └─→ Phase 11 (Operations)
```

---

## Cross-Reference: Phases to DOCS_REFACTOR_PLAN.md

| Phase    | Refactor Plan Reference                                                          |
| -------- | -------------------------------------------------------------------------------- |
| Phase 1  | §2.1 (D1–D6), §6 Target Schema, Task 0.3 Migration Strategy                      |
| Phase 2  | §2.5 (D25–D26), §2.6 (D32), Task 2.3 Security Model                              |
| Phase 3  | §2.6 (D28), §2.8 (D38, D40), Task 3.1 Face Enrollment, Task 1.1 Admin Wireframes |
| Phase 4  | §2.2 (D7–D10), §2.3 (D11–D19), Task 2.1 API Contracts                            |
| Phase 5  | §2.3 (D15–D19), §2.6 (D27–D32), Task 2.2 Offline-First                           |
| Phase 6  | §2.4 (D20–D24), Task 3.2 Excuse Workflow                                         |
| Phase 7  | §2.7 (D33–D37), Task 3.3 Risk Model                                              |
| Phase 8  | §2.8 (D38–D40), Task 3.4 Backup Strategy                                         |
| Phase 9  | §8–§10 of this plan; Task 7.1–7.3 Testing Docs                                   |
| Phase 10 | deployment-workflow.md, production-checklist.md                                  |
| Phase 11 | runbooks.md, monitoring.md, incident-response.md                                 |
