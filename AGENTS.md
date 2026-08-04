# AGENTS.md — attendance_sys_proposal

Proposal/documentation repo with a **working FastAPI backend skeleton** and a **SvelteKit frontend scaffold** (no source files yet). Backend feature modules and Alembic migrations are still empty.

## Repository State

- Remote: `git@github.com:CodeKharl/attendance_sys_proposal.git`. Branch `main`, clean tree.
- Layout: `frontend/` (scaffold only), `backend/` (working skeleton), root `docker-compose.yml` (local dev), `docs/`.
- There is **no root `.gitignore`** — env/venv ignoring is per-dir (`backend/.gitignore`, `frontend/.gitignore`). Both `backend/.env.example` and `frontend/.env.example` exist; never commit a real `.env`.
- No linters, formatters, backend tests, or CI. The only automated check is `npm run check` in `frontend/`. (`README.md` is current and accurate.)

## Docs Layout

Docs live in `docs/{proposals,architecture,deployment,design,presentations}/`. Duplicates — never edit one copy only:

- `docs/wireframes.md` ≡ `docs/design/wireframes.md` (identical)
- `docs/design/frontend-architecture.md` ≡ `docs/architecture/frontend-architecture.md` (identical, conflict markers now cleaned)
- `docs/design/system-mockup.pdf` ≈ `docs/presentations/system-mockup.pdf` (near-duplicates)

Other key files: `docs/proposals/proposal.md` (full 11-section), `docs/proposals/proposal_simple.md` (1-page), `docs/deployment/deployment-workflow.md` (free-tier deploy: Supabase → Fly.io → Vercel), `docs/presentations/presentation-slides.md` + `presentation.pptx`.

## Frontend (`frontend/`)

- SvelteKit 2 + Svelte 5, `@sveltejs/adapter-auto`, TypeScript strict. Deps: `html5-qrcode`, `zod`.
- **No source files yet** (no `src/routes/`, no `app.html`) — scaffold only. Run from `frontend/`: `npm run dev` (port 5173), `npm run check`, `npm run check:watch`, `npm run build`, `npm run preview`. `check` runs `svelte-kit sync` first and generates gitignored `.svelte-kit/`.
- Env: copy `.env.example` to `.env`; only `PUBLIC_*` vars reach the browser (`PUBLIC_API_URL=http://localhost:8000`).
- PWA (`vite-plugin-pwa`) planned but **not installed**; `vite.config.ts` comments mark it as an optional later upgrade.

## Backend (`backend/`)

- **Working skeleton, not empty.** FastAPI app is in `main.py` (module `app`, `/health` endpoint, CORS). Run from `backend/`: `uvicorn main:app --reload`.
- Present and wired: `requirements.txt`, `Dockerfile.dev`, `core/config.py` (pydantic-settings, reads `.env`), `core/database.py` (async SQLAlchemy engine + `get_session`), `api/deps.py` (`get_db`).
- Gotcha: FastAPI `lifespan` runs `SELECT 1` against Postgres at startup — the app **fails to boot if no database is reachable**.
- Not yet implemented: feature slices `features/{auth,attendance,course,enrollment,session,student,sync}/` are empty `__init__.py`; `alembic/versions/` exists but there is **no `alembic.ini` or `env.py`** (Alembic not wired up). No backend tests.

## Local dev (running)

- Recommended (from repo root): `docker compose up --build` → API on :8000, Postgres on :5432 (`attendance_sys`, postgres/postgres). `docker-compose.yml` also defines the API, so no need to run `uvicorn` manually.
- Manual: copy `backend/.env.example` to `.env` (defaults already target `localhost:5432`), then `uvicorn main:app --reload` from `backend/`.
