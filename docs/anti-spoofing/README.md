# Anti-Spoofing — Layered Controls

Code-grounded technical documentation for the anti-spoofing controls in the
attendance workflow. The codebase is the single source of truth; every claim cites
`path:line`.

## Scope

Covers biometric quality/enrollment/matching, liveness challenge, geofence/GPS,
student identity, replay/idempotency protection, review resolution,
benchmark-mode posture, and frontend controls. Does not cover auth/account security
(see `docs/architecture/security-model.md`) or scan storage (see
`docs/attendance-workflow/`).

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
| Presentation | Face liveness UI, QR scan, GPS acquisition/location card, sync queue | `frontend/src/routes/student/scan/+page.svelte`, `frontend/src/lib/features/liveness/*`, `frontend/src/lib/features/sync/*`, `frontend/src/lib/shared/utils/geo.ts` |
| API/Controller | Scan/precheck/review endpoints, rate limit, error envelopes | `backend/src/features/attendance/router.py`, `backend/src/features/attendance/admin_router.py`, `backend/src/api/deps.py` |
| Application | AttendanceService scan pipeline, review resolution, FaceEnrollmentService | `backend/src/features/attendance/service.py`, `backend/src/features/face_enrollment/service.py` |
| Domain | Liveness grading, geofence, score bands, identity comparison, idempotency, staleness | `backend/src/features/attendance/service.py`, `backend/src/shared/face_quality.py` |
| Data | Attendance/session/student/enrollment models, review filter on evidence JSON | `backend/src/features/attendance/model.py`, `backend/src/features/session/model.py`, `backend/src/features/student/model.py` |
| Integrations | MediaPipe quality gates, MobileFaceNet embedding gen, benchmark mode, admin review audit | `backend/src/shared/face_quality.py`, `backend/src/shared/face_embedding_generator.py`, `backend/src/shared/face_embeddings.py`, `backend/src/core/config.py`, `backend/src/shared/audit.py` |

## Related docs

- `docs/architecture/security-model.md` — threat model and controls
- `docs/architecture/face-enrollment.md` — enrollment architecture
- `docs/architecture/data-flow.md` — system-wide flow diagrams
- `docs/architecture/offline-first.md` — offline storage and sync
- `docs/attendance-workflow/` — attendance scan flow and data layer
- `docs/project/decision-log.md` — D27, D31, D16, D17, ADR-083

Last verified against commit: see `git rev-parse HEAD`.
