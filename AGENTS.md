# AGENTS.md — QR-Based Attendance System

**FastAPI backend** (15 feature slices / 17 models + 4 Alembic migrations; 12 routers with routes, enrollment intentionally unmounted) + **SvelteKit frontend** (real API by default, mock opt-in via `PUBLIC_MOCK_MODE`; attendance ledger + excuse queue are hard-coded mock until their backend endpoints land). Backend has a pytest suite (116 test functions / 119 cases) but **no linters, formatters, or CI**. `README.md` is current and accurate; when docs conflict, trust `README.md` + executable config over older guides.

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
- **Dependencies**: `src/api/deps.py` — `_get_db` (the session dep; **there is no public `get_db`**), `_get_current_user` / `_get_optional_current_user` (JWT/HTTPBearer), `require_role(*roles)`, plus `Auth/Admin/Program/Course/Student/Professor/Session/FaceEnrollmentServiceDep` annotated service deps. Use these names; the underscore-prefixed ones are the sanctioned spelling.
- **Exceptions**: `src/core/exceptions.py` — `AppException` (caught by main.py handler), `DomainException` (422), `DatabaseException` (409). Feature slices add their own `exceptions.py` (11 exist).
- **Security**: `src/core/security.py` — Argon2id hashing, JWT access/refresh tokens (plus pre-auth claim tokens), 6-digit OTP generation, **recovery-grant tokens** (`create_recovery_token` / `decode_recovery_token`, `type="recovery"`, TTL `recovery_token_expire_minutes`), **backup-code fingerprints** (`backup_code_fingerprint`, HMAC-SHA256 over `HMAC_SECRET_KEY` or `JWT_SECRET`), and **session codes + QR payloads** (`generate_session_code` / `verify_session_code`, 8-char base62 HMAC over the session id; `build_qr_payload`, versioned JSON `{v, code, offering, radius, pw, lw}`).
- **Models** (all in `src/features/*/model.py`, subclass `core.database.Base`), 17 classes across 13 model files (`admin` and `face_enrollment` are model-less):
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
- **Routers**: `src/api/router.py` mounts 12 routers under `/api` (no `prefix=` arg — prefixes baked into each `APIRouter`): 12 with routes — auth→`/api/auth` (15), admin→`/api/admin/users` (3), program→`/api/admin/programs` (10), course→`/api/admin/courses` (5), offering→`/api/admin/offerings` (10), student-admin→`/api/admin/students` (7), professor-admin→`/api/admin/professors` (6), face-enrollment→`/api/admin/face-enrollment` (2), session-professor(7)→`/api/professor` (courses, sessions list/history/create, active detail, close, attendance), professor-self(2)→`/api/professor` (profile read + password patch), student(2)→`/api/student` (sessions verify-code, face-embedding pull), attendance(2)→`/api/student` (scan, history) — the last two share one mount; inner paths must not collide. `enrollment/router.py` exists but is intentionally unmounted. One `APIRouter` per (feature, mount point); never mount the same router twice.
- **Implemented layers**: `service.py` ×10 (auth, admin, program, course, student, professor, session, face_enrollment, course_professor, attendance), `schema.py` ×9 (same minus course_professor, plus attendance), `constants.py` ×8 (same plus attendance), `exceptions.py` ×11. `shared/{validators,base,captcha,rate_limit,dependencies,cache,pagination,mixins,email,enums,csv_import}.py` exists. Still model-only: sync, excuse, analytics, system. Still model + stub-router only: enrollment.
- **Alembic**: 4 migrations — `679a319c12d6` (baseline, 16 tables), `2a437ca93c53` (adds `mfa_backup_codes`), `33eabbfbfa6a` (adds `mfa_backup_codes.code_fingerprint` + index), `c3e913d02be0` (adds `enrollments.created_at`). To add a table: write model → add `import features.X.model` to `alembic/env.py` → `alembic revision --autogenerate -m "..."` + `alembic upgrade head`. `alembic check` must report "No new upgrade operations detected" before you call the schema done.
- **Shared**: `src/shared/enums.py` (13 StrEnum), `mixins.py`, `pagination.py`, `base.py` (BaseCRUD generic), `email.py`, `validators.py`, `captcha.py`, `rate_limit.py`, `dependencies.py`, `cache.py`, `csv_import.py`.
- **Dockerfile.dev**: 3-stage — `builder` (venv at `/opt/venv`) → `runtime` (uvicorn) → `migrate` (alembic upgrade head).

## Frontend (`frontend/`)

- **Stack**: SvelteKit 2 + Svelte 5, TypeScript strict. Deps: `html5-qrcode`, `zod`, `@mediapipe/tasks-vision` (no `chart.js`).
- **Runes mode forced** via `vite.config.ts` `compilerOptions.runes` as a function (real code → `true`, `node_modules` → exempt) — write `$state`/`$props` runes, not legacy reactive declarations.
- **Mock opt-in, not mock-first**: `src/lib/api/client.ts` sets `MOCK = PUBLIC_MOCK_MODE === 'true'` — real API calls by default; fixtures from `src/lib/api/endpoints.ts` (18 typed `EndpointDef`s) only when explicitly enabled.
- **Pages** (24): `+page.svelte` (Attendly landing), `about`, `cookies`, `privacy-policy`, `auth/login`, `auth/register`, `auth/forgot-password`, `student/dashboard`, `student/scan`, `student/schedule`, `student/history`, `student/profile`, `student/settings`, `professor/dashboard`, `professor/courses`, `professor/reports`, `professor/sessions` (+ `create`, `history`, `active/[id]`), `professor/attendance`, `professor/excuse-requests`, `professor/profile`, `professor/settings`.
- **Feature services**: `src/lib/features/{auth,student,session,attendance,liveness,sync,report,settings,excuse}/service.ts` (plus `professor/schedule.ts`, no `professor/service.ts`; plus `excuse/mock.ts`). Also: `auth/{security,errors,tokens}.ts` + `auth/mock.ts`, `report/mock.ts`, `professor/mock.ts`, `auth/store.svelte.ts` + `student/store.svelte.ts` (runes stores), `liveness/{model,service}.ts`, `liveness/components/{QRScanner,FaceScanner}.svelte`, `student/components/DashboardStats.svelte`, `report/components/{ReportBarChart,ReportTrendChart}.svelte`. No `schema.ts` exists under `src/lib/`. `attendance` (professor ledger) and `excuse` (review queue) services use a hard-coded `MOCK = true` — unlike the global `PUBLIC_MOCK_MODE` flag — until their backend endpoints land.
- **Shared**: `src/lib/shared/types/` (`index/auth/user/student/professor/session/attendance/course/enrollment/excuse/liveness/sync`, mirror backend models), `constants/` (routes, status, roles), `utils/` (qr, geo/Haversine, format, gen).
- `.npmrc` sets `engine-strict=true` — `npm install` fails if Node doesn't satisfy dep engine ranges.
- Env: only `PUBLIC_*` vars reach browser (`PUBLIC_API_URL=http://localhost:8000`, `PUBLIC_MOCK_MODE=false`).
- Planned architecture (see `docs/architecture/frontend-architecture.md`): feature-slice structure under `src/lib/features/` with `store.svelte.ts`, `service.ts`, `schema.ts`, `mock.ts`, `components/`.

## Gotchas & Quirks

| Area | Detail |
|------|--------|
| DB connection | FastAPI lifespan runs `SELECT 1` at startup — container fails if Postgres not ready. Compose handles via `depends_on: condition: service_healthy`. |
| Alembic model imports | `alembic/env.py` imports models using `features.*.model` (not `src.features...`). Must `cd backend` so imports resolve. All 13 feature models are already imported and the head migration is `c3e913d02be0` — only autogenerate if you actually add/change a model, and remember to add the new `import features.X.model`. |
| Service classes | Admin CRUD slices (`/admin/*`: program, course, student-admin, professor-admin) implement `class <Feature>Service` with one `BaseCRUD` handle per model, reached via `<Feature>ServiceDep` in `api/deps.py` — a standing rule, not a per-slice argument (ADR-058). `face_enrollment` is also a class (`FaceEnrollmentService` + `FaceEnrollmentServiceDep`: session + `Settings`, ADR-059), as is `session` (`SessionService` + `SessionServiceDep`: session + `Settings`, owns professor sessions + attendance reads). Everything else (`shared/csv_import.py`) stays module-level functions (ADR-055); `course_professor/service.py` is a retained borderline class, not a precedent. |
| Recovery flow | Step 2 of forgot-password returns a 5-min `type="recovery"` grant; a `forget_password` OTP cannot be minted without it. Unknown emails get a **deterministic** decoy question (ADR-056). |
| Security question | Only the answer is Argon2id-hashed; `users.security_question_hash` holds the question in readable plaintext under a legacy name (ADR-056). Do not "fix" this without revisiting step 1's contract. |
| Frontend mock mode | `MOCK = PUBLIC_MOCK_MODE === 'true'` in `src/lib/api/client.ts` — real API calls by default; mocks only when explicitly enabled. |
| Env files | Backend reads `.env` from `backend/` (not root). Frontend reads `.env` from `frontend/`. Note: `recovery_token_expire_minutes` exists in `config.py` but `RECOVERY_TOKEN_EXPIRE_MINUTES` is missing from `backend/.env.example` (defaults to 5 in code). |
| CORS | `CORS_ORIGINS` in backend `.env` must include frontend origin (`http://localhost:5173`). |
| JWT secret | Required when `DEBUG=false` (validated in `config.py`); `HMAC_SECRET_KEY` used for session codes, and falls back to `JWT_SECRET` for backup-code fingerprints. |
| Student/User link | `Student.user_id` is a unique FK to `users.id` (1:1). Same for `Professor.user_id`. |
| Unmounted routers | `enrollment/router.py` exists but is intentionally unmounted — do not import it in `src/api/router.py`. |
| Trailing slashes | Collection routes use `@router.get("")`/`@router.post("")` so the path matches the contract exactly (`/api/admin/users`, not `/api/admin/users/`). Using `"/"` adds a redirect. |
| Phase 3 routing | Phase 3 landed 6 new mounts and must NOT re-mount `student/router.py` or `professor/router.py` (already live at `/api/student`, `/api/professor`) — it uses `student/admin_router.py` + `professor/admin_router.py` instead. `features/course/` has two routers (`router.py` → `/admin/courses`, `offering_router.py` → `/admin/offerings`). `enrollment/router.py` stays unmounted. Face enrollment is its own slice with no model/migration. Full rationale in ADR-057. |
| Professor route ownership | The `/api/professor` mount is shared by two routers: `features/session/router.py` owns `/professor/courses`, `/professor/sessions/*` and `/professor/attendance`; `features/professor/router.py` owns `/professor/profile*` only. Do not add profile paths to the session router or session paths to the professor router. `GET /professor/excuse-requests` has no backend endpoint yet — the frontend excuse queue is mock-only (D21) until the excuse slice grows past its model. |
| Phase 3 aggregates | `scan_count`, `course_count`, `year_level_count`, `terms_count`, `enrolled_count` are derived per request, not columns. `terms_count` = `sum(len(yl.term_structure["terms"]))` — the JSONB shape is `{terms:[{code,label}]}`, so bare `len(term_structure)` silently returns 1. `course_count` has no `courses.program_id` to count (D44) — it is `COUNT(DISTINCT course_offerings.course_id)` per program. The resulting N+1 is accepted at Phase 3 volumes (ADR-057/058). |
| Phase 3 soft archive | `DELETE /admin/programs/{id}` flips `programs.is_active` **only** — `year_levels` has no `is_active` column and `courses` has no program FK (D44), so the contract's old "cascades year-levels/courses inactive" line is stale; there is nothing to cascade to (ADR-058). Do not invent a cascade. |
| Phase 3 hard delete | `DELETE /admin/{students,professors}/{id}/archive` needs a has-records guard (409) — `enrollments`/`attendance_records`/`excuse_requests`/`sessions` are `ondelete=RESTRICT`, so the `is_active` check alone 500s. Do not relax them to CASCADE (ADR-057). |
| Frontend typecheck | `npm run check` generates `.svelte-kit/` (gitignored) via `svelte-kit sync`. |
| Backend tests | Suite is 116 functions / 119 cases; 2 session tests (`test_create_session_copies_offering_defaults`, `test_get_active_session_counts_tiles_and_banner`) pin a fixed `NOW = 2026-09-27 12:00 UTC` fixture and fail once the wall clock passes it — pre-existing clock sensitivity on `main`, not a regression. |

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
- `docs/project/decision-log.md` — authoritative decision log (D1–D58, e.g. D27 5-step scan flow, D15 rejection reasons, ADR-055 service classes, ADR-056 recovery hardening, ADR-057 Phase 3 routing, ADR-058 admin CRUD slice template, ADR-059 face-enrollment class)
- `docs/operations/runbooks.md` — restore, rollback, unlock, re-enroll, key rotation
- `docs/testing/test-plan.md` — portal×feature matrix & decision coverage
- `docs/deployment/production-checklist.md` — secrets, CORS, storage, first-admin seeding
- `docs/guides/{student,professor,admin}-manual.md` — end-user flows