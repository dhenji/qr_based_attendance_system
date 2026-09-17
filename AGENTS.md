# AGENTS.md — QR-Based Attendance System

**FastAPI backend** (13 feature slices / 16 models + 1 baseline Alembic migration; every router is an empty stub) + **SvelteKit frontend** (mock-first). No linters, formatters, backend tests, or CI — `npm run check` (svelte-check) is the only automated check. `README.md` is current and accurate; when docs conflict, trust `README.md` + executable config over older guides.

## Repository State

- Remote: `git@github.com:CodeKharl/qr_based_attendance_system.git`. Branches/PRs against `main`.
- Layout: `frontend/`, `backend/` (models + migrations + `Dockerfile.dev`), root `docker-compose.dev.yml`, `docs/`.
- Root `.gitignore` ignores `.env`/`.env.*` but un-ignores `.env.example` and `.env.test`. `backend/.env` exists (ignored) — never commit it.
- App is rebranded **"Attendly"** on the frontend landing page; docs/README still use "QR-Based Attendance System".

## Key Commands

### Local Dev (Docker — recommended)
```bash
docker compose -f docker-compose.dev.yml up --build          # API on :8000, Postgres on :5432, frontend on :5173, migrations run automatically
```

### Manual Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
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
npm run check                      # typecheck (runs svelte-kit sync first; watch w/ check:watch)
```

## Backend (`backend/`)

- **Entry**: `src/main.py` — FastAPI app, `/health`, CORS, lifespan runs `SELECT 1` at startup (**fails to boot if DB unreachable**).
- **Config**: `src/core/config.py` — pydantic-settings, `get_settings()` cached. Many settings in `.env.example`: backup pipeline, risk-scoring batch, face-match thresholds, account lockout/OTP, attachment storage, Turnstile.
- **Database**: `src/core/database.py` — async engine + session factory + `Base(DeclarativeBase)`.
- **Dependencies**: `src/api/deps.py` — `get_db`, `get_current_user` (JWT/HTTPBearer), `require_role(*roles)`.
- **Exceptions**: `src/core/exceptions.py` — `AppException` (caught by main.py handler), `DomainException` (422), `DatabaseException` (409).
- **Security**: `src/core/security.py` — Argon2id hashing, JWT access/refresh tokens, 6-digit OTP generation.
- **Models** (all in `src/features/*/model.py`, subclass `core.database.Base`), 16 classes across 13 slices:
  - `auth.User` + `auth.OtpCodes`
  - `student.Student` — `user_id` unique FK to users (1:1); has `face_embedding` (LargeBinary), `face_enrolled_at`, `face_embedding_version`
  - `professor.Professor` — `user_id` unique FK to users (1:1)
  - `course.Course` (template) + `course.CourseOffering` — geofence `classroom_*` fields live here
  - `course_professor.CourseProfessor` (table `course_professors`)
  - `enrollment.Enrollment` — `student_id`, `offering_id`, `academic_year`, `semester`
  - `session.Session` — `session_code` unique, `expires_at`, `classroom_radius_meters`
  - `attendance.Attendance` (table `attendance_records`) — `liveness_evidence` (JSONB), `face_match_score` (NUMERIC(5,4)), `scanned_via`, `original_status`, `excuse_type`/`excuse_reason`/`excused_by`/`excused_at`, `excuse_request_id`
  - `sync.SyncQueue`
  - `excuse.ExcuseRequest` (table `excuse_requests`) — `initiated_by`/`initiated_via`, `reason`, `attachment_urls` (JSONB), `status`, `requested_at`, `reviewed_by`/`reviewed_at`
  - `program.Program` + `program.YearLevel`
  - `analytics.StudentRiskScore` (table `student_risk_scores`) — risk scoring infra
  - `system.BackupLog` (table `backup_log`) — backup pipeline tracking
- **Routers**: `src/api/router.py` mounts 5 of 7 router stubs under `/api`: auth→`/api/auth`, student→`/api/student`, session→`/api/professor`, attendance→`/api/student`, professor→`/api/professor`. `course` and `enrollment` routers exist but are **not mounted**. All 7 routers are empty `APIRouter()` stubs.
- **Implemented layers**: only `auth/schema.py`, `auth/constants.py`, `shared/validators.py`, `course_professor/service.py`. `service.py`/`schema.py` missing for all other features; `shared/dependencies.py`/`cache.py` missing; `src/tests/` is an empty scaffold.
- **Alembic**: 1 baseline migration (`679a319c12d6`) creating the 16-table target schema. To add a table: write model → add `import features.X.model` to `alembic/env.py` → `alembic revision --autogenerate -m "..."` + `alembic upgrade head`.
- **Shared**: `src/shared/enums.py` (13 StrEnum), `mixins.py`, `pagination.py`, `base.py` (BaseCRUD generic), `email.py`, `validators.py`.
- **Dockerfile.dev**: 3-stage — `builder` (venv at `/opt/venv`) → `runtime` (uvicorn) → `migrate` (alembic upgrade head).

## Frontend (`frontend/`)

- **Stack**: SvelteKit 2 + Svelte 5, TypeScript strict. Deps: `html5-qrcode`, `zod`.
- **Runes mode forced** via `vite.config.ts` `compilerOptions.runes` — write `$state`/`$props` runes, not legacy reactive declarations.
- **Mock-first**: `src/lib/api/client.ts` has `MOCK = true` — all service calls return fake data from `src/lib/api/endpoints.ts`. Set to `false` when backend endpoints land.
- **Pages**: `+page.svelte` (landing), `auth/login`, `auth/register`, `auth/forgot-password`, `student/dashboard`, `student/scan`, `professor/sessions`.
- **Feature services**: `src/lib/features/{auth,student,session,attendance,liveness,sync}/service.ts` — mock implementations. Also: `auth/security.ts` (captcha/OTP/security-question helpers), `auth/store.svelte.ts` + `student/store.svelte.ts` (runes stores), `liveness/components/QRScanner.svelte`, `student/components/DashboardStats.svelte`.
- **Shared**: `src/lib/shared/types/` (mirror backend models), `constants/` (routes, status, roles), `utils/` (qr, geo/Haversine, format, gen).
- `src/lib/shared/delete_if_done` is a stray tracked placeholder file — delete when wrapping up.
- `.npmrc` sets `engine-strict=true` — `npm install` fails if Node doesn't satisfy dep engine ranges.
- Env: only `PUBLIC_*` vars reach browser (`PUBLIC_API_URL=http://localhost:8000`).
- Planned architecture (see `docs/architecture/frontend-architecture.md`): feature-slice structure under `src/lib/features/` with `store.svelte.ts`, `service.ts`, `schema.ts`, `mock.ts`, `components/`.

## Gotchas & Quirks

| Area | Detail |
|------|--------|
| DB connection | FastAPI lifespan runs `SELECT 1` at startup — container fails if Postgres not ready. Compose handles via `depends_on: condition: service_healthy`. |
| Alembic model imports | `alembic/env.py` imports models using `features.*.model` (not `src.features...`). Must `cd backend` so imports resolve. All 13 feature models are already imported and the single baseline migration exists — only autogenerate if you actually add/change a model, and remember to add the new `import features.X.model`. |
| Frontend mock mode | `MOCK = true` in `src/lib/api/client.ts`. All API calls return mock data. No real backend integration yet. |
| Env files | Backend reads `.env` from `backend/` (not root). Frontend reads `.env` from `frontend/`. |
| CORS | `CORS_ORIGINS` in backend `.env` must include frontend origin (`http://localhost:5173`). |
| JWT secret | Required when `DEBUG=false` (validated in `config.py`); `HMAC_SECRET_KEY` used for session codes. |
| Student/User link | `Student.user_id` is a unique FK to `users.id` (1:1). Same for `Professor.user_id`. |
| Unmounted routers | `course` and `enrollment` routers exist in `src/features/{course,enrollment}/router.py` but are not imported in `src/api/router.py`. |
| Frontend typecheck | `npm run check` generates `.svelte-kit/` (gitignored) via `svelte-kit sync`. |

## Docs Reference

Key docs an agent is likely to need (README.md links the full inventory):

### Architecture
- `docs/architecture/api-contracts.md` — full API endpoint inventory with request/response schemas
- `docs/architecture/frontend-architecture.md` — production-ready frontend structure
- `docs/architecture/migration-strategy.md` — Alembic migration plan (current → target → planned 19-table)
- `docs/architecture/security-model.md` — threat model & mitigations (auth: OTP, lockout, Turnstile, security questions)
- `docs/architecture/offline-first.md` — IndexedDB sync & conflict handling
- `docs/architecture/excuse-workflow.md` — excuse state machine & permission matrix
- `docs/architecture/face-enrollment.md` — 3-photo enrollment & embedding pipeline
- `docs/architecture/risk-model.md` — at-risk prediction & batch job spec
- `docs/architecture/data-flow.md` — sequence diagrams for all major flows

### Developer
- `docs/developer/feature-template.md` — vertical-slice checklist (model → router → frontend)
- `docs/developer/coding-standards.md` — Python, TypeScript/Svelte, git conventions
- `docs/developer/backend-setup.md` + `docs/developer/frontend-setup.md` — setup guides, seed script
- `docs/project/roadmap.md` — 13-phase implementation roadmap (Phase 0 done, 12 is a gap)

### Decision tracking & ops
- `docs/project/decision-log.md` — authoritative decision log (D1–D54, e.g. D27 5-step scan flow, D15 rejection reasons)
- `docs/operations/runbooks.md` — restore, rollback, unlock, re-enroll, key rotation
- `docs/testing/test-plan.md` — portal×feature matrix & decision coverage
- `docs/deployment/production-checklist.md` — secrets, CORS, storage, first-admin seeding
- `docs/guides/{student,professor,admin}-manual.md` — end-user flows