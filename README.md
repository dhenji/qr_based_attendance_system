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
| Tooling   | Docker / docker-compose, html5-qrcode, zod, chart.js         |

## Prerequisites

- Python 3.12+
- Node.js 20+
- Docker & Docker Compose (for Option A)

## Repository Layout

```
├── .gitignore            # Root-level ignores (env/venv, node, docker data, build output)
├── frontend/             # SvelteKit app — mock-first feature slices + routes
│   ├── Dockerfile.dev    # Vite dev server on :5173 (node:22-alpine)
│   ├── src/routes/       # landing, auth (login/register/forgot-password), student (dashboard/scan), professor/sessions
│   └── src/lib/
│       ├── api/          # client.ts (fetch wrapper, MOCK=true) + endpoints.ts (typed mock endpoint map)
│       ├── features/     # auth, student, session, attendance, liveness, sync — mock services + runes stores ($state) + components (DashboardStats, QRScanner)
│       └── shared/       # types/, constants/ (routes/status/roles), utils/ (qr/geo/format/gen), index.ts
├── backend/              # FastAPI app — vertical feature slices + Alembic
│   ├── src/
│   │   ├── main.py       # App entry point (/health, CORS, lifespan SELECT 1 on boot, AppException handler)
│   │   ├── core/         # config.py (pydantic-settings), database.py (async engine + Base), security.py (Argon2id/JWT/OTP), exceptions.py
│   │   ├── shared/       # enums.py (13 enums), mixins.py, base.py (CRUD base), pagination.py, email.py, validators.py
│   │   ├── api/          # deps.py (get_db, get_current_user, require_role) + router.py (mounts 5 of 7 routers under /api)
│   │   ├── features/     # 13 slices: analytics, attendance, auth, course, course_professor, enrollment, excuse, professor, program, session, student, sync, system
│   │   │   └── */        # model.py per slice (16 classes); router.py stubs for 7; auth/schema.py + auth/constants.py; course_professor/service.py
│   │   └── tests/        # Empty scaffold — no backend tests yet
│   ├── alembic/          # env.py imports all 13 feature models; 1 baseline migration (679a319c12d6) creating the 16-table target schema
│   └── Dockerfile.dev    # Multi-stage: builder (venv /opt/venv) → runtime (uvicorn) → migrate (alembic upgrade head)
├── docker-compose.dev.yml # Local dev: PostgreSQL + migrations + API + frontend
└── docs/                 # Proposals, architecture, deployment, design, developer, guides, operations, presentations, project, testing
```

## Getting Started

### Option A — Docker (recommended)

```bash
docker compose -f docker-compose.dev.yml up --build
```

This starts four services:

- **Database**: PostgreSQL on `localhost:5432` (`attendance_sys`)
- **Migrations**: builds the `migrate` target of `backend/Dockerfile.dev` and runs `alembic upgrade head` once, applying the schema before the API boots
- **API**: builds the `runtime` target of `backend/Dockerfile.dev` — http://localhost:8000, health check at `/health`
- **Frontend (app)**: builds `frontend/Dockerfile.dev` — Vite dev server at http://localhost:5173 with HMR, source mounted for live reload

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

| Variable                        | Default                                                                | Purpose                                                             |
| ------------------------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------------- |
| `APP_NAME`                      | `QR Attendance System API`                                             | API name                                                            |
| `DEBUG`                         | `false`                                                                | Enables SQL echo; skips JWT_SECRET validation when `true`           |
| `DATABASE_URL`                  | `postgresql+asyncpg://postgres:postgres@localhost:5432/attendance_sys` | Async PostgreSQL connection                                         |
| `CORS_ORIGINS`                  | `http://localhost:5173`                                                | Allowed browser origins                                             |
| `HMAC_SECRET_KEY`               | _(empty)_                                                              | Used for secure session codes                                       |
| `JWT_SECRET`                    | _(empty)_                                                              | Required when `DEBUG=false`; generate via `openssl rand -base64 32` |
| `JWT_ALGORITHM`                 | `HS256`                                                                | JWT signing algorithm                                               |
| `ACCESS_TOKEN_EXPIRE_MINUTES`   | `15`                                                                   | Access token TTL                                                    |
| `REFRESH_TOKEN_EXPIRE_DAYS`     | `7`                                                                    | Refresh token TTL                                                   |
| `LOCKOUT_ATTEMPTS`              | `5`                                                                    | Failed login attempts before lockout                                |
| `LOCKOUT_DURATION_MINUTES`      | `15`                                                                   | Lockout duration after failed attempts                              |
| `FACE_MATCH_THRESHOLD`          | `0.70`                                                                 | Face-match similarity threshold                                     |
| `FACE_REVIEW_BAND_LOW`          | `0.65`                                                                 | Lower band requiring manual review                                  |
| `FACE_EMBEDDING_VERSION`        | `1`                                                                    | Face embedding format version                                       |
| `DEFAULT_PRESENT_WINDOW_MINUTES`| `5`                                                                    | Default present window for sessions                                 |
| `DEFAULT_LATE_WINDOW_MINUTES`   | `10`                                                                   | Default late window for sessions                                    |
| `DEFAULT_GEOFENCE_RADIUS_METERS`| `50`                                                                   | Default classroom geofence radius                                   |
| `OTP_EXPIRES_MINUTES`           | `5`                                                                    | OTP code TTL                                                        |
| `BACKUP_STORAGE_TYPE`           | `local`                                                                | Backup backend: `local` or `s3`                                     |
| `BACKUP_LOCAL_DIR`              | `./backups`                                                            | Local backup directory                                              |
| `BACKUP_S3_BUCKET`              | _(empty)_                                                              | S3 bucket (when using S3)                                           |
| `BACKUP_S3_ENDPOINT`            | _(empty)_                                                              | S3-compatible endpoint                                              |
| `BACKUP_S3_PREFIX`              | `backups/`                                                             | S3 key prefix                                                       |
| `BACKUP_ENCRYPTION_KEY`         | _(empty)_                                                              | Backup encryption key                                               |
| `BACKUP_ENCRYPTION_KEY_VERSION` | `1`                                                                    | Encryption key version                                              |
| `BACKUP_RETENTION_DAILY`        | `30`                                                                   | Daily backups to retain                                             |
| `BACKUP_RETENTION_MONTHLY`      | `12`                                                                   | Monthly backups to retain                                           |
| `BACKUP_EXCLUDE_OTP_CODES`      | `false`                                                                | Exclude OTP codes from backups                                      |
| `BACKUP_COMPRESSION_LEVEL`      | `6`                                                                    | pg_dump compression level                                           |
| `RISK_ABSENCE_RATE_HIGH`        | `0.30`                                                                 | Absence rate threshold for high risk scoring                        |
| `RISK_ABSENCE_RATE_MEDIUM`      | `0.15`                                                                 | Absence rate threshold for medium risk scoring                      |
| `RISK_STREAK_GAPS_HIGH`         | `3`                                                                    | Consecutive missed sessions that trigger high risk                  |
| `RISK_SYNC_LAG_HIGH`            | `5`                                                                    | Days of unsynced records that trigger high risk                     |
| `RISK_TREND_NEGATIVE`           | `-0.05`                                                               | Negative attendance trend slope threshold                           |
| `RISK_BATCH_CRON`               | `0 2 * * *`                                                           | Cron schedule for the risk-scoring batch job                        |
| `RISK_BATCH_CHUNK_SIZE`         | `1000`                                                                 | Risk batch chunk size                                               |
| `RISK_BATCH_WORKERS`            | `4`                                                                    | Concurrent risk batch workers                                       |
| `RISK_BATCH_DRY_RUN`            | `false`                                                                | Dry-run flag for risk batch job                                     |
| `ATTACHMENTS_STORAGE_TYPE`      | `local`                                                                | Excuse attachment storage backend                                   |
| `ATTACHMENTS_MAX_BYTES`         | `5242880`                                                              | Maximum upload size for excuse attachments                          |
| `TURNSTILE_SECRET_KEY`          | _(empty)_                                                              | Cloudflare Turnstile captcha secret (optional)                      |
| `BENCHMARK_MODE`                | `false`                                                                | Enables performance-benchmark endpoint                              |

Frontend (`frontend/.env.example`):

| Variable         | Default                 | Purpose                             |
| ---------------- | ----------------------- | ----------------------------------- |
| `PUBLIC_API_URL` | `http://localhost:8000` | Backend base URL exposed to browser |

## Verification

```bash
# Frontend typecheck (runs svelte-kit sync automatically)
cd frontend && npm run check

# Watch mode
cd frontend && npm run check:watch
```

There are no linters, formatters, or backend tests yet.

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

- [`docs/design/database-er.md`](docs/design/database-er.md) — entity-relationship diagram (16-table target schema)
- [`docs/design/wireframes.md`](docs/design/wireframes.md) — screen wireframes

### Developer

- [`docs/developer/backend-setup.md`](docs/developer/backend-setup.md) — Docker Compose, env setup, Alembic, seed script
- [`docs/developer/frontend-setup.md`](docs/developer/frontend-setup.md) — Node, runes mode, Chart.js, service worker
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
- [`docs/project/decision-log.md`](docs/project/decision-log.md) — authoritative decision log (D1–D54)
- [`docs/project/glossary.md`](docs/project/glossary.md) — terminology definitions

### Testing

- [`docs/testing/test-plan.md`](docs/testing/test-plan.md) — portal×feature matrix & decision coverage
- [`docs/testing/test-data.md`](docs/testing/test-data.md) — seed spec (3 programs, 42 students, 6-week history)
- [`docs/testing/performance-benchmarks.md`](docs/testing/performance-benchmarks.md) — scan latency, concurrent sync, risk batch targets

### Presentations

- [`docs/presentations/presentation-slides.md`](docs/presentations/presentation-slides.md) — slide content
- [`docs/presentations/presentation.pptx`](docs/presentations/presentation.pptx) — slide deck

## Project Status

Shared infrastructure is complete — **Phase 0** of the [13-phase roadmap](docs/project/roadmap.md) is **[Done]**. The 16-table model layer covers **Phase 1** (Database & Academic Structure), and current work (auth schemas, JWT deps, OTP/MFA/lockout config) is building out **Phase 2** (Auth, Claims & User Management). **Phase 12** is flagged as a **[gap]** in the roadmap.

| Area     | Status                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Backend  | FastAPI app with `/health`, `/api` router, CORS, lifespan `SELECT 1` boot check, `AppException` handler; async SQLAlchemy 2.0 + `core`/`shared` infra (config, database, Argon2id security, exceptions, base CRUD, pagination, email, validators, 13 enums); `api/deps.py` with `get_db`, `get_current_user` (JWT/HTTPBearer), `require_role(*roles)`; 13 feature slices / 16 model classes; 5 of 7 router stubs mounted under `/api` (auth→`/api/auth`, student→`/api/student`, session→`/api/professor`, attendance→`/api/student`, professor→`/api/professor`; course & enrollment routers exist but are unmounted); 1 baseline Alembic migration `679a319c12d6` creating the 16-table target schema; multi-stage `Dockerfile.dev` (builder→runtime→migrate) |
| Frontend | Mock-first feature-slice implementation — routes for landing, auth (login/register/forgot-password), student (dashboard/scan), professor (sessions); mock feature services + runes stores (auth, student) + components (DashboardStats, QRScanner); shared types/utils/constants; typed `api/client.ts` (`MOCK = true`) + mock `api/endpoints.ts`; Svelte 5 runes mode forced in `vite.config.ts`                                                                                                                                                                                                                                                                            |
| Features | Model layer complete for all 13 slices; `auth/schema.py` (Pydantic) and `course_professor/service.py` are the only service/schema layers so far; router stubs exist for 7 slices (course_professor, excuse, analytics, program, sync, system have no router file yet); `liveness` is frontend-only                                                                                                                                                                                                                                                                                                                                                                          |
| Schema   | 16 of 16 target tables modeled (incl. programs, year_levels, course_offerings, course_professors, excuse_requests, student_risk_scores, backup_log); baseline migration `679a319c12d6` creates the full target schema ([ERD](docs/design/database-er.md)); forward-looking target is 19 tables (adds `mfa_backup_codes`, `audit_logs`, `app_settings`) per docs/architecture/migration-strategy.md                                                                                                                                           |
| Tests    | Frontend `npm run check` only; backend `tests/` is an empty scaffold                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
