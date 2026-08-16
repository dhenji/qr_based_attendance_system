# QR-Based Attendance System

A QR-code based, offline-capable attendance system with anti-spoofing. Students scan the QR code already printed on their ID cards using their phone; professors open class sessions with a code; the system records who is present, who is absent, and generates reports.

Built for **Software Engineering 1**. Full proposal: [`docs/proposals/proposal.md`](docs/proposals/proposal.md).

## Problem

- Manual calling of names wastes 5–10 minutes of class time
- Students can fraudulently sign for absent classmates
- Campus internet is not always reliable
- Paper records are easily lost

## Solution

A web application that:

- Scans the QR code on student IDs to identify the student
- Uses a session code (shown by the professor) + GPS location to prevent cheating
- Works without internet by saving attendance locally and uploading later
- Automatically updates student year levels each school year

## Security & Anti-Spoofing

Every attendance submission is validated against **five layers** before it is accepted; any single failure rejects the record.

| #   | Layer                | What It Prevents                         | CS Concept                   |
| --- | -------------------- | ---------------------------------------- | ---------------------------- |
| 1   | HMAC Session Code    | Outsiders submitting attendance          | HMAC-SHA256                  |
| 2   | GPS Geofencing       | Remote/fake submissions                  | Haversine Algorithm          |
| 3   | Live QR Detection    | Screenshot of a classmate's ID           | Reflection/Liveness Analysis |
| 4   | One Scan Per Session | Same ID used multiple times              | Database Constraint          |
| 5   | Enrollment Check     | Non-enrolled students marking attendance | Relational FK Constraint     |

## Features

| Feature          | Purpose                                                       |
| ---------------- | ------------------------------------------------------------- |
| QR Code Scanning | Scan student ID card QR using phone camera                    |
| Session Code     | Professor shares a code; required to submit attendance        |
| GPS Verification | Ensures student is inside the classroom                       |
| Offline Mode     | Saves attendance locally when no internet; auto-uploads later |
| Student Roster   | Import student from CSV file                                  |
| Dashboard        | View attendance in real time                                  |
| Reports          | Download attendance reports                                   |

## Tech Stack

| Component | Technology                                         |
| --------- | -------------------------------------------------- |
| Backend   | Python (FastAPI, SQLAlchemy async, Alembic)        |
| Frontend  | SvelteKit 5 + TypeScript (strict)                  |
| Database  | PostgreSQL 16                                      |
| Platform  | Progressive Web App (works on any device; planned) |
| Tooling   | Docker / docker-compose, html5-qrcode, zod         |

## Repository Layout

```
├── .gitignore            # Root-level ignores (env/venv, node, docker data, build output)
├── frontend/             # SvelteKit app (minimal app shell + routes)
├── backend/              # FastAPI app — vertical feature slices + Alembic
│   ├── src/
│   │   ├── main.py       # App entry point (/health, CORS, DB lifespan check)
│   │   ├── core/         # config.py (pydantic-settings), database.py (async engine + Base)
│   │   ├── shared/       # Cross-feature enums + mixins
│   │   ├── features/     # auth, student, course, enrollment, session, attendance, sync
│   │   │   └── */model.py # SQLAlchemy models per feature
│   │   ├── api/          # get_db dependency
│   │   └── tests/        # Empty scaffold — no backend tests yet
│   ├── alembic/          # Migrations (initial schema: 68a78206e082)
│   └── Dockerfile.dev    # Multi-stage: builder → runtime → migrate
├── docker-compose.yml    # Local dev: PostgreSQL + migrations + API
└── docs/                 # Proposal, architecture, deployment, design, presentations
```

## Getting Started

### Option A — Docker (recommended)

```bash
docker compose up --build
```

This starts three services:

- **Database**: PostgreSQL on `localhost:5432` (`attendance_sys`)
- **Migrations**: builds the `migrate` target of `backend/Dockerfile.dev` and runs `alembic upgrade head` once, applying the schema before the API boots
- **API**: builds the `runtime` target of `backend/Dockerfile.dev` — http://localhost:8000, health check at `/health`

The backend image is multi-stage: a `builder` stage creates a virtualenv at `/opt/venv` and installs dependencies, a `runtime` stage copies it in for the API, and a `migrate` stage reuses the runtime image with `alembic upgrade head` as its command.

### Option B — Manual backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit values
alembic upgrade head   # apply schema migrations
uvicorn main:app --reload --app-dir src
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env   # only PUBLIC_* vars reach the browser
npm run dev            # http://localhost:5173
```

## Environment Variables

Backend (`backend/.env.example`):

| Variable          | Default                                                                | Purpose                       |
| ----------------- | ---------------------------------------------------------------------- | ----------------------------- |
| `APP_NAME`        | `QR Attendance System API`                                             | API name                      |
| `DEBUG`           | `true`                                                                 | Enables SQL echo              |
| `DATABASE_URL`    | `postgresql+asyncpg://postgres:postgres@localhost:5432/attendance_sys` | Async PostgreSQL connection   |
| `CORS_ORIGINS`    | `http://localhost:5173`                                                | Allowed browser origins       |
| `HMAC_SECRET_KEY` | _(empty)_                                                              | Used for secure session codes |

Frontend (`frontend/.env.example`):

| Variable         | Default                 | Purpose                             |
| ---------------- | ----------------------- | ----------------------------------- |
| `PUBLIC_API_URL` | `http://localhost:8000` | Backend base URL exposed to browser |

## Verification

The only automated check today runs in the frontend:

```bash
cd frontend && npm run check
```

There are no linters, formatters, or backend tests yet.

## Deployment

See [`docs/deployment/deployment-workflow.md`](docs/deployment/deployment-workflow.md) for the free-tier guide: **Supabase** (DB) → **Fly.io** (API) → **Vercel** (frontend).

## Documentation

- [`docs/proposals/proposal.md`](docs/proposals/proposal.md) — full 11-section proposal
- [`docs/proposals/proposal_simple.md`](docs/proposals/proposal_simple.md) — 1-page summary
- [`docs/proposals/models.md`](docs/proposals/models.md) — catalog of models used in anti-spoofing/analytics
- [`docs/proposals/contributions.md`](docs/proposals/contributions.md) — honest CS contributions (offline liveness protocol)
- [`docs/architecture/project-structure.md`](docs/architecture/project-structure.md) — intended backend layout
- [`docs/architecture/frontend-architecture.md`](docs/architecture/frontend-architecture.md) — production-ready frontend structure
- [`docs/design/database-er.md`](docs/design/database-er.md) — entity-relationship diagram
- [`docs/design/wireframes.md`](docs/design/wireframes.md) — screen wireframes
- [`docs/design/system-mockup.pdf`](docs/design/system-mockup.pdf) — system mockup
- [`docs/presentations/presentation-slides.md`](docs/presentations/presentation-slides.md) — slide content
- [`docs/presentations/presentation.pptx`](docs/presentations/presentation.pptx) — slide deck

## Project Status

| Area     | Status                                                                                                                                                  |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Backend  | FastAPI with `/health`, async SQLAlchemy, `core`/`shared` infrastructure, all 7 feature models, initial Alembic migration, multi-stage `Dockerfile.dev` |
| Frontend | Minimal app shell — `src/routes/`, `src/lib/`, `app.html` present; `html5-qrcode` + `zod` deps                                                          |
| Features | Models implemented; `service` / `schema` / `router` layers pending                                                                                      |
| Tests    | Frontend `npm run check` only; backend `tests/` is an empty scaffold                                                                                    |
