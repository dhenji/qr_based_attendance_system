# AGENTS.md — QR-Based Attendance System

FastAPI backend (18 feature slices, 20 models, 10 Alembic migrations) + SvelteKit 2 / Svelte 5 frontend. Real API by default, mock opt-in via `PUBLIC_MOCK_MODE`. No linters or formatters; CI runs the backend suite, `alembic check`, and the frontend typecheck (ADR-069). `README.md` is current; when docs conflict, trust `README.md` + executable config.

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

Seed, load and batch timings — none of these are pytest-collected. The seed needs a migrated live Postgres (`alembic upgrade head`); the load harness needs the API in the load profile so a single load host does not trip the per-IP gates:
```bash
cd backend
python test_seed_data.py --scale small      # small|medium|large|xl; also --reset, --load-fixtures N
PYTHONPATH=src .venv/bin/python -m tests.seed_data --scale small   # same module, importable entry
BENCHMARK_MODE=true FACE_MATCH_THRESHOLD=0.0 .venv/bin/uvicorn main:app --app-dir src   # terminal 1
.venv/bin/locust -f locustfile.py --host http://127.0.0.1:8000 --headless -u 30 -r 6 --run-time 5m --csv load_run   # terminal 2
.venv/bin/python bench_timings.py --batch --workers 4   # nightly risk-batch timing, prints duration_ms
BACKUP_ENCRYPTION_KEY=… .venv/bin/python bench_timings.py --backup   # needs pg_dump + OpenSSL 3 with AEAD
```
`locustfile.py` and `bench_timings.py` are the harness; `src/tests/seed_data.py` is the seed implementation and `test_seed_data.py` a thin root entry point (kept because the docs and runbooks cite that path). Measured results live in `docs/testing/performance-benchmarks.md` §7.

Frontend (`engine-strict=true` in `.npmrc` — install fails on wrong Node):
```bash
cd frontend
npm install
cp .env.example .env   # only PUBLIC_* reaches the browser
npm run dev            # :5173
npm run check          # typecheck (runs svelte-kit sync first)
```

## Backend

- Entry `src/main.py`: `/health`, CORS, lifespan `SELECT 1` on boot — **fails to boot if DB unreachable**. The lifespan also starts/stops the cron scheduler. Only `AppException` has a handler; `DomainException` → 422, `DatabaseException` → 409.
- Config `src/core/config.py`: pydantic-settings, `get_settings()` cached. `JWT_SECRET` required when `DEBUG=false`. `RECOVERY_TOKEN_EXPIRE_MINUTES` defaults to 5 in code but is missing from `backend/.env.example`.
- Scheduler: `src/core/scheduler.py` owns the APScheduler lifecycle (`get_scheduler()`, `BackgroundScheduler`) and imports nothing from `features`/`shared`. Job bodies are adapters in their own feature — `analytics/batch.py::run_scheduled_risk_batch`, `system/service.py::run_scheduled_backup` — and each **commits its own transaction**, because the services only `flush()` and `_get_db` is request-only. Crons: `RISK_BATCH_CRON` (02:00), `BACKUP_CRON` (03:00), both overridable via `SCHEDULER_ENABLED`/`_TIMEZONE`/`_MISFIRE_GRACE_SECONDS`. See ADR-063.
- Deps `src/api/deps.py`: use `_get_db` (no public `get_db`), `_get_current_user` / `_get_optional_current_user`, `require_role(*roles)` (`super_admin` passes `admin` checks), `*ServiceDep` annotated service deps. `_get_db` commits on success, rolls back on any exception.
- Routers: `src/api/router.py` mounts under `/api` with **no `prefix=` arg — each `APIRouter` bakes its own prefix in**. One router per (feature, mount point); never mount the same router twice. `enrollment/router.py` is a stub and stays **unmounted**. Currently **23 routers over 16 mount paths** (24 `*router*.py` files exist; the unmounted one is `enrollment`).
  - `/api/professor` is shared by **five** routers: `session/router.py` owns courses/sessions/attendance; `professor/router.py` owns `profile*` only; `excuse/professor_router.py`, `reports/router.py`, `dashboard/professor_router.py` own their own subtrees. Don't cross them.
  - `/api/student` is shared by **four** routers: `student/router.py` (verify-code, face-embedding, schedule, profile), `attendance/router.py` (scan, precheck, history), `excuse/student_router.py`, `dashboard/student_router.py`. Inner paths must not collide.
  - `/api/admin` is shared by `system/router.py` (audit-logs, system settings, academic-structure) and `dashboard/admin_router.py`.
  - `course/` has two routers (`router.py` → `/admin/courses`, `offering_router.py` → `/admin/offerings`); `student/` and `professor/` each add an `admin_router.py` for their roster CRUD.
  - Collection routes use `@router.get("")`, not `"/"` (trailing-slash redirect breaks the contract).
- Services: admin CRUD slices (`program`, `course`, `student`, `professor`) are `class <Feature>Service` with one `BaseCRUD` per model via `<Feature>ServiceDep` (ADR-058). `SessionService` and `FaceEnrollmentService` are also classes. Everything else stays module-level functions (ADR-055).
- Alembic: head is `1e1582c4e9f8` (10 revisions). New model → add `import features.X.model` to `alembic/env.py`, `alembic revision --autogenerate`, `alembic upgrade head`. `alembic check` must say "No new upgrade operations detected".
- **`alembic check` is the only guard against migration drift, and CI runs it** (`.github/workflows/ci.yml`, job `migrations`, against a `postgres:16-alpine` service — ADR-069). `conftest.py` builds the test schema with `Base.metadata.create_all`, straight from the models, so the suite never exercises the migration chain and cannot detect drift in either direction — a test asserting a unique column passes against both schemas. When an applied migration disagrees with a model, **fix the migration, never the model** (ADR-065): never edit an already-applied revision, add a forward migration. A failing `migrations` job means drift, not a flaky check.
- Models (20 classes, 13 files; `admin`, `dashboard`, `face_enrollment`, `reports`, `upload` model-less): `Student.user_id` / `Professor.user_id` are unique FKs to `users.id` (1:1). Deletes use `ondelete=RESTRICT` — archive routes need a has-records guard (409); never relax to CASCADE. `DELETE /admin/programs/{id}` flips `programs.is_active` only; there is nothing to cascade to (no `is_active` on year levels, no program FK on courses).
- Auth quirks: forgot-password step 2 returns a 5-min `type="recovery"` grant required to mint the OTP; unknown emails get a deterministic decoy question (ADR-056). `users.security_question_hash` stores the question in plaintext under a legacy name — only the answer is hashed; don't "fix" without revisiting the contract.
- Dashboard slice (`features/dashboard/`): three routers, three mount points, so `api/router.py` includes it **three times** — `dashboard_student_router` (`/student/dashboard`), `dashboard_professor_router` (`/professor/dashboard`), `dashboard_admin_router` (`/admin/dashboard`). One router per (feature, mount point); never add a fourth. It aggregates features it doesn't own, so every figure is **composed from an existing service method** rather than recomputed — `compliance_rate` is `get_history().summary.compliance_rate`, admin `avg_rate` is `AnalyticsService.get_overview().avg_compliance_rate` (compliance, NOT participation), and `pending_sync` calls `SystemService.pending_sync_total` **directly** because `get_system_settings()` INSERTs missing `AppSetting` rows — a GET must not write. Roster counts (`student_count`/`professor_count`/`program_count`) count active `is_active` rows and are deliberately *not* the analytics overview's `total_students` (which counts enrolled-in-scope). "Today" means **UTC** throughout. `schedule_days` letters are interpreted by `student/service.py::_meets_on` — `T`=Tuesday, `H`=Thursday, `U`=Sunday — test it as a pure function; `Session.created_at` is the column session queries filter on, not `scheduled_start_time`.
- Password resets: `AuthService.admin_reset_password` is the **single** implementation behind all three admin routes (`/admin/{users,students,professors}/{id}/reset-password`). The student/professor routers resolve the roster row to a `users.id` first (`StudentService.account_user_id` / `ProfessorService.account_user_id`, 409 `*_account_unlinked` when there is none) and then call it — so a credential write has one home, not three. An admin reset also clears `failed_login_attempts`/`is_locked`/`locked_at` (an admin rescuing a locked-out account needs it) and sets `performed_by` to the admin while `entity_id` stays the account. It must **not** touch MFA — that is `disable_mfa`'s job, password-verified. Two service deps on one route is the `reports/router.py:47` pattern.
- MFA is a two-writer field: `verify_mfa` is the only place that sets `mfa_enabled = True` (setup alone writes the secret and leaves the flag False), and `disable_mfa` (`POST /auth/mfa/disable`) is the only path back to False. Any new MFA write site must invalidate unconsumed backup codes the same way — `disable_mfa` stamps `used_at` rather than deleting, which is what makes `list_backup_codes` report 0. Disabling cannot revoke issued refresh tokens (stateless JWTs, no revocation list); that limitation is written up in `security-model.md` T6 / Password & Account Security.
- Email: `shared/email.py` is the one delivery path — real `smtplib`, stdlib only, and it **never raises** (`debug` logs, empty `SMTP_HOST` logs+skips, otherwise implicit TLS 465 / STARTTLS 587). `SMTP_*` in `core/config.py` is deliberately unvalidated (unlike `JWT_SECRET`) so a deployment without a relay still boots. `send_otp_email` keeps its old signature because `auth/service.py` calls it inline; new code that must not block uses `dispatch_emails` (one executor job per batch, futures parked in `shared.email._PENDING`). Excuse notifications: copy in `features/excuse/notifications.py` (pure builders), recipient resolution + dispatch in `ExcuseService`, always last in the method so a raise sends nothing. Recipients read `users.email` first, then the profile's roster `email`. Only §8's four events notify — `quick_excuse`/`excuse_with_evidence`/`edit_excuse`/`revoke_excuse` are silent, and the in-app half is unimplemented (no table, by design).
- Audit: `shared/audit.py::record_audit` is the ONE writer — flush-only, so a row rolls back with the mutation it describes. `action`/`entity_type` are typed by `shared/enums.py::AuditAction`/`AuditEntity` (free-form columns, no DB constraint, **no index on `action`**). Read via `GET /admin/audit-logs` (all rows, 4 filters); `GET /admin/system/academic-structure` reads the same table scoped to the 4 structural entity types. Both live in `system/router.py` (prefix `/admin`); `AuditFilterInvalidException`/`AuditDateRangeInvalidException` are 422. One exception to "services only flush": lockout bookkeeping in `auth/service.py` commits on its own session (`_lockout_transaction`) because the request that raises 400 would otherwise roll the counter back — see ADR-064.
- Scan flow (D27, rejection reasons D15): `POST /student/attendance/{scan,precheck}` resolve the student from the **authenticated user**, only *comparing* `payload.student_number` case-insensitively → `403 student_number_mismatch`. Same rule applies to any new student-facing endpoint taking an ID (e.g. excuse submit). Idempotency key is `user_id:session_id:X-Idempotency-Key`, 15-min TTL, process-local (like `rate_limit` — needs a shared store for multi-instance).
- Benchmark profile (Phase 9, see ADR-067): `BENCHMARK_MODE=true` skips the scan geofence + liveness checks (`attendance/service.py`) and the per-IP scan rate gate (`attendance/router.py`); `RISK_BATCH_WORKERS` shards risk scoring across threads order-preservingly (`analytics/batch.py`). Both default off, so production behavior is unchanged; `test_scan_validation.py` and `test_risk_batch.py` cover each.
- Load-harness traps (Phase 9): never import `locustfile` from the suite — importing locust pulls in gevent monkey-patching and hangs pytest, which is why the harness's helpers live in `bench_timings.py` and why `test_locust_discovery.py` asserts on `locustfile.py`'s *source text* rather than calling it; locust calls `wait_time` bound, so the callable must accept the user argument; a virtual user's identity must come from `SlotAssigner`, never `id(user) % pool` (CPython's aligned addresses collapse onto a few residues and the users then rescan each other's sessions).
- Load gate: `locustfile.py::_report` asserts §2's targets (scan rps, p95, p99, 0 duplicates, slowest replay batch) and sets `environment.process_exit_code = 1` on a miss, so a load run is CI-gateable; thresholds are `LOCUST_MIN_RPS` / `LOCUST_MAX_P95_MS` / `LOCUST_MAX_P99_MS` / `LOCUST_MAX_DRAIN_S`, and the gate only ever forces failure (a clean run leaves the exit code to locust's own `exit_code_on-error`). Throughput counts successful scans over the wall-clock window, not `stats.total.total_time` (that is a sum of response times) nor `total_rps` (that is blended across login/profile/scan). `get_current_response_time_percentile` returns `None` when its trailing-10s cache has no samples — coerce it to a pass and a short run gates green.
- Load queue: slots 1-15 scan live, 16-25 backlog 1-3 scans, 26-30 backlog 5-8 (`_profile_for_slot`); a queued scan is a real POST with `scanned_at` now minus `LOCUST_QUEUE_STALE_S` (default 90, must stay above the 60s staleness floor or replays stop writing sync rows). Each user tracks live-scanned vs backlogged sessions in disjoint sets, because the second scan for a (student, session) is a 409 `duplicate_scan` that fails the gate; leftover backlog replays in `on_stop`. Replayed scans count toward `scans_ok` and carry fresh `X-Idempotency-Key` values — a reused key returns the prior result instead of queueing, which would make the drain leg vacuous.

## Backend tests

- 719 collected cases / 49 files (225 sync + 452 async test functions, plus parametrized expansions): sync hand-rolled-fake tests (`asyncio.run()`, unaffected by `asyncio_mode=auto` — don't mass-convert) + DB-backed async tests. `program` is covered by `features/program/test_program_service.py`; `features/excuse/` has all three layers (`test_service.py`, `test_routes_http.py`, `test_notifications.py`).
- Attendance compliance/participation rates are **one** function: `shared/rates.py::attendance_rates`, keyword-only (`present`, `late`, `excused`, `enrolled`), 4-place rounding, `(0.0, 0.0)` for any non-positive denominator. It replaced four copies that had begun to diverge — `session`'s took transposed arguments. Unit-tested in `tests/test_shared_rates.py`; **do not re-add a per-feature `_rates`**, and compliance must count `present` only.
- `conftest.py` SQLite shims (SQLite-only, inert on Postgres): `JSONB`→`JSON`, `BigInteger`→`INTEGER` (else every `id` insert fails `NOT NULL`), aware-UTC `DateTime` (else `SessionService.create_session` raises `TypeError`), plus `PRAGMA foreign_keys=ON` (else RESTRICT guards pass vacuously).
- DB tests must use `api_client` (httpx + ASGITransport, `_get_db` overridden). `test_client` is sync-only and never used as a context manager (entering it runs lifespan `SELECT 1` → needs live Postgres).
- `api_client` commits only on success, so a **failing request rolls back the seed** — commit after seeding if a test issues two failing requests. Read `server_default` values before committing (else `MissingGreenlet`).
- Autouse fixture clears six process-global caches: `attendance.service._IDEMPOTENCY_STORE`, `rate_limit._limiter._windows`, `auth.service._recovery_limiter._windows`, `shared.cache._cache._store`, `shared.email._PENDING`, plus the scheduler (`core.scheduler.reset_scheduler()`, which clears `_IN_FLIGHT` and unbinds the singleton). Add any new module-level cache here.

## Frontend

- Runes mode forced in `vite.config.ts` (function form, `node_modules` exempt) — write `$state`/`$props`, not legacy reactives. `envPrefix: ['VITE_','PUBLIC_']` is what lets `PUBLIC_*` reach the browser. Strict TS; deps are `html5-qrcode`, `zod`, `@mediapipe/tasks-vision` (no `chart.js`).
- `src/lib/api/client.ts`: `MOCK = PUBLIC_MOCK_MODE === 'true'` (real API by default); all URLs prefixed with `/api`; handles three backend error envelopes (AppException dict, FastAPI 422 list, plain-string 401/403) + 401-refresh retry + `postForm`/`getText` for CSV import/template.
- **No service hard-codes `MOCK = true`** — `client.ts:18` is the only reader of `PUBLIC_MOCK_MODE`, and every service branches on `isMockMode()`. Several still hold a local fixture fallback for the mock leg (in `excuse/mock.ts`, `report/mock.ts`, the `sync` in-memory queue, the `MOCK_*` consts in `api/endpoints.ts`) — that is a data fallback, not a pinned flag. Professor attendance ledger (`attendance/service.ts`) is real — it joins course/session identity client-side because the contract row carries only `scanned_at`.
- Endpoints are named `EndpointDef`s in `src/lib/api/endpoints.ts` collected into an `endpoints` registry; feature slices live in `src/lib/features/` (`admin` included, plus `notifications` which has `poll.ts` and no `service.ts`), shared types/constants/utils under `src/lib/shared/`. Admin routes (`src/routes/admin/...`) are real pages now — 45 page routes in total (4 landing / 3 auth / 6 student / 11 professor / 21 admin).

## Docs (only what agents actually need)

- `docs/architecture/api-contracts.md` — endpoint inventory (scan `student_number` field documented but comparison-only, see above).
- `docs/project/decision-log.md` — authoritative (D1–D70, ADR-055–070); check before "fixing" odd-looking contracts.
- `docs/project/roadmap.md` — 13 phases; Phase 12 is **not** a gap (it is marked `[Done]`, as are Phases 0 and 9).
