# 02 — Presentation Layer

## Admin analytics page

- `frontend/src/routes/admin/analytics/+page.svelte` — filter rail
  (program/year/semester/course/session type/date), tabs: overview,
  comparison, trends, at-risk, staging.
- `frontend/src/lib/features/admin/analytics/service.ts` — API calls.
- `frontend/src/lib/features/admin/analytics/store.svelte.ts` — state.
- `frontend/src/lib/features/admin/analytics/schema.ts` — types.

## Course picker

- Reads `GET /admin/analytics/course-options` (derived from `_offerings_stmt`),
  not the catalogue; supports search `q` and limit.

## Staging / promote UI

- Lists staged dry-run rows (`/risk-staging`), filter unpromoted only;
  promote via `/risk-staging/promote` with optional scope filters.

## Error display

- Admin error envelopes normalized by `client.ts`; analytics errors surface as
  alert banners on the page.
