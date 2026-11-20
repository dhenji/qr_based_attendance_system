# Backend Setup Guide

> Copy-pasteable commands only. Prerequisites: Docker, Python 3.12+, Node 22+.

---

## Quick Start (Docker — recommended)

```bash
# From project root
cp backend/.env.example backend/.env   # edit values as needed
docker compose -f docker-compose.dev.yml up --build
```

API available at `http://localhost:8000`. Postgres at `:5432`. Migrations run automatically on boot.
Frontend (SvelteKit) available at `http://localhost:5173` — HMR uses polling (`CHOKIDAR_USEPOLLING`) so file changes in `frontend/src` auto-refresh the browser.

Verify:

```bash
curl http://localhost:8000/health
```

---

## Manual Setup (without Docker)

### 1. Database

```bash
# Start Postgres (or use an existing instance)
# Create database
createdb attendance_sys
```

### 2. Backend environment

```bash
cd backend
cp .env.example .env
# Edit .env — at minimum set DATABASE_URL and HMAC_SECRET_KEY
```

### 3. Python environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Apply migrations

```bash
cd backend
alembic upgrade head
```

> **Note:** `alembic upgrade head` applies the baseline migration
> (`679a319c12d6`) **and** the revisions on top of it, ending at head
> `768d6ae62710` (attempt-counter check constraint; 31 revisions). That chain carries the schema to the current **22 tables** — including
> `mfa_backup_codes`, `audit_logs`, `app_settings`, `student_risk_scores_staging`,
> and `offering_components`.
> See [migration-strategy.md](../architecture/migration-strategy.md) for the target schema
> reference and the full revision list.
### 5. Run the server

```bash
cd backend
uvicorn main:app --app-dir src --reload
```

---

## Running Tests

Run the backend tests in an isolated Docker Compose service:

```bash
docker compose -f docker-compose.dev.yml --profile test run --rm --build api-test
```

Run them locally without Docker:

```bash
cd backend
python -m pytest src/tests/ -v
```

The suite holds **1152 cases across 92 files** (338 sync + 771 async test functions, plus parametrized expansions). `src/tests/conftest.py` provides the database and client fixtures, backed by in-memory SQLite by default — no database or Docker is required. `pytest`, `pytest-asyncio`, `aiosqlite`, `pytest-cov`, `httpx` and `ruff` are all in `backend/requirements.txt`; pytest config lives in `backend/pytest.ini` (`asyncio_mode = auto` plus the `slow`/`integration` markers), and Ruff config lives in `backend/pyproject.toml`.

Set `TEST_DATABASE_URL` to run the same suite against a real Postgres instead. Create a dedicated test database first — the Compose Postgres only creates `attendance_sys`, and the suite runs `create_all`/`drop_all` per test, so never point `TEST_DATABASE_URL` at `attendance_sys` itself:

```bash
docker compose -f docker-compose.dev.yml exec db \
  psql -U postgres -c "CREATE DATABASE attendance_test;"

cd backend
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/attendance_test \
  PYTHONPATH=src .venv/bin/python -m pytest src/tests -q
```

### Deselecting slow and integration tests

`pytest.ini` declares two markers, so either group can be skipped:

```bash
cd backend
DEBUG=true JWT_SECRET=test-secret-0123456789abcdef PYTHONPATH=src \
  .venv/bin/python -m pytest src/tests -q -m "not slow"
DEBUG=true JWT_SECRET=test-secret-0123456789abcdef PYTHONPATH=src \
  .venv/bin/python -m pytest src/tests -q -m "not integration"
```

CI runs the whole suite on SQLite; see
[test-plan.md §9](../testing/test-plan.md) for what CI gates versus what stays manual.

## Lint & Format

Ruff is the backend linter and formatter, configured in `backend/pyproject.toml`
and pinned in `backend/requirements.txt` (ADR-094). After
`pip install -r requirements.txt`, run both checks from `backend/`:

```bash
cd backend
ruff check .           # lint; add --fix for the safe auto-fixes
ruff format --check .  # verify formatting (what CI runs)
ruff format .          # format in place
```

`alembic/versions/` is excluded because applied migrations are frozen history
(ADR-065), and `**/constants.py` keeps F401 off because those modules re-export
shared bounds by design. The `lint` CI job installs the exact pin from
`backend/requirements.txt`, so local and CI versions match. Editor defaults live
in `.editorconfig` at the repository root.

---

## Seeding & Load Harness

None of the following are pytest-collected — they are standalone entry points.

### Seed data

Needs a **migrated live Postgres** (`alembic upgrade head` first). `small` is the default
scale: 42 students.

```bash
cd backend
python test_seed_data.py --scale small          # small|medium|large|xl; also --reset, --load-fixtures N
PYTHONPATH=src .venv/bin/python -m tests.seed_data --scale small   # same module, importable entry
```

Per-scale row counts are documented in
[test-data.md](../testing/test-data.md).

### Load harness

Run the API in benchmark mode first so a single host does not trip the per-IP rate gates,
then drive it with locust:

```bash
# terminal 1
cd backend
BENCHMARK_MODE=true FACE_MATCH_THRESHOLD=0.0 .venv/bin/uvicorn main:app --app-dir src
# terminal 2
cd backend
.venv/bin/locust -f locustfile.py --host http://127.0.0.1:8000 --headless -u 30 -r 6 --run-time 5m --csv load_run
```

The load run asserts its own throughput and latency targets and sets a non-zero exit code on
a miss, so it is CI-gateable. **Never import `locustfile` from the test suite** — importing
locust monkey-patches with gevent and hangs pytest. Measured results live in
[performance-benchmarks.md §7](../testing/performance-benchmarks.md).

### Batch timings

```bash
cd backend
.venv/bin/python bench_timings.py --batch --workers 4   # nightly risk-batch timing
BACKUP_ENCRYPTION_KEY=… .venv/bin/python bench_timings.py --backup   # needs pg_dump + OpenSSL 3
```

---

## Alembic Workflow

### Create a new migration

```bash
cd backend
alembic revision --autogenerate -m "description of change"
```

### Apply pending migrations

```bash
cd backend
alembic upgrade head
```

### Roll back one step

```bash
cd backend
alembic downgrade -1
```

### Check current revision

```bash
cd backend
alembic current
```

### Check for model/migration drift

```bash
cd backend
alembic check
```

> **Important — this is the only guard against migration drift.** `conftest.py` builds the test
> schema with `Base.metadata.create_all`, straight from the models, so the suite never
> exercises the revision chain and cannot detect drift in **either** direction (ADR-065). CI
> runs `alembic upgrade head && alembic check` against a `postgres:16-alpine` service on every
> push and pull request. **Red means drift, not a flaky check.**
>
> When an applied migration disagrees with a model, **fix the migration, never the model**:
> never edit an already-applied revision, add a forward migration.

### View migration history

```bash
cd backend
alembic history --verbose
```

**Important:** Always run alembic from `backend/` so `features.*` imports resolve correctly. Every new feature model MUST be imported in `backend/alembic/env.py` alongside the existing imports.

---

## Environment Variables

Copy `backend/.env.example` to `backend/.env` and fill in:

| Variable                      | Required               | Default                                                                | Notes                     |
| ----------------------------- | ---------------------- | ---------------------------------------------------------------------- | ------------------------- |
| `DATABASE_URL`                | Yes                    | `postgresql+asyncpg://postgres:postgres@localhost:5432/attendance_sys` | Async PostgreSQL URL      |
| `DEBUG`                       | No                     | `True`                                                                 | Set `False` in production |
| `CORS_ORIGINS`                | No                     | `http://localhost:5173`                                                | Comma-separated origins   |
| `HMAC_SECRET_KEY`             | Yes                    | —                                                                      | For session code signing  |
| `JWT_SECRET`                  | Yes (when DEBUG=false) | —                                                                      | `openssl rand -base64 32` |
| `JWT_ALGORITHM`               | No                     | `HS256`                                                                |                           |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No                     | `15`                                                                   |                           |
| `REFRESH_TOKEN_EXPIRE_DAYS`   | No                     | `7`                                                                    |                           |

See `backend/.env.example` and [§1 of the production checklist](../deployment/production-checklist.md) for the full list of additional env vars (face, risk, backup, attachments).
