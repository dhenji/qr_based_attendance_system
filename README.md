# QR-Based Attendance System

A QR-code based, offline-capable attendance system with anti-spoofing. Students sign in to their own account, enter the session code shown by the professor, and confirm their student ID; the system verifies location and liveness, records who is present, who is absent, and generates reports. Student identity is always derived from the authenticated account — the attendance flow does not scan a student-ID QR code.

Built for **Software Engineering 1**. Full proposal: [`docs/proposals/proposal.md`](docs/proposals/proposal.md).

## Problem

- Manual calling of names wastes 5–10 minutes of class time
- Students can fraudulently sign for absent classmates
- Campus internet is not always reliable
- Paper records are easily lost

## Solution

A web application that:

- Derives the student from their signed-in account, with a student-ID confirmation gate
- Uses a session code (shown by the professor) + GPS location to prevent cheating
- Grades face-liveness evidence before recording attendance
- Works without internet by saving attendance locally and uploading later
- Automatically updates student year levels and sections each school year

## Security & Anti-Spoofing

The attendance flow applies these layers in order. D27's original step 2
(student-ID QR) is now a typed/prefilled confirmation gate — see
[ADR-083](docs/project/decision-log.md).

`authenticated identity → session entry → student-ID confirmation → GPS geofence → face liveness → uniqueness/enrollment check`

Identity is resolved from the bearer token, never from the request body. A body
naming a different student is rejected with `403 student_number_mismatch` and
writes no attendance row. Any single failure rejects the record with one of the
canonical D15 rejection reasons: `duplicate_scan`, `outside_geofence`,
`liveness_failed`, `face_mismatch`, `not_enrolled`, `session_expired`.

| #   | Layer                   | What It Prevents                           | CS Concept                                       |
| --- | ----------------------- | ------------------------------------------ | ------------------------------------------------ |
| 1   | Authenticated Identity  | Impersonation / forged client identifiers  | JWT → `users.id` → `students.user_id`             |
| 2   | Session Entry (code/QR) | Outsiders submitting attendance            | HMAC-derived session code + expiry                |
| 3   | Student-ID Confirmation | Wrong account / mistyped roster number     | Case-insensitive precheck + 403 mismatch          |
| 4   | GPS Geofencing          | Remote/fake submissions                    | Haversine Algorithm                              |
| 5   | Face Liveness           | Casual photo/replay attempts (client-asserted) | Blink/turn challenge; server-graded evidence     |
| 6   | Uniqueness + Enrollment | Same ID used twice / non-enrolled students | DB Constraint + FK Check                         |

> **Current biometric limitation:** the server grades the client's liveness
> evidence, but it does **not** compare a face embedding. `face_match_score` is
> a client-supplied value (the shipped client sends a placeholder `1.0`), and
> face enrollment is not required to scan. Server-side face matching is not
> implemented — see the [security model](docs/architecture/security-model.md)
> and ADR-068.

## Features

| Feature          | Purpose                                                                                                                |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Session Entry    | Professor shows a session code; students enter it (the scan page also accepts a session QR where one is available)      |
| Student ID Check | Prefilled from the signed-in profile; the server rejects a number that does not match the account                      |
| GPS Verification | Ensures student is inside the classroom                                                                                |
| Face Liveness    | Blink/head-turn evidence, server-graded, raises the cost of casual photo/replay attempts                                  |
| Offline Mode     | Saves attendance locally when no internet; auto-uploads later                                                          |
| Student Roster   | Import student from CSV file (with official email)                                                                     |
| Dashboard        | View attendance in real time                                                                                           |
| Analytics        | At-risk forecasting and recommendations for professors                                                                 |
| Reports          | Download attendance reports (CSV/PDF/Print)                                                                            |
| Data Tables      | Sortable columns, category + date-range filters, search, print                                                         |
| Account Security | Strong passwords (Argon2id), OTP, optional MFA, admin reset, lockout; Cloudflare Turnstile captcha (optional, config-gated) |

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
| Tooling   | Docker / docker-compose, html5-qrcode (session QR), qrcode, zod, @mediapipe/tasks-vision |

The MediaPipe face-landmark model and its WASM runtime are vendored under
`frontend/static/` (`models/`, `wasm/`), so face enrollment needs no CDN.

## Prerequisites

- Python 3.12+
- Node.js 20+
- Docker & Docker Compose (for Option A)

## Repository Layout

```
├── .gitignore            # Root-level ignores (env/venv, node, docker data, build output)
├── frontend/             # SvelteKit app — feature slices + routes (real API by default, opt-in mock)
│   ├── Dockerfile.dev    # Vite dev server on :5173 (node:22-alpine)
│   ├── static/           # PWA manifest + icons, robots.txt, and vendored MediaPipe assets (models/face_landmarker.task, wasm/)
│   ├── src/service-worker.ts # Offline cache for queued scans + notification polling
 │   ├── src/routes/       # 46 +page.svelte files (45 pages + 1 /admin redirect stub): landing (Attendly) + about/cookies/privacy-policy, auth (login/register/forgot-password), student (dashboard/scan/schedule/history/profile/settings), professor (dashboard/courses/attendance/excuse-requests/reports/sessions + create/history/active/[id]/profile/settings), admin (dashboard/analytics/attendance/audit-logs/excuses/users/profile + programs, students, professors, courses, offerings CRUD & archive/import, system/settings)
│   └── src/lib/
│       ├── api/          # client.ts (fetch wrapper, real API unless PUBLIC_MOCK_MODE=true) + endpoints.ts (named typed EndpointDefs with mock fixtures, collected into an `endpoints` registry)
 │       ├── components/   # AppIcon, ErrorBoundary, InstallPrompt, LoadingSpinner, MfaSettings, Modal, TempPasswordModal (7 shared)
 │       ├── features/     # 12 top-level dirs (+ analytics under admin = 13th conceptual slice): admin (8 sub-slices: analytics/audit/courses/excuses/liveness/offerings/programs/settings), liveness, attendance (professor ledger, real API), auth, excuse, notifications (poll.ts only), professor, report, session, settings, student, sync — services + runes stores (auth, student, admin) + 5 feature components (DashboardStats, QRScanner, FaceScanner, ReportBarChart, ReportTrendChart)
 │       └── shared/       # types/ (admin/attendance/auth/course/enrollment/excuse/liveness/professor/program/session/student/sync/user + index.ts), constants/ (roles/routes/status/terms), utils/ (format/gen/geo/timing), actions/ (focusTrap), theme.css
├── backend/              # FastAPI app — vertical feature slices + Alembic
│   ├── src/
│   │   ├── main.py       # App entry point (/health, CORS, lifespan SELECT 1 on boot + cron scheduler, AppException handler)
│   │   ├── core/         # config.py (pydantic-settings), database.py (async engine + Base), security.py (Argon2id/JWT/OTP/recovery-grant/backup-code fingerprint, HMAC session codes + versioned QR payload), scheduler.py (APScheduler lifecycle), exceptions.py
│   │   ├── shared/       # enums.py (15 enums), mixins.py, base.py (CRUD base), pagination.py, email.py, validators.py, captcha.py, rate_limit.py, cache.py, dependencies.py, csv_import.py, constants.py, query.py, audit.py, rates.py, storage.py, datetimes.py
 │   │   ├── api/          # deps.py (_get_db, _get_current_user, _get_optional_current_user, require_role, *ServiceDep incl. SessionServiceDep) + router.py (23 routers over 15 mount paths, no prefix= arg — each APIRouter bakes its own prefix in)
│   │   ├── features/     # 18 slices: admin, analytics, attendance, auth, course, course_professor, dashboard, enrollment, excuse, face_enrollment, professor, program, reports, session, student, sync, system, upload
│   │   │   └── */        # model.py in 13 slices (20 classes; admin, dashboard, face_enrollment, reports, upload are model-less); see the router table below for mount points. 23 mounted routers over 24 *router*.py files — enrollment intentionally unmounted; service.py ×15, schema.py ×15, exceptions.py ×13, constants.py ×12
 │   │   └── tests/        # pytest suite — 760 cases in 56 files. conftest.py (test_db_session, api_client/test_client, auth_headers, factories) + sync hand-rolled-fake tests + DB-backed async tests. Config: backend/pytest.ini
 │   ├── alembic/          # env.py imports all 13 feature models; 11 revisions — 679a319c12d6 (baseline, 16 tables), 2a437ca93c53 + 33eabbfbfa6a (mfa_backup_codes + fingerprint index), c3e913d02be0 (enrollments.created_at), a562c3f8a6f7 (FK restrict), d4e5f6a7b8c9 (risk-score staging), e7f8a9b0c1d2 (app_settings), f4a9c2b7d103 (audit_logs), b1c4e7f0a2d6, 1e1582c4e9f8 (timestamp indexes), c9d4e5f6a7b8 (drop users.username, ADR-073) → head c9d4e5f6a7b8
│   ├── test_seed_data.py # Seed CLI entry point → src/tests/seed_data.py (--scale small|medium|large|xl, --reset, --load-fixtures N)
│   ├── locustfile.py     # Concurrent-scan load harness (locust; 30 VUs over a pool of SEED-LOAD-* sessions)
│   ├── bench_timings.py  # One-shot risk-batch / backup timings + the import-safe helpers locustfile reuses
│   └── Dockerfile.dev    # Multi-stage: builder (venv /opt/venv) → runtime (uvicorn) → migrate (alembic upgrade head)
├── docker-compose.dev.yml # Local dev: PostgreSQL + migrations + API + frontend (+ api-test under profile: test)
├── demo/                 # Live-demo seed: `seed_demo.py` (idempotent super_admin + BSCS/BSIT/BSECE structure + offerings) + `rosters/` (students/professors/enrollments CSVs) — runbook in `demo/README.md`
└── docs/                 # Proposals, requirements, architecture, deployment, design, developer, guides, operations, presentations, project, testing
```

### API router mounts

`api/router.py` mounts **23 routers over 15 mount paths** under `/api`, with no
`prefix=` argument — each `APIRouter` bakes its own prefix in. Two mounts are
shared by several features, so their inner paths must not collide. (`/api/admin/dashboard`
is a route on the `/admin` mount — `dashboard/admin_router.py` uses `prefix="/admin"`
with an inner `@router.get("/dashboard")` — not a separate mount.)

| Mount             | Routers (feature/router)                                                                     |
| ----------------- | --------------------------------------------------------------------------------------------- |
| `/api/auth`       | `auth`                                                                                        |
| `/api/admin`      | `system` (audit-logs, system settings, academic-structure), `dashboard/admin_router` (`/dashboard`) |
| `/api/admin/users` | `admin`                                                                                       |
| `/api/admin/programs` | `program`                                                                                  |
| `/api/admin/courses` | `course/router`                                                                            |
| `/api/admin/offerings` | `course/offering_router`                                                                  |
| `/api/admin/students` | `student/admin_router`                                                                     |
| `/api/admin/professors` | `professor/admin_router`                                                                 |
| `/api/admin/face-enrollment` | `face_enrollment`                                                                     |
| `/api/admin/attendance` | `attendance/admin_router` (liveness review)                                               |
| `/api/admin/excuses` | `excuse/admin_router`                                                                      |
| `/api/admin/analytics` | `analytics`                                                                                |
| `/api/professor`  | `session`, `professor` (profile only), `excuse/professor_router`, `reports`, `dashboard/professor_router` |
| `/api/student`    | `student`, `attendance` (scan/precheck/history), `excuse/student_router`, `dashboard/student_router` |
| `/api/upload`     | `upload`                                                                                      |

`enrollment/router.py` is a stub and stays intentionally unmounted, so 24
`*router*.py` files exist for 23 routers over 15 mount paths.

## Getting Started

### Option A — Docker (recommended)

```bash
docker compose -f docker-compose.dev.yml up --build
```

This starts six services (four always-on plus two test profile):

- **Database**: PostgreSQL on `localhost:5432` (`attendance_sys`)
- **Migrations**: builds the `migrate` target of `backend/Dockerfile.dev` and runs `alembic upgrade head` once, applying the schema before the API boots
- **API**: builds the `runtime` target of `backend/Dockerfile.dev` — http://localhost:8000, health check at `/health`
- **Frontend (app)**: builds `frontend/Dockerfile.dev` — Vite dev server at http://localhost:5173 with HMR, source mounted for live reload
- **test-db-init** (only with `--profile test`): one-shot `postgres:16-alpine` that ensures the dedicated `attendance_test` database exists in the shared `db` container (idempotent — safe on existing `pgdata` volumes)
- **api-test** (only with `--profile test`): runs the pytest suite against `attendance_test` via `TEST_DATABASE_URL`, e.g. `docker compose -f docker-compose.dev.yml --profile test run --rm --build api-test`

The backend image is multi-stage: a `builder` stage creates a virtualenv at `/opt/venv` and installs dependencies, a `runtime` stage copies it in for the API, and a `migrate` stage reuses the runtime image with `alembic upgrade head` as its command.

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

### Demo data

See [`demo/README.md`](demo/README.md) for the live-demo runbook:

```bash
python demo/seed_demo.py   # idempotent: super_admin (super@attendly.demo / Demo!1234) + programs/courses/offerings
```

then import `demo/rosters/students.csv`, `professors.csv`, and `enrollments.csv` as shown in the runbook.

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
| `RECOVERY_TOKEN_EXPIRE_MINUTES`  | `5`                                                                    | Forgot-password recovery-grant TTL |
| `ACCESS_TOKEN_EXPIRE_MINUTES`    | `15`                                                                   | Access token TTL                                                    |
| `REFRESH_TOKEN_EXPIRE_DAYS`      | `7`                                                                    | Refresh token TTL                                                   |
| `LOCKOUT_ATTEMPTS`               | `5`                                                                    | Failed login attempts before lockout                                |
| `LOCKOUT_DURATION_MINUTES`       | `15`                                                                   | Lockout duration after failed attempts                              |
| `FACE_MATCH_THRESHOLD`           | `0.70`                                                                 | Band threshold for the client-submitted score (no comparison)       |
| `FACE_REVIEW_BAND_LOW`           | `0.65`                                                                 | Lower bound of the review band                                      |
| `FACE_EMBEDDING_VERSION`         | `1`                                                                    | Placeholder embedding format version                                |
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
| `ATTACHMENTS_LOCAL_DIR`          | `./attachments`                                                        | Where the `local` attachment backend writes                          |
| `SMTP_HOST`                      | _(empty)_                                                              | Mail relay host; empty logs mail instead of sending it               |
| `SMTP_PORT`                      | `587`                                                                  | Relay port (587 = STARTTLS, 465 = implicit TLS)                     |
| `SMTP_USER`                      | _(empty)_                                                              | Relay username                                                     |
| `SMTP_PASSWORD`                  | _(empty)_                                                              | Relay password                                                     |
| `SMTP_FROM`                      | _(empty)_                                                              | Envelope sender; falls back to `SMTP_USER`                         |
| `SMTP_START_TLS`                 | `true`                                                                 | Use STARTTLS on port 587                                            |
| `SMTP_USE_SSL`                   | `false`                                                                | Use implicit TLS on port 465                                        |
| `SMTP_TIMEOUT_SECONDS`           | `10`                                                                   | Relay timeout                                                      |
| `TURNSTILE_SECRET_KEY`           | _(empty)_                                                              | Cloudflare Turnstile captcha secret (optional)                      |
| `BENCHMARK_MODE`                 | `false`                                                                | Enables performance-benchmark endpoint                              |
| `SCHEDULER_ENABLED`              | `true`                                                                 | Run the background cron scheduler (off = no crons)                  |
| `SCHEDULER_TIMEZONE`             | `UTC`                                                                  | Scheduler zoneinfo name; unknown values warn and fall back to UTC    |
| `SCHEDULER_MISFIRE_GRACE_SECONDS`| `300`                                                                  | Grace period for a missed cron fire                                 |
| `BACKUP_CRON`                    | `0 3 * * *`                                                            | Cron schedule for the nightly encrypted backup                      |

`LOCUST_*` variables (`LOCUST_MIN_RPS`, `LOCUST_MAX_P95_MS`, `LOCUST_MAX_P99_MS`,
`LOCUST_MAX_DRAIN_S`, `LOCUST_POOL_SIZE`, `LOCUST_MEAN_WAIT_S`,
`LOCUST_QUEUE_STALE_S`, …) are read directly by `backend/locustfile.py` rather
than by `Settings()`, and gate the load run.

Frontend (`frontend/.env.example`):

| Variable           | Default                 | Purpose                                              |
| ------------------ | ----------------------- | ---------------------------------------------------- |
| `PUBLIC_API_URL`   | `http://localhost:8000` | Backend base URL exposed to browser                  |
| `PUBLIC_MOCK_MODE` | `false`                 | `true` serves fixtures instead of calling the API; defaults to real requests |

## Verification

Backend tests (Compose — realistic Postgres path):

```bash
docker compose -f docker-compose.dev.yml --profile test run --rm --build api-test
```

This runs the suite (**760 cases across 56 files**) against the dedicated
`attendance_test` database: `test-db-init` creates it idempotently, then
`api-test` sets `TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/attendance_test`.
The suite runs `create_all`/`drop_all` per test, so it must never point at
`attendance_sys` — `api-test` deliberately sets no `DATABASE_URL`.

Or run it directly against the local venv — no Docker and no database are
needed, because `conftest.py` defaults to in-memory SQLite.

```bash
cd backend
DEBUG=true JWT_SECRET=test-secret-0123456789abcdef PYTHONPATH=src .venv/bin/python -m pytest src/tests -q
```

`DEBUG=true` and a `JWT_SECRET` are only needed for the pre-existing tests,
which build `Settings()` themselves; `conftest.py` sets both for everything
it owns. `PYTHONPATH=src` is what makes `core.*`/`features.*` importable.

To run the same suite against a real Postgres from the local venv (instead
of SQLite), create a dedicated test database first — the suite runs
`create_all`/`drop_all` per test, so never point `TEST_DATABASE_URL` at
`attendance_sys` itself (the Compose path above handles this automatically
via `test-db-init`):

```bash
docker compose -f docker-compose.dev.yml exec db \
  psql -U postgres -c "CREATE DATABASE attendance_test;"
```

```bash
cd backend
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/attendance_test \
  PYTHONPATH=src .venv/bin/python -m pytest src/tests -q
```

Markers (`backend/pytest.ini`): `-m "not slow"`, `-m "not integration"`.

Coverage (no `--cov` in `addopts`, so a plain run stays fast):

```bash
cd backend && PYTHONPATH=src .venv/bin/python -m pytest src/tests -q \
  --cov=src/features --cov=src/shared --cov=src/core --cov-report=term-missing
```

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

There are no linters or formatters configured. The backend suite is 760 cases
across 56 files (228 sync + 490 async test functions, plus parametrized expansions).

### CI

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every push to
`main`, every pull request, and manually via `workflow_dispatch`, as three parallel jobs — rationale in
[ADR-069](docs/project/decision-log.md):

| Job | Gate | Needs |
| --- | --- | --- |
| `backend` | `python -m pytest src/tests -q` — 760 cases on in-memory SQLite | nothing |
| `migrations` | `alembic upgrade head && alembic check` | a `postgres:16-alpine` service |
| `frontend` | `npm ci && npm run check` (svelte-check) | nothing |

No job reads a secret. The `migrations` job is the one that matters: the test
schema is built with `Base.metadata.create_all`, straight from the models, so
the suite exercises the migration chain in neither direction and **cannot** catch
drift (ADR-065). `alembic check` is the only thing that does — the local
equivalent is the schema drift check above.

CI **reports**; it only *blocks* a merge once `backend`, `migrations`, and
`frontend` are added as required status checks in the repository's branch
protection settings. **`main` is not protected today** — on a private repository
GitHub gates branch protection and rulesets behind a paid plan, so merges are
currently enforced by convention, not by the platform.

> **Note**: several test modules pin a fixed `NOW =
> 2026-09-27 12:00 UTC` fixture and are wall-clock sensitive —
> pre-existing clock sensitivity on `main`, not a regression.

## Deployment

See [`docs/deployment/deployment-workflow.md`](docs/deployment/deployment-workflow.md) for the free-tier guide: **Supabase** (DB) → **Fly.io** (API) → **Vercel** (frontend).

## Documentation

### Requirements

- [`docs/requirements/Attendly_SRS_Table_Format.pdf`](docs/requirements/Attendly_SRS_Table_Format.pdf) — software requirements specification (table format)

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
- [`docs/architecture/face-enrollment.md`](docs/architecture/face-enrollment.md) — face enrollment flow & current verification limitations
- [`docs/architecture/excuse-workflow.md`](docs/architecture/excuse-workflow.md) — state machine & permission matrix
- [`docs/architecture/risk-model.md`](docs/architecture/risk-model.md) — at-risk prediction & batch job spec

### Deployment

- [`docs/deployment/deployment-workflow.md`](docs/deployment/deployment-workflow.md) — free-tier: Supabase → Fly.io → Vercel
- [`docs/deployment/backup-strategy.md`](docs/deployment/backup-strategy.md) — full pg_dump pipeline, encryption, retention
- [`docs/deployment/production-checklist.md`](docs/deployment/production-checklist.md) — secrets, CORS, storage, first-admin seeding

### Design

- [`docs/design/database-er.md`](docs/design/database-er.md) — entity-relationship diagram (20 tables landed)
- [`docs/design/wireframes.md`](docs/design/wireframes.md) — screen wireframes

### Developer

- [`docs/developer/backend-setup.md`](docs/developer/backend-setup.md) — Docker Compose, env setup, Alembic, seed script
- [`docs/developer/frontend-setup.md`](docs/developer/frontend-setup.md) — Node, runes mode, service worker
- [`docs/developer/coding-standards.md`](docs/developer/coding-standards.md) — Python, TypeScript/Svelte, git conventions
- [`docs/developer/feature-template.md`](docs/developer/feature-template.md) — vertical-slice checklist (model→router→frontend)

### Guides

- [`docs/guides/admin-manual.md`](docs/guides/admin-manual.md) — program setup, imports, assignment, analytics, backup
- [`docs/guides/professor-manual.md`](docs/guides/professor-manual.md) — sessions, windows, excuses, reports
- [`docs/guides/student-manual.md`](docs/guides/student-manual.md) — scan flow, offline, excuses, calendar
- [`docs/guides/face-enrollment-guide.md`](docs/guides/face-enrollment-guide.md) — 3-photo upload script, current limitations & privacy notes

### Operations

- [`docs/operations/runbooks.md`](docs/operations/runbooks.md) — restore, rollback, unlock, re-enroll, sync-clear, key rotation
- [`docs/operations/monitoring.md`](docs/operations/monitoring.md) — health endpoints, metrics, SLOs
- [`docs/operations/incident-response.md`](docs/operations/incident-response.md) — spoof spike, DB outage, sync flood, backup drill

### Project

- [`docs/project/roadmap.md`](docs/project/roadmap.md) — 13-phase implementation roadmap (Phase 0–12; 0, 9 and 12 marked `[Done]`)
- [`docs/project/decision-log.md`](docs/project/decision-log.md) — authoritative decision log (D1–D83, ADR-001–ADR-083)
- [`docs/project/glossary.md`](docs/project/glossary.md) — terminology definitions

### Testing

- [`docs/testing/test-plan.md`](docs/testing/test-plan.md) — portal×feature matrix & decision coverage
- [`docs/testing/test-data.md`](docs/testing/test-data.md) — seed spec (3 programs, 42 students, 6-week history)
- [`docs/testing/performance-benchmarks.md`](docs/testing/performance-benchmarks.md) — scan latency, concurrent sync, risk batch targets

### Presentations

- [`docs/presentations/presentation-slides.md`](docs/presentations/presentation-slides.md) — slide content
- [`docs/presentations/presentation.pptx`](docs/presentations/presentation.pptx) — slide deck

## Project Status

Every phase of the [13-phase roadmap](docs/project/roadmap.md) has landed its
backend deliverables; Phases 0, 9 and 12 are explicitly marked `[Done]`, and the
roadmap is the authority on per-phase status. The frontend calls the real API by
default (`PUBLIC_MOCK_MODE=false`) — mock mode is opt-in for UI work.

| Area      | Status                                                                                                                                                                                                                     |
| --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Backend   | 18 feature slices / 20 model classes / 20 tables; 23 routers over 15 mount paths under `/api` (see the mount table above); head migration `c9d4e5f6a7b8` (11 revisions); APScheduler crons for the 02:00 risk batch and 03:00 backup; `AppException` handler, lifespan `SELECT 1` boot check, shared `rates.py`/`audit.py`/`email.py` infra |
| Frontend  | 46 +page.svelte files (45 pages across landing/auth/student/professor/admin + 1 /admin redirect stub); 12 top-level feature dirs (+ analytics under admin) (`admin` has 8 sub-slices) + runes stores (auth, student, admin) + 5 feature components and 7 shared ones; typed `api/client.ts` + an `EndpointDef` registry; PWA via `static/manifest.webmanifest` and `src/service-worker.ts` |
| Schema    | 20 tables modelled and migrated, including `app_settings`, `audit_logs`, `student_risk_scores_staging` and `mfa_backup_codes` ([ERD](docs/design/database-er.md)); `users.username` removed (D73, email is the whole identity) |
| Tests     | 760 backend cases in 56 files (SQLite by default, or `TEST_DATABASE_URL` for Postgres), run through the `api-test` Compose service or the local venv; frontend verification is `npm run check`                     |
| Benchmarks | Measured load run 2026-10-04: 11.0 scans/s over 300s, p95 26ms, p99 33ms, 0 duplicate rejections; risk batch 4.2s for 10,058 students. Backup leg environment-blocked on OpenSSL 3 AEAD — see [performance-benchmarks.md](docs/testing/performance-benchmarks.md) §7 |

The remaining known gaps are operational rather than structural: Phase 10
(production launch) and Phase 11 (ongoing operations) are deployment and process
work, not code.
