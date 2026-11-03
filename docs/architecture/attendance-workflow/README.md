# Attendance Workflow — Layered Architecture

Code-grounded technical documentation for the student attendance scan workflow. The
codebase is the single source of truth; every claim below cites a `path:line`.

## Scope

Covers the online scan, precheck, offline replay, liveness review, and student
history flows, sliced by architectural layer. Does not cover excuse, analytics,
or admin roster flows (see `docs/architecture/excuse-workflow.md`,
`docs/architecture/api-contracts.md`).

## Reading order

1. `01-architecture-overview.md` — layers, boundaries, dependency direction
2. `02-presentation-layer.md` — scan page, liveness, sync queue, GPS, errors
3. `03-api-and-controller-layer.md` — routers, deps, rate limit, error envelopes
4. `04-application-and-service-layer.md` — `AttendanceService`, `SessionService`
5. `05-domain-and-business-logic-layer.md` — liveness grading, geofence, status
6. `06-data-access-and-persistence-layer.md` — models, tables, queries, shims
7. `07-integrations-and-background-processing.md` — face gen, MediaPipe, cron, sync
8. `08-end-to-end-workflow.md` — online/precheck/offline/review/history (Mermaid)
9. `09-dependencies-and-data-flow.md` — dependency graph, transforms, error paths
## Layer map

| Layer | Components | Key sources |
|---|---|---|
| Presentation | Scan page, liveness, sync queue, GPS | `frontend/src/routes/student/scan/+page.svelte`, `frontend/src/lib/features/liveness/*`, `frontend/src/lib/features/sync/*` |
| API/Controller | Routers, deps, rate limit, error envelopes | `backend/src/features/attendance/router.py`, `backend/src/features/attendance/admin_router.py`, `backend/src/api/deps.py`, `backend/src/api/router.py` |
| Application | `AttendanceService`, `SessionService` lifecycle | `backend/src/features/attendance/service.py`, `backend/src/features/session/service.py` |
| Domain | Liveness grading, geofence, status anchor/windows, score bands, rates | `backend/src/features/attendance/service.py` (`_validate_liveness_evidence`, `_validate_geofence`, `_compute_status`, `_is_review_band`), `backend/src/shared/rates.py` |
| Data | Models, tables, queries, SQLite shims, transactions | `backend/src/features/attendance/model.py`, `backend/src/features/session/model.py`, SQLAlchemy in services |
| Integrations | Face embedding gen, MediaPipe, email, cron risk batch, sync replay | `backend/src/shared/face_embedding_generator.py`, `backend/src/shared/face_quality.py`, `backend/src/shared/email.py`, `backend/src/analytics/batch.py`, `backend/src/core/scheduler.py` |

## Related docs

- `docs/architecture/data-flow.md` — system-wide flow diagrams (pointers here)
- `docs/architecture/offline-first.md` — offline storage and sync
- `docs/architecture/api-contracts.md` — endpoint contract (scan `student_number` is comparison-only)
- `docs/project/decision-log.md` — decision IDs (D27, D31, D15, D16, D17, …)

Last verified against commit: see `git rev-parse HEAD`.
