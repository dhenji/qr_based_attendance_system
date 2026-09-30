# Backend Setup Guide

> Copy-pasteable commands only. Prerequisites: Docker, Python 3.12+, Node 20+.

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

> **Note:** `alembic upgrade head` applies the 16-table baseline migration
> (`679a319c12d6`). Further model changes (e.g. locking, audit, settings tables)
> are added via new revisions on top. See [migration-strategy.md](../architecture/migration-strategy.md)
> for the target schema reference.

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

The suite holds 239 cases across 19 files. `src/tests/conftest.py` provides the database and client fixtures, backed by in-memory SQLite by default — no database or Docker is required. `pytest`, `pytest-asyncio`, `aiosqlite`, `pytest-cov` and `httpx` are all in `backend/requirements.txt`; config lives in `backend/pytest.ini` (`asyncio_mode = auto` plus the `slow`/`integration` markers).

Set `TEST_DATABASE_URL` to run the same suite against a real Postgres instead.

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
