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

| # | Layer              | What It Prevents                     | CS Concept                   |
| - | ------------------ | ------------------------------------ | ---------------------------- |
| 1 | HMAC Session Code  | Outsiders submitting attendance      | HMAC-SHA256                  |
| 2 | GPS Geofencing     | Remote/fake submissions              | Haversine Algorithm          |
| 3 | Live QR Detection  | Screenshot of a classmate's ID       | Reflection/Liveness Analysis |
| 4 | One Scan Per Session | Same ID used multiple times        | Database Constraint          |
| 5 | Enrollment Check   | Non-enrolled students marking attendance | Relational FK Constraint |

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

| Component | Technology                                        |
| --------- | ------------------------------------------------- |
| Backend   | Python (FastAPI, SQLAlchemy async, Alembic)       |
| Frontend  | SvelteKit 5 + TypeScript (strict)                 |
| Database  | PostgreSQL 16                                     |
| Platform  | Progressive Web App (works on any device; planned) |
| Tooling   | Docker / docker-compose, html5-qrcode, zod        |

## Repository Layout

```
├── frontend/   # SvelteKit app (scaffold only — no source files yet)
├── backend/    # FastAPI app (working skeleton) + Dockerfile.dev
├── docker-compose.yml  # Local dev: PostgreSQL + API
└── docs/       # Proposal, architecture, deployment, design, presentations
```

## Getting Started

### Option A — Docker (recommended)

```bash
docker compose up --build
```

This starts both services:

- **API**: http://localhost:8000 — health check at `/health`
- **Database**: PostgreSQL on `localhost:5432` (`attendance_sys`)

### Option B — Manual backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit values
uvicorn main:app --reload
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

| Variable         | Default                                                        | Purpose                          |
| ---------------- | -------------------------------------------------------------- | -------------------------------- |
| `APP_NAME`       | `QR Attendance System API`                                     | API name                         |
| `DEBUG`          | `true`                                                         | Enables SQL echo                 |
| `DATABASE_URL`   | `postgresql+asyncpg://postgres:postgres@localhost:5432/attendance_sys` | Async PostgreSQL connection |
| `CORS_ORIGINS`   | `http://localhost:5173`                                        | Allowed browser origins          |
| `HMAC_SECRET_KEY`| *(empty)*                                                      | Used for secure session codes    |

Frontend (`frontend/.env.example`):

| Variable          | Default                 | Purpose                            |
| ----------------- | ----------------------- | ---------------------------------- |
| `PUBLIC_API_URL`  | `http://localhost:8000` | Backend base URL exposed to browser |

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
- [`docs/architecture/project-structure.md`](docs/architecture/project-structure.md) — intended backend layout
- [`docs/design/frontend-architecture.md`](docs/design/frontend-architecture.md) — production-ready frontend structure
- [`docs/design/wireframes.md`](docs/design/wireframes.md) — screen wireframes
- [`docs/presentations/presentation-slides.md`](docs/presentations/presentation-slides.md) — slide content

## Project Status

| Area     | Status                                         |
| -------- | ---------------------------------------------- |
| Backend  | Working skeleton — FastAPI with `/health`, async SQLAlchemy session, config |
| Frontend | Scaffold only — deps installed, no `src/routes/` yet |
| Features | In progress — feature-sliced backend modules exist but are empty |
| Tests    | None                                           |

## Team

| Name | Role |
| ---- | ---- |
| [Name] | [Role] |