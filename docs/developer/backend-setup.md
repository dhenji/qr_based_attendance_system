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

> **Note:** `alembic upgrade head` creates the full target schema (16 tables with correct
> columns, constraints, and FKs). See [migration-strategy.md](../architecture/migration-strategy.md)
> for the target schema reference.

### 5. Run the server

```bash
cd backend
uvicorn main:app --app-dir src --reload
```

---

## Running Tests

```bash
cd backend
python -m pytest src/tests/ -v
```

Test directory structure:

```
backend/src/tests/
├── __init__.py
├── test_students.py
├── test_attendance.py
├── test_cache.py
└── test_sessions.py
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
