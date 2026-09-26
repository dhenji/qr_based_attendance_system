# AGENTS.md — QR-Based Attendance System

**FastAPI backend** (14 feature slices / 17 models + 3 Alembic migrations; `auth` and `admin` routers fully implemented, the rest are prefix-only stubs) + **SvelteKit frontend** (mock-first). Backend has a pytest suite (56 tests) but **no linters, formatters, or CI**. `README.md` is current and accurate; when docs conflict, trust `README.md` + executable config over older guides.

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

### Backend Tests
```bash
cd backend
DEBUG=true JWT_SECRET=test-secret-0123456789abcdef PYTHONPATH=src .venv/bin/python -m pytest src/tests -q
```
`DEBUG=true` + a dummy `JWT_SECRET` are required or `Settings` validation fails at import. There is no `conftest.py`; the suite uses hand-rolled fakes (fake `AsyncSession`/settings) and never touches a real database.

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
- **Dependencies**: `src/api/deps.py` — `_get_db` (the session dep; **there is no public `get_db`**), `_get_current_user` (JWT/HTTPBearer), `require_role(*roles)`, plus `AuthServiceDep` / `AdminServiceDep` annotated service deps. Use these names; the underscore-prefixed ones are the sanctioned spelling.
- **Exceptions**: `src/core/exceptions.py` — `AppException` (caught by main.py handler), `DomainException` (422), `DatabaseException` (409). Feature slices add their own `exceptions.py` (9 exist).
- **Security**: `src/core/security.py` — Argon2id hashing, JWT access/refresh tokens, 6-digit OTP generation, **recovery-grant tokens** (`create_recovery_token` / `decode_recovery_token`, `type="recovery"`, TTL `recovery_token_expire_minutes`), and **backup-code fingerprints** (`backup_code_fingerprint`, HMAC-SHA256 over `HMAC_SECRET_KEY` or `JWT_SECRET`).
- **Models** (all in `src/features/*/model.py`, subclass `core.database.Base`), 17 classes across 14 slices:
  - `auth.User` + `auth.OtpCodes`
  - `auth.MfaBackupCodes` (table `mfa_backup_codes`) — `code_hash` (Argon2id) **and** `code_fingerprint` (HMAC-SHA256, indexed) so verification is one indexed lookup + one hash instead of scanning every row
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
- **Routers**: `src/api/router.py` mounts 6 of 8 router stubs under `/api`: auth→`/api/auth`, admin→`/api/admin/users`, student→`/api/student`, session→`/api/professor`, attendance→`/api/student`, professor→`/api/professor`. `course` and `enrollment` routers exist but are **not mounted**. Prefixes are baked into each `APIRouter`; `include_router` is called with **no** `prefix=` argument. Several routers may share one mount point (professor+session at `/professor`, student+attendance at `/student`) — their inner paths must not collide. One `APIRouter` per (feature, mount point); never mount the same router twice. Only auth and admin have real routes; the other six are prefix-only stubs.
- **Implemented layers**: `auth/{schema,constants,service,router}.py` and `admin/{schema,constants,service,router}.py` are complete; `shared/{validators,base,captcha,rate_limit,dependencies,cache,pagination,mixins,email,enums}.py` and `course_professor/service.py` exist. `service.py`/`schema.py` still missing for student, professor, session, attendance, course, enrollment, program, excuse, analytics, sync, system.
- **Alembic**: 3 migrations — `679a319c12d6` (baseline, 16 tables), `2a437ca93c53` (adds `mfa_backup_codes`), `33eabbfbfa6a` (adds `mfa_backup_codes.code_fingerprint` + index). To add a table: write model → add `import features.X.model` to `alembic/env.py` → `alembic revision --autogenerate -m "..."` + `alembic upgrade head`. `alembic check` must report "No new upgrade operations detected" before you call the schema done.
- **Shared**: `src/shared/enums.py` (13 StrEnum), `mixins.py`, `pagination.py`, `base.py` (BaseCRUD generic), `email.py`, `validators.py`, `captcha.py`, `rate_limit.py`, `dependencies.py`, `cache.py`.
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
| Service classes | Admin CRUD slices (`/admin/*`: program, course, student-admin, professor-admin) implement `class <Feature>Service` with one `BaseCRUD` handle per model, reached via `<Feature>ServiceDep` in `api/deps.py` — a standing rule, not a per-slice argument (ADR-058). Everything else (`face_enrollment`, `shared/csv_import.py`) stays module-level functions (ADR-055); `course_professor/service.py` is a retained borderline class, not a precedent. |
| Recovery flow | Step 2 of forgot-password returns a 5-min `type="recovery"` grant; a `forget_password` OTP cannot be minted without it. Unknown emails get a **deterministic** decoy question (ADR-056). |
| Security question | Only the answer is Argon2id-hashed; `users.security_question_hash` holds the question in readable plaintext under a legacy name (ADR-056). Do not "fix" this without revisiting step 1's contract. |
| Frontend mock mode | `MOCK = true` in `src/lib/api/client.ts`. All API calls return mock data. No real backend integration yet. |
| Env files | Backend reads `.env` from `backend/` (not root). Frontend reads `.env` from `frontend/`. |
| CORS | `CORS_ORIGINS` in backend `.env` must include frontend origin (`http://localhost:5173`). |
| JWT secret | Required when `DEBUG=false` (validated in `config.py`); `HMAC_SECRET_KEY` used for session codes, and falls back to `JWT_SECRET` for backup-code fingerprints. |
| Student/User link | `Student.user_id` is a unique FK to `users.id` (1:1). Same for `Professor.user_id`. |
| Unmounted routers | `course` and `enrollment` routers exist in `src/features/{course,enrollment}/router.py` but are not imported in `src/api/router.py`. |
| Trailing slashes | Collection routes use `@router.get("")`/`@router.post("")` so the path matches the contract exactly (`/api/admin/users`, not `/api/admin/users/`). Using `"/"` adds a redirect. |
| Phase 3 routing | Phase 3 adds 6 new mounts and must NOT re-mount `student/router.py` or `professor/router.py` (already live at `/api/student`, `/api/professor`) — it needs `student/admin_router.py` + `professor/admin_router.py` instead. `features/course/` needs two routers (`router.py` → `/admin/courses`, `offering_router.py` → `/admin/offerings`). `enrollment/router.py` stays unmounted. Face enrollment is its own slice with no model/migration. Full rationale in ADR-057. |
| Phase 3 aggregates | `scan_count`, `course_count`, `year_level_count`, `terms_count`, `enrolled_count` are derived per request, not columns. `terms_count` = `sum(len(yl.term_structure["terms"]))` — the JSONB shape is `{terms:[{code,label}]}`, so bare `len(term_structure)` silently returns 1. `course_count` has no `courses.program_id` to count (D44) — it is `COUNT(DISTINCT course_offerings.course_id)` per program. The resulting N+1 is accepted at Phase 3 volumes (ADR-057/058). |
| Phase 3 soft archive | `DELETE /admin/programs/{id}` flips `programs.is_active` **only** — `year_levels` has no `is_active` column and `courses` has no program FK (D44), so the contract's old "cascades year-levels/courses inactive" line is stale; there is nothing to cascade to (ADR-058). Do not invent a cascade. |
| Phase 3 hard delete | `DELETE /admin/{students,professors}/{id}/archive` needs a has-records guard (409) — `enrollments`/`attendance_records`/`excuse_requests`/`sessions` are `ondelete=RESTRICT`, so the `is_active` check alone 500s. Do not relax them to CASCADE (ADR-057). |
| Frontend typecheck | `npm run check` generates `.svelte-kit/` (gitignored) via `svelte-kit sync`. |

## Docs Reference

Key docs an agent is likely to need (README.md links the full inventory):

### Architecture
- `docs/architecture/api-contracts.md` — full API endpoint inventory with request/response schemas
- `docs/architecture/frontend-architecture.md` — production-ready frontend structure
- `docs/architecture/migration-strategy.md` — Alembic migration plan (current → target → planned 19-table; 17 tables landed)
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
- `docs/project/decision-log.md` — authoritative decision log (D1–D58, e.g. D27 5-step scan flow, D15 rejection reasons, ADR-055 service classes, ADR-056 recovery hardening, ADR-057 Phase 3 routing, ADR-058 admin CRUD slice template)
- `docs/operations/runbooks.md` — restore, rollback, unlock, re-enroll, key rotation
- `docs/testing/test-plan.md` — portal×feature matrix & decision coverage
- `docs/deployment/production-checklist.md` — secrets, CORS, storage, first-admin seeding
- `docs/guides/{student,professor,admin}-manual.md` — end-user flows