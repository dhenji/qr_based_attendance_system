# AGENTS.md — QR-Based Attendance System

Proposal/documentation repo with a **FastAPI backend** (feature models + initial Alembic migration) and a **minimal SvelteKit app shell**. Feature `service`/`schema`/`router` layers are still empty.

## Repository State

- Remote: `git@github.com:CodeKharl/qr_based_attendance_system.git`. Recent commits are merged PRs (#11–#19) — work flows through branches/PRs against `main`.
- Layout: `frontend/` (app shell), `backend/` (models + migrations + `Dockerfile.dev`), root `docker-compose.yml` (local dev), `docs/`.
- Root `.gitignore` exists: ignores `.env`/`.env.*` but **un-ignores** `.env.example` and `.env.test`. A real `backend/.env` exists (ignored); never commit one.
- No linters, formatters, backend tests, or CI. Only automated check: `npm run check` in `frontend/`. `README.md` is current and accurate.

## Docs

Docs live in `docs/{proposals,architecture,deployment,design,presentations}/`. Key files: `docs/proposals/proposal.md` (full 11-section), `docs/proposals/proposal_simple.md` (1-page), `docs/proposals/models.md` (model catalog), `docs/proposals/contributions.md` (CS contributions), `docs/design/database-er.md` (ERD), `docs/deployment/deployment-workflow.md` (free-tier: Supabase → Fly.io → Vercel), `docs/design/wireframes.md` (992-line consolidated wireframes), `docs/presentations/presentation-slides.md` + `presentation.pptx`.

## Frontend (`frontend/`)

- SvelteKit 2 + Svelte 5, `@sveltejs/adapter-auto`, TypeScript strict. Deps: `html5-qrcode`, `zod`.
- **Runes mode is forced on** via `vite.config.ts` compilerOptions — write `$state`/`$props` runes, not legacy reactive declarations.
- Minimal shell only: `src/routes/+page.svelte`, `src/routes/+layout.svelte`, `app.html`, `src/lib/` (favicon, index.ts). No API routes or real pages yet.
- `.npmrc` sets `engine-strict=true` — `npm install` fails if Node doesn't satisfy dep engine ranges (package.json itself declares no `engines`).
- Run from `frontend/`: `npm run dev` (port 5173), `npm run check` (runs `svelte-kit sync` first; generates gitignored `.svelte-kit/`), `npm run build`, `npm run preview`.
- Env: copy `.env.example` to `.env`; only `PUBLIC_*` vars reach the browser (`PUBLIC_API_URL=http://localhost:8000`).
- PWA (`vite-plugin-pwa`) planned but **not installed**; `vite.config.ts` comments mark it as an optional later upgrade.

## Backend (`backend/`)

- FastAPI app in `main.py` (instance `app`, `/health`, CORS). Run from `backend/`: `uvicorn main:app --reload`.
- Wired: `requirements.txt`, `core/config.py` (pydantic-settings, reads `.env`), `core/database.py` (`Base(DeclarativeBase)` + async engine + `get_session`), `api/deps.py` (`get_db`).
- `Dockerfile.dev` is **multi-stage**: `builder` (venv at `/opt/venv` + pip install) → `runtime` (API) → `migrate` (`alembic upgrade head`). `docker-compose.yml` builds the `migrate` service with `target: migrate`.
- **Models & Alembic**: all 7 feature models subclass `core.database.Base` — `auth.User`, `student.Student`, `course.Course`, `enrollment.Enrollment`, `session.Session`, `attendance.Attendance`, `sync.SyncQueue`. `alembic/env.py` imports every feature model, so `target_metadata` is populated; `alembic/versions/68a78206e082_initial_schema.py` creates the full schema. To add a table: write a model, make sure it's imported in `alembic/env.py`, then `alembic revision --autogenerate -m "..."` + `alembic upgrade head`.
- Gotcha: FastAPI `lifespan` runs `SELECT 1` against Postgres at startup — the app **fails to boot if no database is reachable**.
- Missing so far: `service.py`, `schema.py`, `router.py` per feature slice; `backend/shared/dependencies.py`/`cache.py`/`base.py`; everything in `backend/tests/`. Existing shared helpers: `shared/enums.py` (`UserRole`, `ValidationStatus`, `SyncStatus`, `QueueStatus`), `shared/mixins.py` (`CreatedAtMixin`, `TimestampMixin`).

## Local dev (running)

- Recommended (from repo root): `docker compose up --build` → API on :8000, Postgres on :5432 (`attendance_sys`, postgres/postgres), bind-mounts `./backend` into the container. The compose `migrate` service (build target `migrate`) runs `alembic upgrade head` before the API boots, so the schema is applied automatically. No need to run `uvicorn` manually.
- Manual: copy `backend/.env.example` to `.env` (defaults already target `localhost:5432`), run `alembic upgrade head` from `backend/`, then `uvicorn main:app --reload`.