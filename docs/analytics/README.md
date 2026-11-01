# Analytics — Layered Architecture

Code-grounded technical documentation for the admin analytics and risk-scoring
slice. The codebase is the single source of truth; every claim cites `path:line`.

## Scope

Covers admin analytics (`/admin/analytics/*`): overview, course comparison,
trends, at-risk, course options, risk refresh, risk staging/promote, and the
nightly risk batch. Does not cover attendance scan flow (see
`docs/attendance-workflow/`) or excuse analytics.

## Reading order

1. `01-architecture-overview.md`
2. `02-presentation-layer.md`
3. `03-api-and-controller-layer.md`
4. `04-application-and-service-layer.md`
5. `05-domain-and-business-logic-layer.md`
6. `06-data-access-and-persistence-layer.md`
7. `07-integrations-and-background-processing.md`
8. `08-end-to-end-workflow.md`
9. `09-dependencies-and-data-flow.md`
10. `10-documentation-alignment-audit.md`

## Layer map

| Layer | Components | Key sources |
|---|---|---|
| Presentation | Admin analytics page, filters, staging/promote UI | `frontend/src/routes/admin/analytics/+page.svelte`, `frontend/src/lib/features/admin/analytics/*` |
| API/Controller | Analytics router, deps, rate limit, error envelopes | `backend/src/features/analytics/router.py`, `backend/src/api/deps.py`, `backend/src/api/router.py` |
| Application | `AnalyticsService`, batch orchestration | `backend/src/features/analytics/service.py`, `backend/src/features/analytics/batch.py` |
| Domain | Rates, cohorts, risk features, decision table, trend slope | `backend/src/shared/rates.py`, `backend/src/shared/cohorts.py`, `backend/src/features/analytics/service.py`, `backend/src/features/analytics/batch.py`, `backend/src/core/config.py` |
| Data | Risk score/staging models, attendance/session/course/enrollment/program models, queries | `backend/src/features/analytics/model.py`, `backend/src/features/*/model.py` |
| Integrations | Nightly cron risk batch, staging/promote, CSV export | `backend/src/core/scheduler.py`, `backend/src/features/analytics/batch.py`, `backend/src/features/analytics/router.py` |

## Related docs

- `docs/architecture/risk-model.md` — detailed risk feature derivations
- `docs/architecture/api-contracts.md` — endpoint contract
- `docs/architecture/data-flow.md` — system-wide flow diagrams
- `docs/attendance-workflow/` — attendance scan flow and data layer
- `docs/project/decision-log.md` — D34, D35, D85, D86, ADR-084, ADR-085

Last verified against commit: see `git rev-parse HEAD`.
