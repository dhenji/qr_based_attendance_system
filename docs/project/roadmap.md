# Implementation Roadmap — QR Attendance System

> Execution phases for building the system from current state (models + migrations + app shell)
> to full production-ready deployment. Phases are ordered by dependency; later phases build on
> earlier ones. Each phase lists deliverables, key decisions from the
> [Decision Log](./decision-log.md), and prerequisite docs.

---

## Phase 0: Shared Infrastructure [Done]

**Goal:** Core app shell, config, database, shared utilities, baseline migration.

### Deliverables

- FastAPI app shell (`main.py`, `/health`, CORS, lifespan) — `backend/src/main.py`
- pydantic-settings config (`core/config.py`) incl. backup/attachment env vars
- Async engine + session factory + `Base` (`core/database.py`)
- Shared exceptions taxonomy (`core/exceptions.py` — `AppException`/`DomainException`/`DatabaseException`)
- `core/security.py` — Argon2id hashing, JWT access/refresh tokens, HMAC session codes, 6-digit OTP
- `shared/enums.py`, `shared/mixins.py`, `shared/pagination.py`, `shared/base.py` (BaseCRUD), `shared/email.py` (debug stub)
- `api/deps.py` — `_get_db`, `_get_current_user`, `require_role(*roles)`, plus `AuthServiceDep`/`AdminServiceDep` (the session dependency is `_get_db`; there is no public `get_db`)
- Alembic baseline migration `679a319c12d6` (16 tables), + `2a437ca93c53` and `33eabbfbfa6a` in Phase 2 (`mfa_backup_codes` + fingerprint index) → 17 tables

> **Forward-looking:** `audit_logs`, `app_settings` land in Phases 8/12 → 19-table
> target. `mfa_backup_codes` landed in Phase 2 (ADR-054). See
> [migration-strategy.md](../architecture/migration-strategy.md).

### Prerequisite Docs

- [Migration Strategy](../architecture/migration-strategy.md)
- [Coding Standards](../developer/coding-standards.md)

---

## Phase 1: Database & Academic Structure

**Goal:** Create the target hierarchical model (baseline migration creates all 16 tables directly).

### Deliverables

- New tables: `programs`, `year_levels`, `course_offerings`, `course_professors`, `excuse_requests`, `student_risk_scores`, `backup_log` — **all 16/16 target tables are now modeled**; migrations regenerated as a single full baseline `679a319c12d6` (3 legacy revisions dropped, `996b2fb85c6f` replaced)
- Strip `courses` to a pure template: retains only `units` + `session_duration_hours` (D4)
- Create `course_offerings` with schedule, classroom, default windows, and program/year-level FKs (D4)
- Expand `sessions` (drop `course_id`, add `offering_id`), duration, windows, scheduled times, classroom override (D12, D14, D17)
- Expand `attendance_records` with excuse fields, face evidence, rejection reasons (D15, D16)
- Expand `students` with face embedding columns (D28)
- ~~Add `offering_id` + `semester` to `enrollments` (D5)~~ ✅ — `enrollments` modeled with `offering_id`/`semester` NOT NULL, `academic_year` NOT NULL, and `UNIQUE(student_id, offering_id, academic_year)`
- Enum expansion: `ValidationStatus` gains `excused`, `rejected` (D15)
- Enum expansion: `ValidationStatus` values are `present`/`late`/`absent`/`excused`/`pending`/`rejected` in the target schema (no migration needed — baseline creates correct enum values)

### Key Decisions

| ID  | Decision                                                           |
| --- | ------------------------------------------------------------------ |
| D1  | Program → Year Level → CourseOffering ← Course hierarchy (courses have no program/year FKs) |
| D2  | Section stored on `students` only, not enrollments                                         |
| D3  | Term structure per-program-per-year (JSONB on `year_levels`)                                |
| D4  | Scheduling metadata, default windows, GPS moved to `course_offerings`; courses keep only units + session_duration_hours — superseded by D44 (final placement) |
| D5  | Enrollment gains `semester` + `offering_id` validated against term structure                |
| D6  | Courses shared across programs/year levels via multiple offerings per course                |

### Prerequisite Docs

- [Target Schema](../design/database-er.md) — canonical ERD for the target schema
- [Migration Strategy](../architecture/migration-strategy.md) — ordered Alembic plan

---

## Phase 2: Auth, Claims & User Management

**Goal:** Complete the auth layer — claim-based registration, MFA, OTP, lockout.

### Deliverables

- `User` model security fields: `security_question_hash`, `security_answer_hash`, `mfa_enabled`, `mfa_secret`, `failed_login_attempts`, `must_change_password` (already in baseline migration `679a319c12d6`)
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
| D51 | Token transport (JWT bearer) + MFA login gating                                                          |
| D52 | Security question in auth recovery (ADR-052)                                                              |
| D53 | Cloudflare Turnstile captcha, key-gated (ADR-053)                                                         |
| D54 | MFA backup codes (ADR-054)                                                                               |

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
| D7  | Course↔Professor M2M with `is_primary`, effective dating, semester — superseded by D45 (composite PK on `offering_id`) |
| D8  | Mid-semester professor replacement via effective_to / new effective_from |
| D9  | Assistants supported (secondary assignments)                             |
| D11 | Opening from My Courses locks course; Dashboard allows selector          |
| D12 | Duration expiry = min(created_at + duration, scheduled_end)              |
| D13 | Present window + late window ≤ duration (CHECK constraint)               |
| D14 | Default windows on course, overridable per session — superseded by D44 (defaults moved to `course_offerings`) |
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

## Phase 9: Integration Testing & QA [Done]

**Goal:** End-to-end testing across all portals, security validation, performance benchmarks.

> **Status:** all deliverables landed and measured; suite was 707 collected cases
> in 45 files at the time of this run (now 719 in 49 — re-check with
> `pytest src/tests -q --collect-only`), green on SQLite and on Postgres. Load: 11.0 req/s over 5 minutes
> with 30 virtual students, scan p50 18ms / p95 26ms / p99 33ms, zero spurious
> duplicate rejections. Risk batch: 10,058 rows in 4.2s, identical with
> `RISK_BATCH_WORKERS=1` and `=4` (DB-bound at this volume). **Backup leg is
> environment-blocked:** the pipeline needs `openssl enc` with AEAD support for
> `-aes-256-gcm`, which the bench host's OpenSSL build does not provide; the
> re-run command and the exact error are recorded in
> [performance-benchmarks.md](../testing/performance-benchmarks.md) §7. See also
> ADR-067 for where the seed and load harness live and why.

### Deliverables

- Test plan covering all 54 decisions (test-plan.md)
- Test data: ~40 students, shared GE course, 6-week history (test-data.md)
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

## Phase 12: Frontend-Readiness Roundup [Done]

**Goal:** Backend endpoints that exist solely to power the frontend wireframe audit.

All six deliverable groups shipped. The three dashboards live in their own
`features/dashboard/` slice because each aggregates features it does not own —
see the module docstring in `service.py`. Every figure they report is composed
from an existing service method rather than recomputed, so a dashboard cannot
disagree with the page above it.

### Deliverables

- `app_settings` KV table + `GET/PATCH /admin/system/settings` (`geofence_default_radius`,
  `present_window_default`, `late_window_default`, `backup_retention_daily/monthly`,
  `pending_sync_count`)
- Admin reset-password ×3 (admin / student / professor accounts) — one
  implementation, `AuthService.admin_reset_password`
- `POST /auth/mfa/disable` (password required; clears backup codes)
- Dashboard summaries ×3 (`/student/dashboard`, `/professor/dashboard`, `/admin/dashboard`)
- CSV export/template ×3 (student history, attendance overview, roster template)
- `GET /auth/me` + profile enrichments

### Prerequisite Docs

- [API Contracts](../architecture/api-contracts.md) — SHARED Auth Endpoints + Dashboard Summaries
- [Decision Log](./decision-log.md) (D51–D54, ADR-052/053/054)

---

## Dependency Graph

```
Phase 0 (Shared Infrastructure)
  └─→ Phase 1 (DB Schema)
       └─→ Phase 2 (Auth/Claims)
            └─→ Phase 3 (Admin CRUD)
                 ├─→ Phase 4 (Professor Sessions)
                 │    └─→ Phase 5 (Student Scan)
                 │         └─→ Phase 6 (Excuses)
                 │              └─→ Phase 7 (Reports & Analytics)
                 └─→ Phase 8 (Settings & Backup)
                          └─→ Phase 9 (Integration Testing)
                               └─→ Phase 10 (Deployment)
                                    ├─→ Phase 11 (Operations)
                                    └─→ Phase 12 (Frontend-Readiness Roundup)
```

---

## Cross-Reference: Phases to Reference Docs

| Phase    | Reference Docs                                                                                          |
| -------- | ------------------------------------------------------------------------------------------------------- |
| Phase 0  | [migration-strategy.md](../architecture/migration-strategy.md), [coding-standards.md](../developer/coding-standards.md) |
| Phase 1  | [decision-log.md](./decision-log.md) (D1–D6), [database-er.md](../design/database-er.md) Target Schema, [migration-strategy.md](../architecture/migration-strategy.md) |
| Phase 2  | decision-log (D25–D26, D32, D51–D54), [security-model.md](../architecture/security-model.md)            |
| Phase 3  | decision-log (D28, D38, D40), [face-enrollment.md](../architecture/face-enrollment.md), [wireframes.md](../design/wireframes.md) |
| Phase 4  | decision-log (D7–D10, D11–D19), [api-contracts.md](../architecture/api-contracts.md)                     |
| Phase 5  | decision-log (D15–D19, D27–D32), [offline-first.md](../architecture/offline-first.md)                    |
| Phase 6  | decision-log (D20–D24), [excuse-workflow.md](../architecture/excuse-workflow.md)                         |
| Phase 7  | decision-log (D33–D37), [risk-model.md](../architecture/risk-model.md)                                   |
| Phase 8  | decision-log (D38–D40), [backup-strategy.md](../deployment/backup-strategy.md)                           |
| Phase 9  | [test-plan.md](../testing/test-plan.md), [test-data.md](../testing/test-data.md)                         |
| Phase 10 | [deployment-workflow.md](../deployment/deployment-workflow.md), [production-checklist.md](../deployment/production-checklist.md) |
| Phase 11 | [runbooks.md](../operations/runbooks.md), [monitoring.md](../operations/monitoring.md), [incident-response.md](../operations/incident-response.md) |
| Phase 12 | [api-contracts.md](../architecture/api-contracts.md) (SHARED + Dashboard Summaries), [wireframes.md](../design/wireframes.md) |
