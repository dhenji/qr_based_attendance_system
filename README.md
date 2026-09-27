# QR-Based Attendance System

A QR-code based, offline-capable attendance system with anti-spoofing. Students scan the QR code already printed on their ID cards using their phone; professors open class sessions with a code; the system records who is present, who is absent, and generates reports.

Built for **Software Engineering 1**. Full proposal: [`docs/proposals/proposal.md`](docs/proposals/proposal.md).

## Problem

- Manual calling of names wastes 5–10 minutes of class time
- Students can fraudulently sign for absent classmates
- Campus internet is not always reliable
- Paper records are easily lost

## Solution

A web application that:

- Scans the QR code on student IDs to identify the student
- Uses a session code (shown by the professor) + GPS location to prevent cheating
- Works without internet by saving attendance locally and uploading later
- Automatically updates student year levels and sections each school year

## Security & Anti-Spoofing

Every attendance submission follows the canonical **5-step scan flow (D27)**:
`session entry → student-ID QR → GPS geofence → face liveness + match → uniqueness/enrollment check`.
Any single failure rejects the record with one of the canonical D15 rejection
reasons: `duplicate`, `outside_geofence`, `liveness_failed`, `face_mismatch`,
`not_enrolled`, `session_expired`.

| #   | Layer                   | What It Prevents                           | CS Concept                                  |
| --- | ----------------------- | ------------------------------------------ | ------------------------------------------- |
| 1   | Session Entry (code/QR) | Outsiders submitting attendance            | HMAC-SHA256                                 |
| 2   | Student-ID QR           | Wrong identity / unattended devices        | QR payload = student number                 |
| 3   | GPS Geofencing          | Remote/fake submissions                    | Haversine Algorithm                         |
| 4   | Face Liveness + Match   | Photos, replay & distortion tricks         | Blink/turn challenge + embedding similarity |
| 5   | Uniqueness + Enrollment | Same ID used twice / non-enrolled students | DB Constraint + FK Check                    |

## Features

| Feature          | Purpose                                                                                                                |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------- |
| QR Code Scanning | Scan student ID card QR using phone camera                                                                             |
| Session Code     | Professor shares a code; required to submit attendance                                                                 |
| GPS Verification | Ensures student is inside the classroom                                                                                |
| Face Liveness    | Blink/head-turn challenges to block photo, replay & distortion tricks                                                  |
| Offline Mode     | Saves attendance locally when no internet; auto-uploads later                                                          |
| Student Roster   | Import student from CSV file (with official email)                                                                     |
| Dashboard        | View attendance in real time                                                                                           |
| Analytics        | At-risk forecasting and recommendations for professors                                                                 |
| Reports          | Download attendance reports (CSV/PDF/Print)                                                                            |
| Data Tables      | Sortable columns, category + date-range filters, search, print                                                         |
| Account Security | Strong passwords (Argon2id), OTP, optional MFA, admin reset, lockout; Cloudflare Turnstile captcha (optional, planned) |

> **Registration**: students and professors self-register with email +
> password by **claiming** their admin-seeded record (official email lookup +
> OTP ownership proof — names are never typed). Admin accounts are seeded at
> deploy (Super Admin) or created by an existing admin; never
> self-registered. Students use First/Middle/Last names with a Section field;
> admins bulk-promote year + section each academic year.

## Tech Stack

| Component | Technology                                                   |
| --------- | ------------------------------------------------------------ |
| Backend   | Python (FastAPI, SQLAlchemy async, Alembic, Argon2id, PyJWT) |
| Frontend  | SvelteKit 2 (Svelte 5 runes) + TypeScript (strict)           |
| Database  | PostgreSQL 16                                                |
| Platform  | Progressive Web App (works on any device; planned)           |
| Tooling   | Docker / docker-compose, html5-qrcode, zod, @mediapipe/tasks-vision |

## Prerequisites

- Python 3.12+
- Node.js 20+
- Docker & Docker Compose (for Option A)

## Repository Layout

```
├── .gitignore            # Root-level ignores (env/venv, node, docker data, build output)
├── frontend/             # SvelteKit app — feature slices + routes (real API by default, opt-in mock)
│   ├── Dockerfile.dev    # Vite dev server on :5173 (node:22-alpine)
│   ├── src/routes/       # landing (Attendly), about/cookies/privacy-policy, auth (login/register/forgot-password), student (dashboard/scan/schedule/history/profile/settings), professor (dashboard/courses/reports/sessions + create/history/active/[id])
│   └── src/lib/
│       ├── api/          # client.ts (fetch wrapper, real API unless PUBLIC_MOCK_MODE=true) + endpoints.ts (18 typed EndpointDefs with mock fixtures)
│       ├── features/     # auth, student, session, attendance, liveness, sync, report, professor, settings — services + runes stores (auth, student) + components (DashboardStats, QRScanner, FaceScanner, ReportBarChart, ReportTrendChart)
│       └── shared/       # types/ (auth/user/student/session/attendance/course/enrollment/liveness/sync), constants/ (routes/status/roles), utils/ (qr/geo/format/gen), index.ts
├── backend/              # FastAPI app — vertical feature slices + Alembic
│   ├── src/
│   │   ├── main.py       # App entry point (/health, CORS, lifespan SELECT 1 on boot, AppException handler)
│   │   ├── core/         # config.py (pydantic-settings), database.py (async engine + Base), security.py (Argon2id/JWT/OTP/recovery-grant/backup-code fingerprint), exceptions.py
│   │   ├── shared/       # enums.py (13 enums), mixins.py, base.py (CRUD base), pagination.py, email.py, validators.py, captcha.py, rate_limit.py, cache.py, dependencies.py, csv_import.py
│   │   ├── api/          # deps.py (_get_db, _get_current_user, _get_optional_current_user, require_role, *ServiceDep) + router.py (12 routers mounted under /api, no prefix= arg)
│   │   ├── features/     # 15 slices: admin, analytics, attendance, auth, course, course_professor, enrollment, excuse, face_enrollment, professor, program, session, student, sync, system
│   │   │   └── */        # model.py in 13 slices (17 classes; admin + face_enrollment are model-less); 8 with routes (auth/admin/program/course/offering/student-admin/professor-admin/face-enrollment), 4 prefix-only stubs (student/professor/session/attendance), enrollment intentionally unmounted; service.py ×8, schema.py ×7, exceptions.py ×11, constants.py ×6
│   │   └── tests/        # pytest suite — 102 test functions (105 cases with parametrization) in 11 files (hand-rolled fakes, no DB); requires DEBUG=true + JWT_SECRET
│   ├── alembic/          # env.py imports all 13 feature models; 4 migrations — 679a319c12d6 (baseline, 16 tables), 2a437ca93c53 + 33eabbfbfa6a (mfa_backup_codes + fingerprint index), c3e913d02be0 (enrollments.created_at) → 17 tables
│   └── Dockerfile.dev    # Multi-stage: builder (venv /opt/venv) → runtime (uvicorn) → migrate (alembic upgrade head)
├── docker-compose.dev.yml # Local dev: PostgreSQL + migrations + API + frontend (+ api-test under profile: test)
└── docs/                 # Proposals, architecture, deployment, design, developer, guides, operations, presentations, project, testing
```

## Getting Started

### Option A — Docker (recommended)

```bash
docker compose -f docker-compose.dev.yml up --build
```

This starts five services (four always-on plus one test profile):

- **Database**: PostgreSQL on `localhost:5432` (`attendance_sys`)
- **Migrations**: builds the `migrate` target of `backend/Dockerfile.dev` and runs `alembic upgrade head` once, applying the schema before the API boots
- **API**: builds the `runtime` target of `backend/Dockerfile.dev` — http://localhost:8000, health check at `/health`
- **Frontend (app)**: builds `frontend/Dockerfile.dev` — Vite dev server at http://localhost:5173 with HMR, source mounted for live reload
- **api-test** (only with `--profile test`): runs the pytest suite, e.g. `docker compose -f docker-compose.dev.yml --profile test run --rm --build api-test`

The backend image is multi-stage: a `builder` stage creates a virtualenv at `/opt/venv` and installs dependencies, a `runtime` stage copies it in for the API, and a `migrate` stage reuses the runtime image with `alembic upgrade head` as its command.

### Option B

### Manual backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit values
alembic upgrade head   # apply schema migrations
uvicorn main:app --reload --app-dir src
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env   # only PUBLIC_* vars reach the browser
npm run dev            # http://localhost:5173
```

> **Note**: `.npmrc` sets `engine-strict=true` — `npm install` fails if Node
> doesn't satisfy dependency engine ranges.

## Environment Variables

Backend (`backend/.env.example`):

| Variable                         | Default                                                                | Purpose                                                             |
| -------------------------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------------- |
| `APP_NAME`                       | `QR Attendance System API`                                             | API name                                                            |
| `DEBUG`                          | `false`                                                                | Enables SQL echo; skips JWT_SECRET validation when `true`           |
| `DATABASE_URL`                   | `postgresql+asyncpg://postgres:postgres@localhost:5432/attendance_sys` | Async PostgreSQL connection                                         |
| `CORS_ORIGINS`                   | `http://localhost:5173`                                                | Allowed browser origins                                             |
| `HMAC_SECRET_KEY`                | _(empty)_                                                              | Used for secure session codes                                       |
| `JWT_SECRET`                     | _(empty)_                                                              | Required when `DEBUG=false`; generate via `openssl rand -base64 32` |
| `JWT_ALGORITHM`                  | `HS256`                                                                | JWT signing algorithm                                               |
| `PREAUTH_TOKEN_EXPIRE_MINUTES`   | `5`                                                                    | Pre-auth (claim) token TTL                                          |
| `RECOVERY_TOKEN_EXPIRE_MINUTES`  | `5`                                                                    | Forgot-password recovery-grant TTL (in `config.py`; missing from `backend/.env.example`) |
| `ACCESS_TOKEN_EXPIRE_MINUTES`    | `15`                                                                   | Access token TTL                                                    |
| `REFRESH_TOKEN_EXPIRE_DAYS`      | `7`                                                                    | Refresh token TTL                                                   |
| `LOCKOUT_ATTEMPTS`               | `5`                                                                    | Failed login attempts before lockout                                |
| `LOCKOUT_DURATION_MINUTES`       | `15`                                                                   | Lockout duration after failed attempts                              |
| `FACE_MATCH_THRESHOLD`           | `0.70`                                                                 | Face-match similarity threshold                                     |
| `FACE_REVIEW_BAND_LOW`           | `0.65`                                                                 | Lower band requiring manual review                                  |
| `FACE_EMBEDDING_VERSION`         | `1`                                                                    | Face embedding format version                                       |
| `DEFAULT_PRESENT_WINDOW_MINUTES` | `5`                                                                    | Default present window for sessions                                 |
| `DEFAULT_LATE_WINDOW_MINUTES`    | `10`                                                                   | Default late window for sessions                                    |
| `DEFAULT_GEOFENCE_RADIUS_METERS` | `50`                                                                   | Default classroom geofence radius                                   |
| `OTP_EXPIRES_MINUTES`            | `5`                                                                    | OTP code TTL                                                        |
| `BACKUP_STORAGE_TYPE`            | `local`                                                                | Backup backend: `local` or `s3`                                     |
| `BACKUP_LOCAL_DIR`               | `./backups`                                                            | Local backup directory                                              |
| `BACKUP_S3_BUCKET`               | _(empty)_                                                              | S3 bucket (when using S3)                                           |
| `BACKUP_S3_ENDPOINT`             | _(empty)_                                                              | S3-compatible endpoint                                              |
| `BACKUP_S3_PREFIX`               | `backups/`                                                             | S3 key prefix                                                       |
| `BACKUP_ENCRYPTION_KEY`          | _(empty)_                                                              | Backup encryption key                                               |
| `BACKUP_ENCRYPTION_KEY_VERSION`  | `1`                                                                    | Encryption key version                                              |
| `BACKUP_RETENTION_DAILY`         | `30`                                                                   | Daily backups to retain                                             |
| `BACKUP_RETENTION_MONTHLY`       | `12`                                                                   | Monthly backups to retain                                           |
| `BACKUP_EXCLUDE_OTP_CODES`       | `false`                                                                | Exclude OTP codes from backups                                      |
| `BACKUP_COMPRESSION_LEVEL`       | `6`                                                                    | pg_dump compression level                                           |
| `RISK_ABSENCE_RATE_HIGH`         | `0.30`                                                                 | Absence rate threshold for high risk scoring                        |
| `RISK_ABSENCE_RATE_MEDIUM`       | `0.15`                                                                 | Absence rate threshold for medium risk scoring                      |
| `RISK_STREAK_GAPS_HIGH`          | `3`                                                                    | Consecutive missed sessions that trigger high risk                  |
| `RISK_SYNC_LAG_HIGH`             | `5`                                                                    | Days of unsynced records that trigger high risk                     |
| `RISK_TREND_NEGATIVE`            | `-0.05`                                                                | Negative attendance trend slope threshold                           |
| `RISK_BATCH_CRON`                | `0 2 * * *`                                                            | Cron schedule for the risk-scoring batch job                        |
| `RISK_BATCH_CHUNK_SIZE`          | `1000`                                                                 | Risk batch chunk size                                               |
| `RISK_BATCH_WORKERS`             | `4`                                                                    | Concurrent risk batch workers                                       |
| `RISK_BATCH_DRY_RUN`             | `false`                                                                | Dry-run flag for risk batch job                                     |
| `ATTACHMENTS_STORAGE_TYPE`       | `local`                                                                | Excuse attachment storage backend                                   |
| `ATTACHMENTS_MAX_BYTES`          | `5242880`                                                              | Maximum upload size for excuse attachments                          |
| `TURNSTILE_SECRET_KEY`           | _(empty)_                                                              | Cloudflare Turnstile captcha secret (optional)                      |
| `BENCHMARK_MODE`                 | `false`                                                                | Enables performance-benchmark endpoint                              |

Frontend (`frontend/.env.example`):

| Variable           | Default                 | Purpose                                              |
| ------------------ | ----------------------- | ---------------------------------------------------- |
| `PUBLIC_API_URL`   | `http://localhost:8000` | Backend base URL exposed to browser                  |
| `PUBLIC_MOCK_MODE` | `false`                 | `true` serves fixtures instead of calling the API; defaults to real requests |

## Verification

Backend tests:

```bash
docker compose -f docker-compose.dev.yml --profile test run --rm --build api-test
```

Or directly against the local venv (no Docker, no database — the suite uses
hand-rolled fakes and never opens a connection):

```bash
cd backend
DEBUG=true JWT_SECRET=test-secret-0123456789abcdef PYTHONPATH=src .venv/bin/python -m pytest src/tests -q
```

`DEBUG=true` and a dummy `JWT_SECRET` are required, otherwise `Settings`
validation fails at import time. There is no `conftest.py`.

Schema drift check (requires a reachable Postgres and `alembic`):

```bash
cd backend && alembic check    # expect: "No new upgrade operations detected"
```

Frontend typecheck (runs svelte-kit sync automatically):

```bash
cd frontend && npm run check
```

Frontend watch mode:

```bash
cd frontend && npm run check:watch
```

There are no linters or formatters configured, and no CI workflows (no `.github/workflows`). The backend suite currently contains 102 test functions (105 cases with parametrization).

## Deployment

See [`docs/deployment/deployment-workflow.md`](docs/deployment/deployment-workflow.md) for the free-tier guide: **Supabase** (DB) → **Fly.io** (API) → **Vercel** (frontend).

## Documentation

### Proposals

- [`docs/proposals/proposal.md`](docs/proposals/proposal.md) — full 11-section proposal
- [`docs/proposals/proposal_simple.md`](docs/proposals/proposal_simple.md) — 1-page summary
- [`docs/proposals/models.md`](docs/proposals/models.md) — catalog of models used in anti-spoofing/analytics
- [`docs/proposals/contributions.md`](docs/proposals/contributions.md) — honest CS contributions (offline liveness protocol)

### Architecture

- [`docs/architecture/project-structure.md`](docs/architecture/project-structure.md) — intended backend + frontend layout
- [`docs/architecture/frontend-architecture.md`](docs/architecture/frontend-architecture.md) — production-ready frontend structure
- [`docs/architecture/api-contracts.md`](docs/architecture/api-contracts.md) — full API endpoint inventory
- [`docs/architecture/offline-first.md`](docs/architecture/offline-first.md) — IndexedDB sync & conflict handling
- [`docs/architecture/security-model.md`](docs/architecture/security-model.md) — threat model & mitigations
- [`docs/architecture/data-flow.md`](docs/architecture/data-flow.md) — sequence diagrams for all major flows
- [`docs/architecture/migration-strategy.md`](docs/architecture/migration-strategy.md) — Alembic migration plan
- [`docs/architecture/face-enrollment.md`](docs/architecture/face-enrollment.md) — 3-photo enrollment & embedding pipeline
- [`docs/architecture/excuse-workflow.md`](docs/architecture/excuse-workflow.md) — state machine & permission matrix
- [`docs/architecture/risk-model.md`](docs/architecture/risk-model.md) — at-risk prediction & batch job spec

### Deployment

- [`docs/deployment/deployment-workflow.md`](docs/deployment/deployment-workflow.md) — free-tier: Supabase → Fly.io → Vercel
- [`docs/deployment/backup-strategy.md`](docs/deployment/backup-strategy.md) — full pg_dump pipeline, encryption, retention
- [`docs/deployment/production-checklist.md`](docs/deployment/production-checklist.md) — secrets, CORS, storage, first-admin seeding

### Design

- [`docs/design/database-er.md`](docs/design/database-er.md) — entity-relationship diagram (19-table target; 17 landed)
- [`docs/design/wireframes.md`](docs/design/wireframes.md) — screen wireframes

### Developer

- [`docs/developer/backend-setup.md`](docs/developer/backend-setup.md) — Docker Compose, env setup, Alembic, seed script
- [`docs/developer/frontend-setup.md`](docs/developer/frontend-setup.md) — Node, runes mode, service worker
- [`docs/developer/coding-standards.md`](docs/developer/coding-standards.md) — Python, TypeScript/Svelte, git conventions
- [`docs/developer/feature-template.md`](docs/developer/feature-template.md) — vertical-slice checklist (model→router→frontend)

### Guides

- [`docs/guides/admin-manual.md`](docs/guides/admin-manual.md) — program setup, imports, assignment, analytics, backup
- [`docs/guides/professor-manual.md`](docs/guides/professor-manual.md) — sessions, windows, excuses, reports
- [`docs/guides/student-manual.md`](docs/guides/student-manual.md) — 5-step scan, offline, excuses, calendar
- [`docs/guides/face-enrollment-guide.md`](docs/guides/face-enrollment-guide.md) — 3-photo capture script & privacy notes

### Operations

- [`docs/operations/runbooks.md`](docs/operations/runbooks.md) — restore, rollback, unlock, re-enroll, sync-clear, key rotation
- [`docs/operations/monitoring.md`](docs/operations/monitoring.md) — health endpoints, metrics, SLOs
- [`docs/operations/incident-response.md`](docs/operations/incident-response.md) — spoof spike, DB outage, sync flood, backup drill

### Project

- [`docs/project/roadmap.md`](docs/project/roadmap.md) — 13-phase implementation roadmap (Phase 0–12)
- [`docs/project/decision-log.md`](docs/project/decision-log.md) — authoritative decision log (D1–D58, ADR-055–ADR-059)
- [`docs/project/glossary.md`](docs/project/glossary.md) — terminology definitions

### Testing

- [`docs/testing/test-plan.md`](docs/testing/test-plan.md) — portal×feature matrix & decision coverage
- [`docs/testing/test-data.md`](docs/testing/test-data.md) — seed spec (3 programs, 42 students, 6-week history)
- [`docs/testing/performance-benchmarks.md`](docs/testing/performance-benchmarks.md) — scan latency, concurrent sync, risk batch targets

### Presentations

- [`docs/presentations/presentation-slides.md`](docs/presentations/presentation-slides.md) — slide content
- [`docs/presentations/presentation.pptx`](docs/presentations/presentation.pptx) — slide deck

## Project Status

Shared infrastructure is complete — **Phase 0** of the [13-phase roadmap](docs/project/roadmap.md) is **[Done]**. The 17-table model layer covers **Phase 1** (Database & Academic Structure), **Phase 2** (Auth, Claims & User Management: JWT deps, OTP/MFA incl. backup-code fingerprint, lockout, recovery grants, Turnstile) has landed, and **Phase 3** (Admin CRUD: programs/year-levels, course templates, course offerings, student/professor admin with roster CSV import + archive guards, face enrollment) has landed through `#79`–`#92`. Auth + student portal are wired to the real API; the frontend calls the backend by default (`PUBLIC_MOCK_MODE=false`). **Phase 12** is flagged as a **[gap]** in the roadmap.

| Area     | Status                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Backend  | FastAPI app with `/health`, `/api` router, CORS, lifespan `SELECT 1` boot check, `AppException` handler; async SQLAlchemy 2.0 + `core`/`shared` infra (config, database, Argon2id security, exceptions, base CRUD, pagination, email, validators, captcha, rate limiting, cache, csv_import, 13 enums); `api/deps.py` with `_get_db`, `_get_current_user`/`_get_optional_current_user` (JWT/HTTPBearer), `require_role(*roles)`, plus `Auth/Admin/Program/Course/Student/Professor/FaceEnrollmentServiceDep`; 15 feature slices / 17 model classes; 12 routers mounted under `/api` with 8 carrying routes — auth(15)→`/api/auth`, admin(3)→`/api/admin/users`, program(10)→`/api/admin/programs`, course(5)→`/api/admin/courses`, offering(10)→`/api/admin/offerings`, student-admin(7)→`/api/admin/students`, professor-admin(6)→`/api/admin/professors`, face-enrollment(2)→`/api/admin/face-enrollment` — plus 4 prefix-only stubs (student+attendance share `/api/student`, session+professor share `/api/professor`; `enrollment/router.py` intentionally unmounted); 4 Alembic migrations — `679a319c12d6` (16-table baseline) + `2a437ca93c53` + `33eabbfbfa6a` (`mfa_backup_codes` + indexed fingerprint) + `c3e913d02be0` (`enrollments.created_at`) → 17 tables; 102-test pytest suite; multi-stage `Dockerfile.dev` (builder→runtime→migrate) |
| Frontend | Real-API-by-default feature-slice implementation (mock only when `PUBLIC_MOCK_MODE=true`) — 20 pages: landing (Attendly), about/cookies/privacy-policy, auth (login/register/forgot-password), student (dashboard/scan/schedule/history/profile/settings), professor (dashboard/courses/reports/sessions + create/history/active/[id]); 9 feature slices (auth, student, session, attendance, liveness, sync, report, professor, settings) + runes stores (auth, student) + components (DashboardStats, QRScanner, FaceScanner, ReportBarChart, ReportTrendChart); typed `api/client.ts` (BASE_URL + `/api` prefix, auth header, 401-refresh retry, 3-envelope unwrapping) + 18-entry `api/endpoints.ts` registry with mock fixtures; Svelte 5 runes mode forced in `vite.config.ts` (function form, `node_modules` exempt) |
| Features | Model layer complete (17 classes); service layer landed for auth, admin, program, course, student, professor, face_enrollment (+ `course_professor` borderline class, `shared/csv_import.py` module-level fns); schema layer for the same minus `course_professor`; `session`/`attendance`/`enrollment` remain model + stub-router only; `sync`/`excuse`/`analytics`/`system` remain model-only; `liveness` is frontend-only (+ `face_enrollment` backend slice with no model)                                                                                                                                                                                                                                                                                                                                                          |
| Schema   | 17 tables modeled (incl. programs, year_levels, course_offerings, course_professors, excuse_requests, student_risk_scores, backup_log, mfa_backup_codes); migrations at head `c3e913d02be0` ([ERD](docs/design/database-er.md)); forward-looking target is 19 tables (adds `audit_logs`, `app_settings`) per docs/architecture/migration-strategy.md                                                                                                                                                                                                                                                                                                                                                                                         |
| Tests    | 102 backend test functions (105 cases with parametrization, 11 files) run through the `api-test` Compose service (`--profile test`); frontend verification uses `npm run check`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
