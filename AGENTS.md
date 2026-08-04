# AGENTS.md — attendance_sys_proposal

Proposal/documentation repo with a SvelteKit frontend scaffold at the repo root. Backend (FastAPI + PostgreSQL) is planned but empty.

## Repository State

- Remote: `git@github.com:CodeKharl/attendance_sys_proposal.git`
- Branch `refactor/revoke-src` has **uncommitted** changes: `src/frontend/` was deleted in favor of root-level `frontend/` (byte-identical content — pure relocation), and an empty `backend/` was created. `git status` shows the deletions; treat `frontend/` as the real layout and don't restore `src/frontend/`.
- No tests, linters, formatters, CI, or Dockerfile exist. The only verification is `npm run check` in `frontend/`.
- `.env` files are gitignored everywhere; only `frontend/.env.example` exists.

## Docs Layout

Docs live in `docs/proposals/`, `docs/architecture/`, `docs/deployment/`, `docs/design/`, `docs/presentations/`:

| File | Purpose |
|------|---------|
| `docs/proposals/proposal.md` | Full 11-section proposal (CS concepts, data flow, schema) |
| `docs/proposals/proposal_simple.md` | Condensed 1-page version for early submission |
| `docs/design/frontend-architecture.md` | Production-ready SvelteKit structure: route groups `(auth)`, `(student)`, `(professor)`, `(admin)`, Zod validators, scanner module. Clean copy — prefer editing this one |
| `docs/architecture/frontend-architecture.md` | Same content but still contains leftover `<<<<<<< HEAD` conflict markers; only edit if you clean them. `docs/architecture/project-structure.md`'s frontend section is simpler/outdated |
| `docs/deployment/deployment-workflow.md` | Free-tier deploy guide: Supabase (DB) → Fly.io (API) → Vercel (frontend) |
| `docs/presentations/presentation-slides.md`, `presentation.pptx` | Slide content (mermaid diagrams) + deck |

Duplicates — don't edit both copies:
- `docs/wireframes.md` ≡ `docs/design/wireframes.md` (identical)
- `docs/design/system-mockup.pdf` ≈ `docs/presentations/system-mockup.pdf` (near-duplicates)

## Frontend (`frontend/`)

- SvelteKit 2 + Svelte 5, `@sveltejs/adapter-auto`, TypeScript strict. Deps: `html5-qrcode`, `zod`.
- **No source files yet** (no `src/routes/`, no `app.html`) — scaffold only. All commands run from `frontend/`: `npm run dev`, `npm run check`, `npm run check:watch`, `npm run build`, `npm run preview`. `check` runs `svelte-kit sync` first and generates gitignored `.svelte-kit/`.
- Env: copy `frontend/.env.example` to `.env`; only `PUBLIC_*` vars reach the browser (`PUBLIC_API_URL=http://localhost:8000` for the not-yet-built backend).
- PWA (`vite-plugin-pwa`) is planned but **not installed**; `vite.config.ts` comments mark it as an optional later upgrade.

## Backend (`backend/`)

- Empty directory. Per `docs/deployment/deployment-workflow.md`: FastAPI, `uvicorn --reload` dev, Alembic migrations, Fly.io Docker deploy (`fly deploy`).