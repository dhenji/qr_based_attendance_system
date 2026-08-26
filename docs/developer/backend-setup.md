# Backend Setup Guide

> Copy-pasteable commands only. Prerequisites: Docker, Python 3.12+, Node 20+.

---

## Quick Start (Docker — recommended)

```bash
# From project root
cp backend/.env.example backend/.env   # edit values as needed
docker compose up --build
```

API available at `http://localhost:8000`. Postgres at `:5432`. Migrations run automatically on boot.

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

### 5. Seed programs and year levels

```bash
cd backend
PYTHONPATH=src python seed_programs.py
```

This creates the default academic hierarchy (per D3):

| Program | Years | Term Structures |
|---------|-------|-----------------|
| BSCS | 4 | Y1–Y2, Y4: 1st_sem, 2nd_sem; Y3: 1st_sem, 2nd_sem, midyear |
| BSIT | 4 | Y1–Y4: 1st_sem, 2nd_sem |
| BSECE | 5 | Y1–Y5: 1st_sem, 2nd_sem |

### 6. Run the server

```bash
cd backend
uvicorn main:app --app-dir src --reload
```

---

## Seed Script: `backend/seed_programs.py`

Create this file at `backend/seed_programs.py`:

```python
"""Seed default programs and year levels per D3 examples.

Usage:
    cd backend
    python seed_programs.py
"""
import asyncio
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import database
from features.program.model import Program, YearLevel


PROGRAMS = [
    {
        "code": "BSCS",
        "name": "Bachelor of Science in Computer Science",
        "total_years": 4,
        "year_levels": [
            {"year_number": 1, "label": "1st Year", "terms": ["1st_sem", "2nd_sem"]},
            {"year_number": 2, "label": "2nd Year", "terms": ["1st_sem", "2nd_sem"]},
            {"year_number": 3, "label": "3rd Year", "terms": ["1st_sem", "2nd_sem", "midyear"]},
            {"year_number": 4, "label": "4th Year", "terms": ["1st_sem", "2nd_sem"]},
        ],
    },
    {
        "code": "BSIT",
        "name": "Bachelor of Science in Information Technology",
        "total_years": 4,
        "year_levels": [
            {"year_number": 1, "label": "1st Year", "terms": ["1st_sem", "2nd_sem"]},
            {"year_number": 2, "label": "2nd Year", "terms": ["1st_sem", "2nd_sem"]},
            {"year_number": 3, "label": "3rd Year", "terms": ["1st_sem", "2nd_sem"]},
            {"year_number": 4, "label": "4th Year", "terms": ["1st_sem", "2nd_sem"]},
        ],
    },
    {
        "code": "BSECE",
        "name": "Bachelor of Science in Electronics Engineering",
        "total_years": 5,
        "year_levels": [
            {"year_number": 1, "label": "1st Year", "terms": ["1st_sem", "2nd_sem"]},
            {"year_number": 2, "label": "2nd Year", "terms": ["1st_sem", "2nd_sem"]},
            {"year_number": 3, "label": "3rd Year", "terms": ["1st_sem", "2nd_sem"]},
            {"year_number": 4, "label": "4th Year", "terms": ["1st_sem", "2nd_sem"]},
            {"year_number": 5, "label": "5th Year", "terms": ["1st_sem", "2nd_sem"]},
        ],
    },
]


def make_term_structure(terms: list[str]) -> dict:
    """Build the JSONB term_structure payload."""
    labels = {
        "1st_sem": "1st Semester",
        "2nd_sem": "2nd Semester",
        "midyear": "Midyear",
    }
    return {"terms": [{"code": t, "label": labels.get(t, t)} for t in terms]}


async def seed() -> None:
    async with database.get_session() as session:
        for prog_def in PROGRAMS:
            existing = await session.execute(
                select(Program).where(Program.code == prog_def["code"])
            )
            if existing.scalar_one_or_none():
                print(f"  Program {prog_def['code']} already exists — skipping.")
                continue

            program = Program(
                code=prog_def["code"],
                name=prog_def["name"],
                total_years=prog_def["total_years"],
            )
            session.add(program)
            await session.flush()  # get program.id

            for yl_def in prog_def["year_levels"]:
                year_level = YearLevel(
                    program_id=program.id,
                    year_number=yl_def["year_number"],
                    label=yl_def["label"],
                    term_structure=make_term_structure(yl_def["terms"]),
                    sort_order=yl_def["year_number"],
                )
                session.add(year_level)

            await session.commit()
            print(f"  Seeded {prog_def['code']} with {prog_def['total_years']} year levels.")

    print("Done.")


if __name__ == "__main__":
    asyncio.run(seed())
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

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `DATABASE_URL` | Yes | `postgresql+asyncpg://postgres:postgres@localhost:5432/attendance_sys` | Async PostgreSQL URL |
| `DEBUG` | No | `True` | Set `False` in production |
| `CORS_ORIGINS` | No | `http://localhost:5173` | Comma-separated origins |
| `HMAC_SECRET_KEY` | Yes | — | For session code signing |
| `JWT_SECRET` | Yes (when DEBUG=false) | — | `openssl rand -base64 32` |
| `JWT_ALGORITHM` | No | `HS256` | |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `30` | |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | `7` | |

See `DOCS_REFACTOR_PLAN.md` §8 for the full list of additional env vars (face, risk, backup, attachments).
