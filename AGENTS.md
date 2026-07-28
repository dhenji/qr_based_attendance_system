# AGENTS.md — attendance_sys_proposal

**This is a proposal/documentation repository.** No implementation code exists yet. The actual project (FastAPI + SvelteKit + PostgreSQL) has not been started.

## Repository State

- 7 commits (initial proposal → sveltekit switch → structure+deployment → presentation → AGENTS.md → frontend-architecture → merge)
- Remote: `git@github.com:CodeKharl/attendance_sys_proposal.git`
- No `.gitignore`, `package.json`, `requirements.txt`, `Dockerfile`, CI workflows, tests, linters, formatters, or typecheckers exist
- No `.env` files are committed
- When implementation begins, use `project-structure.md` as the directory blueprint

## Key Documents

| File | Purpose |
|------|---------|
| `proposal.md` | Full 11-section proposal with CS concepts, data flow, schema |
| `proposal_simple.md` | Condensed 1-page version for early submission |
| `project-structure.md` | Planned directory layout for implementation (frontend section is simpler) |
| `frontend-architecture.md` | Production-ready SvelteKit frontend structure (supersedes `project-structure.md` frontend portion) |
| `deployment-workflow.md` | Free-tier deploy guide: Supabase (DB) → Fly.io (API) → Vercel (frontend) |
| `presentation-slides.md` | Slide content with mermaid diagrams |
| `presentation.pptx` | Slide deck (binary) |

## Tech Stack (Planned)

- **Backend**: Python FastAPI (`uvicorn --reload` dev, Fly.io Docker production)
- **Frontend**: SvelteKit PWA with `vite-plugin-pwa` (switched from React per commit `5fdadc5`)
- **Database**: PostgreSQL (local Docker dev, Supabase cloud production)
- **Deployment**: Fly.io (API, `fly deploy`) → Vercel (frontend, git-push deploy) → Supabase (DB)
- **QR Library**: `html5-qrcode`
- **Migrations**: Alembic (manual local run, auto-migrate on startup, or Fly.io release command)

## Frontend Structure Note

Two docs describe the planned frontend layout. The richer one is `frontend-architecture.md` — it uses route groups `(auth)`, `(student)`, `(professor)`, `(admin)`, adds Zod validators, server-side auth helpers, and separates scanner components into a module. Prefer it over the simpler `project-structure.md` frontend section when implementation starts.

## Development Commands (Planned)

These are the likely commands once implementation begins:
- **Backend (dev)**: `cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload`
- **Frontend (dev)**: `cd frontend && npm install && npm run dev`
- **DB (local)**: `docker-compose up` (PostgreSQL)
- **Backend deploy**: `cd backend && fly deploy`
- **Migrations**: `cd backend && DATABASE_URL="..." alembic upgrade head`
