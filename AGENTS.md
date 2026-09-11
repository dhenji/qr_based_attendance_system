# AGENTS.md — QR-Based Attendance System

**FastAPI backend** (models + Alembic migrations, service/schema/router layers mostly empty) + **SvelteKit frontend** (mock-first, pages exist but mostly wired to mock data). No linters, formatters, tests, or CI — `npm run check` (svelte-check) is the only automated check.

## Repository State

- Remote: `git@github.com:CodeKharl/qr_based_attendance_system.git`. Branches/PRs against `main`.
- Layout: `frontend/`, `backend/` (models + migrations + `Dockerfile.dev`), root `docker-compose.yml`, `docs/`.
- Root `.gitignore` ignores `.env`/`.env.*` but un-ignores `.env.example` and `.env.test`. `backend/.env` exists (ignored) — never commit it.

## Key Commands

### Local Dev (Docker — recommended)
```bash
docker compose up --build          # API on :8000, Postgres on :5432, migrations run automatically
```

### Manual Backend
```bash
cd backend
cp .env.example .env
alembic upgrade head
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

- **Entry**: `src/main.py` — FastAPI app, `/health`, CORS, lifespan runs `SELECT 1` at startup (**fails to boot if DB unreachable**).
- **Config**: `src/core/config.py` — pydantic-settings, `get_settings()` cached.
- **Database**: `src/core/database.py` — async engine + session factory + `Base(DeclarativeBase)`.
- **Dependencies**: `src/api/deps.py` — `get_db`, `get_current_user` (JWT/HTTPBearer), `require_role(*roles)`.
- **Exceptions**: `src/core/exceptions.py` — `AppException` (caught by main.py handler), `DomainException` (422), `DatabaseException` (409).
- **Security**: `src/core/security.py` — Argon2id hashing, JWT access/refresh tokens, 6-digit OTP generation.
- **Models** (all in `src/features/*/model.py`, subclass `core.database.Base`):
  - `auth.User` + `auth.OtpCodes`
  - `student.Student` — `user_id` unique FK to users
  - `professor.Professor` — `user_id` unique FK to users
  - `course.Course` (template: `course_code`, `course_name`, `units`, `session_duration_hours`) + `course.CourseOffering` — geofence `classroom_*` fields live here
  - `enrollment.Enrollment` — `student_id`, `offering_id` (FK → course_offerings), `academic_year`, `semester`
  - `session.Session` — `session_code` unique, `expires_at`, `classroom_radius_meters`
  - `attendance.AttendanceRecord` (table: `attendance_records`) — `liveness_evidence` (JSONB), `face_match_score` (NUMERIC(5,4)), `scanned_via`, `original_status`, `excuse_type`/`excuse_reason`/`excused_*` fields
  - `sync.SyncQueue`
  - `excuse.ExcuseRequest` (table: `excuse_requests`) — `initiated_by`/`initiated_via`, `reason`, `attachment_urls` (JSONB), `status`, `reviewed_by`/`reviewed_at`
  - `program.Program` + `program.YearLevel` — imported in `alembic/env.py`
- **Routers**: `src/api/router.py` mounts 5 routers under `/api`. `course` and `enrollment` routers exist as files but are **not mounted**. All mounted routers are currently empty stubs.
- **Alembic**: 3 migrations in `alembic/versions/`. To add a table: write model, add `import features.X.model` to `alembic/env.py`, then `alembic revision --autogenerate -m "..."` + `alembic upgrade head`.
- **Shared**: `src/shared/enums.py` (15 StrEnum classes), `src/shared/mixins.py`, `src/shared/pagination.py`, `src/shared/base.py` (BaseCRUD generic), `src/shared/email.py`.
- **Missing**: `service.py` and `schema.py` for all features (incl. `excuse`, which has model only); `src/shared/dependencies.py`/`cache.py`; `src/tests/` is empty.
- **Dockerfile.dev**: 3-stage — `builder` (venv at `/opt/venv`) → `runtime` (uvicorn) → `migrate` (alembic upgrade head).

## Frontend (`frontend/`)

- **Stack**: SvelteKit 2 + Svelte 5, TypeScript strict. Deps: `html5-qrcode`, `zod`.
- **Runes mode forced** via `vite.config.ts` `compilerOptions.runes` — write `$state`/`$props` runes, not legacy reactive declarations.
- **Mock-first**: `src/lib/api/client.ts` has `MOCK = true` — all service calls return fake data from `src/lib/api/endpoints.ts`. Set to `false` when backend endpoints land.
- **Pages exist**: `+page.svelte` (landing), `auth/login`, `auth/register`, `student/dashboard`, `student/scan`, `professor/sessions`.
- **Feature services**: `src/lib/features/{auth,student,session,attendance,liveness,sync}/service.ts` — mock implementations. Auth and student also have `store.svelte.ts`.
- **Shared types**: `src/lib/shared/types/` — mirrors backend models (`user.ts`, `student.ts`, `course.ts`, etc.).
- `.npmrc` sets `engine-strict=true` — `npm install` fails if Node doesn't satisfy dep engine ranges.
- Env: only `PUBLIC_*` vars reach browser (`PUBLIC_API_URL=http://localhost:8000`).
- Planned architecture (see `docs/architecture/frontend-architecture.md`): feature-slice structure under `src/lib/features/` with `store.svelte.ts`, `service.ts`, `schema.ts`, `mock.ts`, `components/`.

## Gotchas & Quirks

| Area | Detail |
|------|--------|
| DB connection | FastAPI lifespan runs `SELECT 1` at startup — container fails if Postgres not ready. Compose handles via `depends_on: condition: service_healthy`. |
| Alembic model imports | `alembic/env.py` imports models using `features.*.model` (not `src.features...`). Must `cd backend` so imports resolve. Currently imports all feature models incl. `features.program.model`. When `features/excuse/model.py` (ExcuseRequest) is created, add `import features.excuse.model` before regenerating migrations. |
| Frontend mock mode | `MOCK = true` in `src/lib/api/client.ts`. All API calls return mock data. No real backend integration yet. |
| Env files | Backend reads `.env` from `backend/` (not root). Frontend reads `.env` from `frontend/`. |
| CORS | `CORS_ORIGINS` in backend `.env` must include frontend origin (`http://localhost:5173`). |
| JWT secret | Required when `DEBUG=false` (validated in `config.py`). |
| Student/User link | `Student.user_id` is a unique FK to `users.id` (1:1). Same for `Professor.user_id`. |
| Unmounted routers | `course` and `enrollment` routers exist in `src/features/{course,enrollment}/router.py` but are not imported in `src/api/router.py`. |
| Frontend typecheck | `npm run check` generates `.svelte-kit/` (gitignored) via `svelte-kit sync`. |

## Docs Reference

Key docs that an agent is likely to need:

### Architecture
- `docs/architecture/api-contracts.md` — full API endpoint inventory with request/response schemas
- `docs/architecture/frontend-architecture.md` — production-ready frontend structure
- `docs/architecture/migration-strategy.md` — Alembic migration plan (current → target schema)
- `docs/architecture/project-structure.md` — intended backend + frontend layout
- `docs/architecture/security-model.md` — threat model & mitigations
- `docs/architecture/data-flow.md` — sequence diagrams for all major flows

### Developer
- `docs/developer/feature-template.md` — vertical-slice checklist (model → router → frontend)
- `docs/developer/coding-standards.md` — Python, TypeScript/Svelte, git conventions
- `docs/developer/backend-setup.md` — Docker Compose, env setup, alembic, seed script

### Other
- `docs/design/database-er.md` — ERD with target schema
- `docs/project/roadmap.md` — implementation phases with dependency graph
- `docs/project/decision-log.md` — authoritative decision log
- `README.md` — project overview, is current and accurate