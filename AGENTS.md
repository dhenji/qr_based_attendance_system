# AGENTS.md — attendance_sys_proposal

**This is a proposal/documentation repository.** No implementation code exists yet. The actual project (FastAPI + SvelteKit + PostgreSQL) has not been started.

## Key Documents

| File | Purpose |
|------|---------|
| `proposal.md` | Full proposal — 11 sections, CS concepts, data flow, schema |
| `proposal_simple.md` | Condensed 1-page version for early submission |
| `project-structure.md` | Planned directory layout for implementation |
| `deployment-workflow.md` | Free-tier deploy guide: Supabase (DB) → Fly.io (API) → Vercel (frontend) |
| `presentation-slides.md` | Slide content with mermaid diagrams |
| `presentation.pptx` | Slide deck (binary) |

## Tech Stack (Planned)

- **Backend**: Python FastAPI
- **Frontend**: SvelteKit PWA (switched from React per commit `5fdadc5`)
- **Database**: PostgreSQL (local Docker / Supabase production)
- **Deployment**: Fly.io (API) → Vercel (frontend) → Supabase (DB)
- **QR Library**: `html5-qrcode`
- **PWA Plugin**: `vite-plugin-pwa`

## Git Context

- 4 commits: initial proposal → sveltekit switch → structure+deployment → presentation
- Remote: `git@github.com:CodeKharl/attendance_sys_proposal.git`

## No Existing Infrastructure

- No `package.json`, `requirements.txt`, `Dockerfile`, or CI workflows
- No tests, linters, formatters, or typecheckers configured
- No `.env` files committed
- When implementation begins, start by creating the planned structure in `project-structure.md`
