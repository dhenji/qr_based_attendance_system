# AGENTS.md — QR-Based Attendance System

FastAPI backend (15 feature slices, 17 models, 4 Alembic migrations) + SvelteKit 2 / Svelte 5 frontend. Real API by default, mock opt-in via `PUBLIC_MOCK_MODE`. No linters, formatters, or CI. `README.md` is current; when docs conflict, trust `README.md` + executable config.

## Repo state

- Remote `git@github.com:CodeKharl/qr_based_attendance_system.git`; PRs against `main`.
- Layout: `frontend/`, `backend/` (`src/` + `alembic/` + `Dockerfile.dev`), root `docker-compose.dev.yml`, `docs/`.
- Root `.gitignore` ignores `.env`/`.env.*` except `.env.example`/`.env.test`. `backend/.env` exists (ignored) — never commit it.
- Frontend landing page brands the app "Attendly"; docs still say "QR-Based Attendance System".

## Commands

```bash
docker compose -f docker-compose.dev.yml up --build          # API :8000, Postgres :5432, frontend :5173, migrations auto-run
docker compose -f docker-compose.dev.yml --profile test run --rm --build api-test  # backend suite in Docker
```

Manual backend (must run from `backend/` — imports are `features.*`, not `src.features.*`):
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn main:app --app-dir src --reload
```

Backend tests — SQLite in-memory by default (no Docker needed); `DEBUG` + `JWT_SECRET` required because some tests build `Settings()` directly:
```bash
cd backend
DEBUG=true JWT_SECRET=test-secret-0123456789abcdef PYTHONPATH=src .venv/bin/python -m pytest src/tests -q
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/attendance_test PYTHONPATH=src .venv/bin/python -m pytest src/tests -q  # same suite on Postgres
```
Markers in `backend/pytest.ini`: `-m "not slow"`, `-m "not integration"`. No `--cov` in `addopts`; add `--cov=src/features --cov=src/shared --cov=src/core` explicitly when needed.

Frontend (`engine-strict=true` in `.npmrc` — install fails on wrong Node):
```bash
cd frontend
npm install
cp .env.example .env   # only PUBLIC_* reaches the browser
npm run dev            # :5173
npm run check          # typecheck (runs svelte-kit sync first)
```

## Backend

- Entry `src/main.py`: `/health`, CORS, lifespan `SELECT 1` on boot — **fails to boot if DB unreachable**. Only `AppException` has a handler; `DomainException` → 422, `DatabaseException` → 409.
- Config `src/core/config.py`: pydantic-settings, `get_settings()` cached. `JWT_SECRET` required when `DEBUG=false`. `RECOVERY_TOKEN_EXPIRE_MINUTES` defaults to 5 in code but is missing from `backend/.env.example`.
- Deps `src/api/deps.py`: use `_get_db` (no public `get_db`), `_get_current_user` / `_get_optional_current_user`, `require_role(*roles)` (`super_admin` passes `admin` checks), `*ServiceDep` annotated service deps. `_get_db` commits on success, rolls back on any exception.
- Routers: `src/api/router.py` mounts under `/api` with **no `prefix=` arg — each `APIRouter` bakes its own prefix in**. One router per (feature, mount point); never mount the same router twice. `enrollment/router.py` is a stub and stays **unmounted**.
  - `/api/professor` is shared: `session/router.py` owns courses/sessions/attendance; `professor/router.py` owns `profile*` only. Don't cross them.
  - `/api/student` is shared: `student/router.py` (verify-code, face-embedding, schedule, profile) + `attendance/router.py` (scan, precheck, history). Inner paths must not collide.
  - `course/` has two routers (`router.py` → `/admin/courses`, `offering_router.py` → `/admin/offerings`).
  - Collection routes use `@router.get("")`, not `"/"` (trailing-slash redirect breaks the contract).
- Services: admin CRUD slices (`program`, `course`, `student`, `professor`) are `class <Feature>Service` with one `BaseCRUD` per model via `<Feature>ServiceDep` (ADR-058). `SessionService` and `FaceEnrollmentService` are also classes. Everything else stays module-level functions (ADR-055).
- Alembic: head is `c3e913d02be0` (4 migrations). New model → add `import features.X.model` to `alembic/env.py`, `alembic revision --autogenerate`, `alembic upgrade head`. `alembic check` must say "No new upgrade operations detected".
- Models (17 classes, 13 files; `admin` + `face_enrollment` model-less): `Student.user_id` / `Professor.user_id` are unique FKs to `users.id` (1:1). Deletes use `ondelete=RESTRICT` — archive routes need a has-records guard (409); never relax to CASCADE. `DELETE /admin/programs/{id}` flips `programs.is_active` only; there is nothing to cascade to (no `is_active` on year levels, no program FK on courses).
- Auth quirks: forgot-password step 2 returns a 5-min `type="recovery"` grant required to mint the OTP; unknown emails get a deterministic decoy question (ADR-056). `users.security_question_hash` stores the question in plaintext under a legacy name — only the answer is hashed; don't "fix" without revisiting the contract.
- Email: `shared/email.py` is the one delivery path — real `smtplib`, stdlib only, and it **never raises** (`debug` logs, empty `SMTP_HOST` logs+skips, otherwise implicit TLS 465 / STARTTLS 587). `SMTP_*` in `core/config.py` is deliberately unvalidated (unlike `JWT_SECRET`) so a deployment without a relay still boots. `send_otp_email` keeps its old signature because `auth/service.py` calls it inline; new code that must not block uses `dispatch_emails` (one executor job per batch, futures parked in `shared.email._PENDING`). Excuse notifications: copy in `features/excuse/notifications.py` (pure builders), recipient resolution + dispatch in `ExcuseService`, always last in the method so a raise sends nothing. Recipients read `users.email` first, then the profile's roster `email`. Only §8's four events notify — `quick_excuse`/`excuse_with_evidence`/`edit_excuse`/`revoke_excuse` are silent, and the in-app half is unimplemented (no table, by design).
- Scan flow (D27, rejection reasons D15): `POST /student/attendance/{scan,precheck}` resolve the student from the **authenticated user**, only *comparing* `payload.student_number` case-insensitively → `403 student_number_mismatch`. Same rule applies to any new student-facing endpoint taking an ID (e.g. excuse submit). Idempotency key is `user_id:session_id:X-Idempotency-Key`, 15-min TTL, process-local (like `rate_limit` — needs a shared store for multi-instance).

## Backend tests

- 386 cases / 25 files: sync hand-rolled-fake tests (`asyncio.run()`, unaffected by `asyncio_mode=auto` — don't mass-convert) + DB-backed async tests. `program` slice has no test file, and `features/excuse/` has only `test_notifications.py` (the full excuse-service cover is still unwritten).
- `conftest.py` SQLite shims (SQLite-only, inert on Postgres): `JSONB`→`JSON`, `BigInteger`→`INTEGER` (else every `id` insert fails `NOT NULL`), aware-UTC `DateTime` (else `SessionService.create_session` raises `TypeError`), plus `PRAGMA foreign_keys=ON` (else RESTRICT guards pass vacuously).
- DB tests must use `api_client` (httpx + ASGITransport, `_get_db` overridden). `test_client` is sync-only and never used as a context manager (entering it runs lifespan `SELECT 1` → needs live Postgres).
- `api_client` commits only on success, so a **failing request rolls back the seed** — commit after seeding if a test issues two failing requests. Read `server_default` values before committing (else `MissingGreenlet`).
- Autouse fixture clears five process-global caches: `attendance.service._IDEMPOTENCY_STORE`, `rate_limit._limiter._windows`, `auth.service._recovery_limiter._windows`, `shared.cache._cache._store`, `shared.email._PENDING`. Add any new module-level cache here.

## Frontend

- Runes mode forced in `vite.config.ts` (function form, `node_modules` exempt) — write `$state`/`$props`, not legacy reactives. `envPrefix: ['VITE_','PUBLIC_']` is what lets `PUBLIC_*` reach the browser. Strict TS; deps are `html5-qrcode`, `zod`, `@mediapipe/tasks-vision` (no `chart.js`).
- `src/lib/api/client.ts`: `MOCK = PUBLIC_MOCK_MODE === 'true'` (real API by default); all URLs prefixed with `/api`; handles three backend error envelopes (AppException dict, FastAPI 422 list, plain-string 401/403) + 401-refresh retry + `postForm`/`getText` for CSV import/template.
- Still hard-coded `MOCK = true` (ignore the global flag): `excuse/service.ts` (backend model-only, no `GET /professor/excuse-requests` yet), `report/service.ts`, `sync/service.ts` (IndexedDB wrapper not built). Professor attendance ledger (`attendance/service.ts`) is real — it joins course/session identity client-side because the contract row carries only `scanned_at`.
- Endpoints are named `EndpointDef`s in `src/lib/api/endpoints.ts` collected into an `endpoints` registry; feature slices live in `src/lib/features/` (`admin` included), shared types/constants/utils under `src/lib/shared/`. Admin routes (`src/routes/admin/...`) are real pages now — don't assume the old 24-page list is complete.

## Docs (only what agents actually need)

- `docs/architecture/api-contracts.md` — endpoint inventory (scan `student_number` field documented but comparison-only, see above).
- `docs/project/decision-log.md` — authoritative (D1–D62, ADR-055–062); check before "fixing" odd-looking contracts.
- `docs/project/roadmap.md` — 13 phases; Phase 12 is a flagged gap.
