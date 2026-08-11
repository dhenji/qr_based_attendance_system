# AGENTS.md — attendance_sys_proposal

Proposal/documentation repo with a **working FastAPI backend skeleton** and a **minimal SvelteKit app shell**. All domain code (feature modules, SQLAlchemy models, Alembic migrations of `features/` slices) is still empty.

## Repository State

- Remote: `git@github.com:CodeKharl/attendance_sys_proposal.git`. Work in progress on branch `docs/all-doc-change` — the docs reorg (deletions + README rewrite) is uncommitted and ahead of `main`.
- Layout: `frontend/` (app shell), `backend/` (working skeleton), root `docker-compose.yml` (local dev), `docs/`.
- **No root `.gitignore`** — env/venv ignoring is per-dir (`backend/.gitignore`, `frontend/.gitignore`). A real `.env` exists in `backend/` (ignored); never commit one.
- No linters, formatters, backend tests, or CI. Only automated check: `npm run check` in `frontend/`. `README.md` is current and accurate.

## Docs

Docs live in `docs/{proposals,architecture,deployment,design,presentations}/`. Past duplicate pairs (`docs/wireframes.md`, `docs/design/frontend-architecture.md`) were deleted in the current reorg — only `docs/design/system-mockup.pdf` ≈ `docs/presentations/system-mockup.pdf` remain as near-duplicates.

Key files: `docs/proposals/proposal.md` (full 11-section), `docs/proposals/proposal_simple.md` (1-page), `docs/design/database-er.md` (ERD), `docs/deployment/deployment-workflow.md` (free-tier: Supabase → Fly.io → Vercel), `docs/design/wireframes.md` (992-line consolidated wireframes), `docs/presentations/presentation-slides.md` + `presentation.pptx`.

## Frontend (`frontend/`)

- SvelteKit 2 + Svelte 5, `@sveltejs/adapter-auto`, TypeScript strict. Deps: `html5-qrcode`, `zod`.
- **Runes mode is forced on** via `vite.config.ts` compilerOptions — write `$state`/`$props` runes, not legacy reactive declarations.
- Minimal shell only: `src/routes/+page.svelte`, `src/routes/+layout.svelte`, `app.html`, `src/lib/` (favicon, index.ts). No API routes or real pages yet.
- `.npmrc` sets `engine-strict=true` — `npm install` fails if Node doesn't satisfy dep engine ranges (package.json itself declares no `engines`).
- Run from `frontend/`: `npm run dev` (port 5173), `npm run check` (runs `svelte-kit sync` first; generates gitignored `.svelte-kit/`), `npm run build`, `npm run preview`.
- Env: copy `.env.example` to `.env`; only `PUBLIC_*` vars reach the browser (`PUBLIC_API_URL=http://localhost:8000`).
- PWA (`vite-plugin-pwa`) planned but **not installed**; `vite.config.ts` comments mark it as an optional later upgrade.

## Backend (`backend/`)

- FastAPI app in `main.py` (module `app`, `/health`, CORS). Run from `backend/`: `uvicorn main:app --reload`.
- Wired: `requirements.txt`, `Dockerfile.dev` (runs uvicorn `--reload`), `core/config.py` (pydantic-settings, reads `.env`), `core/database.py` (**empty `Base(DeclarativeBase)` singleton** + async engine + `get_session`), `api/deps.py` (`get_db`).
- **Alembic is wired** (`alembic.ini` + `alembic/env.py`, async, reads `DATABASE_URL` from settings) but `alembic/versions/` is empty and there are **no models yet** — `target_metadata = Base.metadata` is empty, so `alembic revision --autogenerate` produces nothing until models exist. New models must subclass `core.database.Base` and be imported before autogenerate.
- Gotcha: FastAPI `lifespan` runs `SELECT 1` against Postgres at startup — the app **fails to boot if no database is reachable**.
- Empty modules: feature slices `features/{auth,attendance,course,enrollment,session,student,sync}/`, `backend/shared/`, `backend/tests/`.

## Local dev (running)

- Recommended (from repo root): `docker compose up --build` → API on :8000, Postgres on :5432 (`attendance_sys`, postgres/postgres), bind-mounts `./backend` into the container. No need to run `uvicorn` manually.
- Manual: copy `backend/.env.example` to `.env` (defaults already target `localhost:5432`), then `uvicorn main:app --reload` from `backend/`.