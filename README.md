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

Every attendance submission is validated against **five layers** before it is accepted; any single failure rejects the record.

| #   | Layer                | What It Prevents                         | CS Concept                   |
| --- | -------------------- | ---------------------------------------- | ---------------------------- |
| 1   | HMAC Session Code    | Outsiders submitting attendance          | HMAC-SHA256                  |
| 2   | GPS Geofencing       | Remote/fake submissions                  | Haversine Algorithm          |
| 3   | Live QR Detection    | Screenshot of a classmate's ID           | Reflection/Liveness Analysis |
| 4   | One Scan Per Session | Same ID used multiple times              | Database Constraint          |
| 5   | Enrollment Check     | Non-enrolled students marking attendance | Relational FK Constraint     |

## Features

| Feature          | Purpose                                                       |
| ---------------- | ------------------------------------------------------------- |
| QR Code Scanning | Scan student ID card QR using phone camera                    |
| Session Code     | Professor shares a code; required to submit attendance        |
| GPS Verification | Ensures student is inside the classroom                       |
| Face Liveness    | Blink/head-turn challenges to block photo, replay & distortion tricks |
| Offline Mode     | Saves attendance locally when no internet; auto-uploads later |
| Student Roster   | Import student from CSV file (with official email)           |
| Dashboard        | View attendance in real time                                  |
| Analytics        | At-risk forecasting and recommendations for professors        |
| Reports          | Download attendance reports (CSV/PDF/Print)                    |
| Data Tables      | Sortable columns, category + date-range filters, search, print |
| Account Security | Strong passwords (bcrypt), Cloudflare Turnstile, OTP, optional MFA, admin reset, lockout |

> **Registration**: students and professors self-register with email +
> password by **claiming** their admin-seeded record (official email lookup +
> OTP ownership proof — names are never typed). Admin accounts are seeded at
> deploy (Super Admin) or created by an existing admin; never
> self-registered. Students use First/Middle/Last names with a Section field;
> admins bulk-promote year + section each academic year.

## Tech Stack

| Component | Technology                                              |
| --------- | ------------------------------------------------------- |
| Backend   | Python (FastAPI, SQLAlchemy async, Alembic)             |
| Frontend  | SvelteKit 5 + TypeScript (strict, runes mode)           |
| Database  | PostgreSQL 16                                           |
| Platform  | Progressive Web App (works on any device; planned)      |
| Tooling   | Docker / docker-compose, html5-qrcode, zod, chart.js    |

## Prerequisites

- Python 3.12+
- Node.js 20+
- Docker & Docker Compose (for Option A)

## Repository Layout

```
├── .gitignore            # Root-level ignores (env/venv, node, docker data, build output)
├── frontend/             # SvelteKit app (minimal app shell + routes)
├── backend/              # FastAPI app — vertical feature slices + Alembic
│   ├── src/
│   │   ├── main.py       # App entry point (/health, CORS, DB lifespan check)
│   │   ├── core/         # config.py (pydantic-settings), database.py (async engine + Base)
│   │   ├── shared/       # Cross-feature enums + mixins
│   │   ├── features/     # auth, professor, student, course, enrollment, session, attendance, sync
│   │   │   └── */model.py # SQLAlchemy models per feature (8 models total)
│   │   ├── api/          # get_db dependency
│   │   └── tests/        # Empty scaffold — no backend tests yet
│   ├── alembic/          # 3 migrations: initial schema, students→users link, OTP codes + security fields
│   └── Dockerfile.dev    # Multi-stage: builder → runtime → migrate
├── docker-compose.yml    # Local dev: PostgreSQL + migrations + API
└── docs/                 # Proposals, architecture, deployment, design, developer, guides, operations, testing
```

## Getting Started

### Option A — Docker (recommended)

```bash
docker compose up --build
```

This starts three services:

- **Database**: PostgreSQL on `localhost:5432` (`attendance_sys`)
- **Migrations**: builds the `migrate` target of `backend/Dockerfile.dev` and runs `alembic upgrade head` once, applying the schema before the API boots
- **API**: builds the `runtime` target of `backend/Dockerfile.dev` — http://localhost:8000, health check at `/health`

The backend image is multi-stage: a `builder` stage creates a virtualenv at `/opt/venv` and installs dependencies, a `runtime` stage copies it in for the API, and a `migrate` stage reuses the runtime image with `alembic upgrade head` as its command.

### Option B — Manual backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit values
alembic upgrade head   # apply schema migrations
PYTHONPATH=src python seed_programs.py   # seed BSCS/BSIT/BSECE programs + year levels
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

| Variable                  | Default                                                                | Purpose                              |
| ------------------------- | ---------------------------------------------------------------------- | ------------------------------------ |
| `APP_NAME`                | `QR Attendance System API`                                             | API name                             |
| `DEBUG`                   | `true`                                                                 | Enables SQL echo                     |
| `DATABASE_URL`            | `postgresql+asyncpg://postgres:postgres@localhost:5432/attendance_sys` | Async PostgreSQL connection          |
| `CORS_ORIGINS`            | `http://localhost:5173`                                                | Allowed browser origins              |
| `HMAC_SECRET_KEY`         | _(empty)_                                                              | Used for secure session codes        |
| `JWT_SECRET`              | _(empty)_                                                              | Required when `DEBUG=false`; generate via `openssl rand -base64 32` |
| `JWT_ALGORITHM`           | `HS256`                                                                | JWT signing algorithm                |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30`                                                               | Access token TTL                     |
| `REFRESH_TOKEN_EXPIRE_DAYS`   | `7`                                                                 | Refresh token TTL                    |

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
- [`docs/design/database-er.md`](docs/design/database-er.md) — entity-relationship diagram (15-table target schema)
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
- [`docs/project/roadmap.md`](docs/project/roadmap.md) — 11-phase implementation roadmap
- [`docs/project/decision-log.md`](docs/project/decision-log.md) — authoritative decision log (D1–D43)
- [`docs/project/glossary.md`](docs/project/glossary.md) — terminology definitions

### Testing
- [`docs/testing/test-plan.md`](docs/testing/test-plan.md) — portal×feature matrix & decision coverage
- [`docs/testing/test-data.md`](docs/testing/test-data.md) — seed spec (3 programs, 42 students, 6-week history)
- [`docs/testing/performance-benchmarks.md`](docs/testing/performance-benchmarks.md) — scan latency, concurrent sync, risk batch targets

### Presentations
- [`docs/presentations/presentation-slides.md`](docs/presentations/presentation-slides.md) — slide content
- [`docs/presentations/presentation.pptx`](docs/presentations/presentation.pptx) — slide deck

## Project Status

The project is in **Phase 1 (partial)** of the [11-phase roadmap](docs/project/roadmap.md).

| Area     | Status                                                                                                                                                                |
| -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Backend  | FastAPI with `/health`, async SQLAlchemy, `core`/`shared` infrastructure, 8 feature models (auth, professor, student, course, enrollment, session, attendance, sync), 3 Alembic migrations (initial schema + `students.user_id` link + OTP codes/security fields), multi-stage `Dockerfile.dev` |
| Frontend | Minimal app shell — `src/routes/`, `src/lib/`, `app.html` present; `html5-qrcode` + `zod` deps; Svelte 5 runes mode enabled                                            |
| Features | Models implemented; `service` / `schema` / `router` layers pending for all features                                                                                  |
| Schema   | 8 of 15 target tables modeled; remaining: programs, year_levels, course_professors, excuse_requests, student_risk_scores, backup_log ([ERD](docs/design/database-er.md)) |
| Tests    | Frontend `npm run check` only; backend `tests/` is an empty scaffold                                                                                                  |
