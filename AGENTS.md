# AGENTS.md — QR-Based Attendance System

**FastAPI backend** (7 feature models + initial Alembic migrations) + **minimal SvelteKit app shell**. Feature `service`/`schema`/`router` layers are empty.

## Repository State

- Remote: `git@github.com:CodeKharl/qr_based_attendance_system.git`. Work flows through branches/PRs against `main`.
- Layout: `frontend/` (app shell), `backend/` (models + migrations + `Dockerfile.dev`), root `docker-compose.yml` (local dev), `docs/`.
- Root `.gitignore` ignores `.env`/`.env.*` but **un-ignores** `.env.example` and `.env.test`. A real `backend/.env` exists (ignored); never commit one.
- No linters, formatters, backend tests, or CI. Only automated check: `npm run check` in `frontend/`. `README.md` is current and accurate.

## Key Commands

### Local Dev (Docker — recommended)
```bash
docker compose up --build          # API on :8000, Postgres on :5432, migrations run automatically
```

### Manual Backend
```bash
cd backend
cp .env.example .env               # edit values
alembic upgrade head               # apply schema
uvicorn main:app --app-dir src --reload
```

### Frontend
```bash
cd frontend
npm install
cp .env.example .env               # only PUBLIC_* vars reach browser
npm run dev                        # http://localhost:5173
npm run check                      # typecheck (runs svelte-kit sync first)
```

## Backend (`backend/`)

- **Entry**: `src/main.py` — FastAPI `app`, `/health`, CORS, lifespan runs `SELECT 1` against Postgres at startup (app **fails to boot if DB unreachable**).
- **Config**: `src/core/config.py` — `pydantic-settings` reads `.env`, `get_settings()` cached.
- **Database**: `src/core/database.py` — async engine + session factory + `Base(DeclarativeBase)`.
- **Dependency**: `src/api/deps.py` — `get_db` yields `AsyncSession`.
- **Models** (all in `src/features/*/model.py`, subclass `core.database.Base`):
  - `auth.User` + `auth.OtpCodes`
  - `student.Student`
  - `course.Course`
  - `enrollment.Enrollment`
  - `session.Session`
  - `attendance.AttendanceRecord`
  - `sync.SyncQueue`
- **Alembic**: `alembic/env.py` imports all 7 feature models so `target_metadata` is populated.
  - `68a78206e082_initial_schema.py` — creates full schema
  - `388e5e496455_link_students_to_user_accounts.py` — adds `user_id` FK to `students`
  - `996b2fb85c6f_add_account_security_fields_otp_codes_.py` — adds security fields to `users`, creates `otp_codes`
  - To add a table: write model, ensure imported in `alembic/env.py`, then `alembic revision --autogenerate -m "..."` + `alembic upgrade head`.
- **Shared**: `src/shared/enums.py` (`UserRole`, `OtpPurpose`, `ValidationStatus`, `SyncStatus`, `QueueStatus`), `src/shared/mixins.py` (`CreatedAtMixin`, `TimestampMixin`).
- **Missing**: `service.py`, `schema.py`, `router.py` per feature; `backend/src/shared/dependencies.py`/`cache.py`/`base.py`; everything in `backend/src/tests/`.
- **Dockerfile.dev**: Multi-stage — `builder` (venv at `/opt/venv` + pip install) → `runtime` (API) → `migrate` (`alembic upgrade head`). Compose builds `migrate` with `target: migrate` and `api` with `target: runtime`.

## Frontend (`frontend/`)

- **Stack**: SvelteKit 2 + Svelte 5, `@sveltejs/adapter-auto`, TypeScript strict. Deps: `html5-qrcode`, `zod`.
- **Runes mode forced on** via `vite.config.ts` `compilerOptions.runes` — write `$state`/`$props` runes, not legacy reactive declarations.
- **Minimal shell only**: `src/routes/+page.svelte`, `src/routes/+layout.svelte`, `app.html`, `src/lib/` (favicon, index.ts). No API routes or real pages yet.
- `.npmrc` sets `engine-strict=true` — `npm install` fails if Node doesn't satisfy dep engine ranges (package.json declares no `engines`).
- Env: copy `.env.example` to `.env`; only `PUBLIC_*` vars reach browser (`PUBLIC_API_URL=http://localhost:8000`).
- PWA (`vite-plugin-pwa`) planned but **not installed**; `vite.config.ts` comments mark it as optional later upgrade.
- Planned architecture (see `docs/architecture/frontend-architecture.md`): feature-slice structure mirroring backend under `src/lib/features/{auth,student,session,attendance,liveness,sync,...}` with `store.svelte.ts`, `service.ts`, `schema.ts`, `mock.ts`, `components/`.

## Gotchas & Quirks

| Area | Detail |
|------|--------|
| DB connection | FastAPI lifespan runs `SELECT 1` at startup — container fails if Postgres not ready. Compose handles this via `depends_on: condition: service_healthy`. |
| Migrations | `alembic/env.py` imports models using `features.*.model` (not `src.features...`). Running alembic manually requires `cd backend` so imports resolve. |
| Env files | Backend reads `.env` from `backend/` (not root). Frontend reads `.env` from `frontend/`. |
| CORS | `CORS_ORIGINS` in backend `.env` must include frontend origin (`http://localhost:5173`). |
| JWT secret | Required when `DEBUG=false` (validated in `config.py`). |
| Student ↔ User link | `Student.user_id` is `unique` FK to `users.id` (added in migration `388e5e496455`). |
| Frontend typecheck | `npm run check` generates `.svelte-kit/` (gitignored) via `svelte-kit sync`. |

## Docs Reference

### Design
- `docs/design/wireframes.md` — 47-screen wireframe catalog (admin/professor/student/shared)
- `docs/design/database-er.md` — ERD with target schema (programs, year_levels, courses, etc.)

### Proposals
- `docs/proposals/proposal.md` — full 11-section proposal
- `docs/proposals/proposal_simple.md` — 1-page summary
- `docs/proposals/models.md` — ML/AI model catalog
- `docs/proposals/contributions.md` — CS contributions mapping

### Architecture
- `docs/architecture/project-structure.md` — intended backend + frontend layout
- `docs/architecture/frontend-architecture.md` — production-ready frontend structure
- `docs/architecture/api-contracts.md` — full API endpoint inventory with request/response schemas
- `docs/architecture/offline-first.md` — IndexedDB sync algorithm & conflict handling
- `docs/architecture/security-model.md` — threat model & mitigations
- `docs/architecture/data-flow.md` — sequence diagrams for all major flows
- `docs/architecture/migration-strategy.md` — Alembic migration plan (current → target schema)
- `docs/architecture/face-enrollment.md` — 3-photo enrollment & embedding pipeline
- `docs/architecture/excuse-workflow.md` — state machine & permission matrix
- `docs/architecture/risk-model.md` — heuristic at-risk prediction & batch job spec

### Deployment
- `docs/deployment/deployment-workflow.md` — free-tier: Supabase → Fly.io → Vercel
- `docs/deployment/backup-strategy.md` — full pg_dump pipeline, encryption, retention
- `docs/deployment/production-checklist.md` — secrets, CORS, storage, first-admin seeding

### Developer
- `docs/developer/backend-setup.md` — Docker Compose, env setup, alembic, seed script
- `docs/developer/frontend-setup.md` — Node, runes mode, Chart.js, service worker
- `docs/developer/feature-template.md` — vertical-slice checklist (model→router→frontend)
- `docs/developer/coding-standards.md` — Python, TypeScript/Svelte, git conventions

### Operations
- `docs/operations/runbooks.md` — restore, rollback, unlock, re-enroll, sync-clear, key rotation
- `docs/operations/monitoring.md` — health endpoints, metrics, SLOs
- `docs/operations/incident-response.md` — spoof spike, DB outage, sync flood, backup drill

### Testing
- `docs/testing/test-plan.md` — portal×feature matrix + decision coverage (D1–D43)
- `docs/testing/test-data.md` — seed spec (3 programs, 42 students, 6-week history)
- `docs/testing/performance-benchmarks.md` — scan latency, concurrent sync, risk batch targets

### Guides
- `docs/guides/admin-manual.md` — program setup, imports, assignment, analytics, backup
- `docs/guides/professor-manual.md` — sessions, windows, excuses, reports
- `docs/guides/student-manual.md` — 5-step scan, offline, excuses, calendar
- `docs/guides/face-enrollment-guide.md` — 3-photo capture script & privacy notes

### Project
- `docs/project/decision-log.md` — authoritative decision log (D1–D43)
- `docs/project/glossary.md` — terminology definitions
- `docs/project/roadmap.md` — implementation phases with dependency graph

### Presentations
- `docs/presentations/presentation-slides.md` — presentation content
- `docs/presentations/presentation.pptx` — slide deck