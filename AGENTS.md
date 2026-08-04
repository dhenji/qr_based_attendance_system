# AGENTS.md — attendance_sys_proposal

Proposal/documentation repo with a starting SvelteKit frontend scaffold. Backend (FastAPI + PostgreSQL) is not started yet.

## Repository State

- Remote: `git@github.com:CodeKharl/attendance_sys_proposal.git`
- Branch `chore/src-setup` has **uncommitted** changes: `frontend/` was deleted in favor of `src/frontend/`, and an empty `src/backend/` was created. Do not be confused by the deleted `frontend/` paths in `git status`; `src/frontend/` is the current layout.
- No tests, linters, formatters, CI, or Dockerfile exist. The only verification available is `npm run check` (svelte-check) in `src/frontend`.
- No `.env` files are committed; only `.env.example` exists.

## Docs Layout

Docs were reorganized into `docs/proposals/`, `docs/architecture/`, `docs/deployment/`, `docs/design/`, `docs/presentations/`:

| File | Purpose |
|------|---------|
| `docs/proposals/proposal.md` | Full 11-section proposal (CS concepts, data flow, schema) |
| `docs/proposals/proposal_simple.md` | Condensed 1-page version for early submission |
| `docs/architecture/frontend-architecture.md` | Production-ready SvelteKit structure: route groups `(auth)`, `(student)`, `(professor)`, `(admin)`, Zod validators, scanner module. Prefer this over `docs/architecture/project-structure.md` (its frontend section is simpler/outdated) |
| `docs/deployment/deployment-workflow.md` | Free-tier deploy guide: Supabase (DB) → Fly.io (API) → Vercel (frontend) |
| `docs/presentations/presentation-slides.md`, `presentation.pptx` | Slide content (mermaid diagrams) + deck |
| `docs/wireframes.md`, `docs/design/wireframes.md` | Duplicate wireframes (identical); `docs/design/system-mockup.pdf` vs `docs/presentations/system-mockup.pdf` are also near-duplicates. Don't edit both copies |

Gotcha: `docs/architecture/frontend-architecture.md` contains leftover unmerged conflict markers (`<<<<<<< HEAD` / `>>>>>>>`) — expected, but clean them if you edit that file.

## Frontend (`src/frontend/`)

- SvelteKit 2 + Svelte 5, `@sveltejs/adapter-auto`, TypeScript strict. Deps installed: `html5-qrcode`, `zod`.
- **No source files yet** (no `src/routes/`, no `app.html`) — only config. Commands:
  - Dev: `cd src/frontend && npm run dev`
  - Typecheck: `npm run check` (runs `svelte-kit sync` first; generates `.svelte-kit/` which is gitignored)
  - Build/preview: `npm run build` / `npm run preview`
- Env: copy `.env.example` to `.env`; `PUBLIC_API_URL=http://localhost:8000` (backend). Only `PUBLIC_*` vars reach the browser.
- PWA (`vite-plugin-pwa`) is planned but **not installed**; `vite.config.ts` comments mark it as an optional later upgrade.

## Backend (planned only)

- `src/backend/` is empty. Per `docs/deployment/deployment-workflow.md`: FastAPI, `uvicorn --reload` dev, Alembic migrations, Fly.io Docker deploy (`fly deploy`).
