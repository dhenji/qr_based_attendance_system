# Project Folder Structure — QR Attendance System

> Historical intent, not current state: this doc shows the planned layout.
> Truth is `README.md` + the code — 18 feature slices, 20 tables, 23 routers
> over 15 mounts, 46 `+page.svelte` files.

```
attendance-system/
│
├── backend/                          # FastAPI Python backend — vertical feature slicing
│   ├── src/                          # Application source (src-layout)
│   │   ├── main.py                   # FastAPI app entry point (uvicorn main:app --app-dir src)
│   │   │
│   │   ├── core/                     # Cross-cutting infrastructure (no business logic)
│   │   │   ├── __init__.py
│   │   │   ├── config.py             # App settings, environment variables
│   │   │   ├── database.py           # Async SQLAlchemy engine + session factory + Base
│   │   │   ├── security.py           # Argon2id hashing, JWT access/refresh/recovery tokens, OTP, backup-code fingerprints
│   │   │   └── exceptions.py         # AppException/DomainException/DatabaseException + error handler
│   │   │
│   │   ├── shared/                   # Cross-feature helpers
│   │   │   ├── __init__.py
│   │   │   ├── enums.py              # UserRole, OtpPurpose, ValidationStatus, ExcuseInitiatedBy, ExcuseInitiatedVia, ExcuseStatus, RiskLevel, BackupKind, BackupStorage, BackupStatus, ScannedVia, SyncStatus, QueueStatus
│   │   │   ├── mixins.py             # CreatedAtMixin, TimestampMixin
│   │   │   ├── dependencies.py       # pagination + reusable annotated deps
│   │   │   ├── captcha.py            # Cloudflare Turnstile siteverify (key-gated no-op when unset)
│   │   │   ├── email.py              # SMTP sender (OTP + excuse notifications), config-gated no-op when SMTP_HOST unset
│   │   │   ├── cache.py              # LRU cache (O(1) student lookup)
│   │   │   ├── rate_limit.py         # in-process sliding-window limiter
│   │   │   ├── validators.py         # password policy, email/ID normalization
│   │   │   ├── pagination.py         # page/size + PaginatedResponse
│   │   │   └── base.py               # BaseCRUD[T] generic
│   │   │
│   │   ├── api/                      # Router aggregation
│   │   │   ├── __init__.py
│   │   │   ├── router.py             # mounts auth, admin/users, student, attendance, session, professor; course & enrollment routers exist unmounted
│   │   │   └── deps.py               # _get_db, _get_current_user, require_role, AuthServiceDep/AdminServiceDep
│   │   │
│   │   ├── features/                 # Vertical slices — one folder per domain
│   │   │   ├── auth/                 # model.py: User, OtpCodes (router mounted)
│   │   │   ├── student/              # model.py: Student (router mounted)
│   │   │   ├── session/              # model.py: Session (router mounted)
│   │   │   ├── attendance/           # model.py: Attendance (router mounted)
│   │   │   ├── professor/            # model.py: Professor (router mounted)
│   │   │   ├── course/               # model.py: Course, CourseOffering (router file exists, unmounted)
│   │   │   ├── course_professor/     # model.py: CourseProfessor + service.py
│   │   │   ├── enrollment/           # model.py: Enrollment (router file exists, unmounted)
│   │   │   ├── program/              # model.py: Program, YearLevel (no router file)
│   │   │   ├── excuse/               # model.py: ExcuseRequest (model only)
│   │   │   ├── analytics/            # model.py: StudentRiskScore (model only)
│   │   │   ├── sync/                 # model.py: SyncQueue (no router file)
│   │   │   └── system/               # model.py: BackupLog (model only)
│   │   │
│   │   └── tests/                    # (planned) Unit & integration tests
│   │       ├── conftest.py
│   │       ├── test_auth.py
│   │       ├── test_program.py
│   │       ├── test_student.py
│   │       ├── test_session.py
│   │       └── test_attendance.py
│   │
│   ├── alembic/                      # Database migration files
│   │   └── versions/                 # initial_schema (users, students, courses, …)
│   │
│   ├── requirements.txt              # Python dependencies
│   ├── Dockerfile.dev                # Local dev container
│   ├── Dockerfile                    # (planned) Production image for Fly.io
│   ├── fly.toml                      # (planned) Fly.io deployment config
│   ├── .env.example                  # Template for local env vars
│   └── .env                          # Local environment variables (gitignored)
│
├── frontend/                         # SvelteKit app — mock-first feature slices (SvelteKit 2 + Svelte 5 runes)
│   ├── src/
│   │   ├── app.html                  # Main HTML template
│   │   ├── app.d.ts                  # Global TypeScript declarations
│   │   ├── hooks.client.ts           # Connectivity → offline store; sync trigger
│   │   │
│   │   ├── lib/
│   │   │   ├── index.ts              # Barrel exports
│   │   │   ├── app/                  # session.svelte.ts (auth session, role switcher), offline.svelte.ts (online status + pending queue)
│   │   │   ├── api/                  # client.ts (fetch wrapper, MOCK flag) + endpoints.ts (typed mock endpoint map)
│   │   │   ├── features/             # one folder per frontend domain
│   │   │   │   ├── auth/             # service.ts, store.svelte.ts, schema.ts, mock.ts, components/
│   │   │   │   ├── student/          # service.ts, store.svelte.ts, mock.ts, components/
│   │   │   │   ├── session/          # service.ts, store.svelte.ts, schema.ts, mock.ts, components/
│   │   │   │   ├── attendance/       # service.ts, store.svelte.ts, schema.ts, mock.ts
│   │   │   │   ├── liveness/         # store.svelte.ts (scan state machine), bundle.ts, schema.ts, components/ — frontend-only feature
│   │   │   │   ├── sync/             # service.ts, db.ts (IndexedDB wrapper), engine.ts (enqueue/dequeue/retry/status)
│   │   │   │   ├── course/  ○        # deferred — empty until backend
│   │   │   │   ├── enrollment/ ○     # deferred
│   │   │   │   └── analytics/ ○      # deferred
│   │   │   └── shared/
│   │   │       ├── styles/tokens.css # palette, spacing, radius, status colors
│   │   │       ├── ui/               # Button, Card, Input, Select, Toggle, Table, Badge, Modal, EmptyState
│   │   │       ├── components/       # Sidebar, Topbar, StatusBadge, OfflineBanner
│   │   │       ├── utils/            # geo.ts (haversine + geofence), format.ts, gen.ts, qr.ts
│   │   │       ├── constants/        # roles.ts, routes.ts, status.ts
│   │   │       ├── types/            # mirrors backend models (user, student, course, enrollment, session, attendance, liveness, sync)
│   │   │       └── validators/       # base.ts shared zod bits (email, id, password strength)
│   │   │
│   │   └── routes/                   # auth/login, auth/register, student/dashboard, student/scan, professor/sessions
│   │
│   ├── static/                       # Static assets (favicon, logo)
│   ├── svelte.config.js              # SvelteKit configuration
│   ├── vite.config.ts                # Vite config (vite-plugin-pwa: Deferred)
│   ├── tsconfig.json                 # TypeScript strict config
│   ├── package.json                  # Node dependencies
│   ├── .env.example                  # PUBLIC_API_URL template
│   └── .env                          # PUBLIC_API_URL (gitignored)
│
├── docs/                             # Documentation
│   ├── project/
│   │   ├── decision-log.md           # ADR-format decision log (D1–D73)
│   │   └── glossary.md               # Term definitions
│   ├── proposals/
│   │   ├── proposal.md               # Full project proposal
│   │   ├── proposal_simple.md        # Simplified proposal (1st week)
│   │   ├── models.md                 # ML/model catalog
│   │   └── contributions.md          # CS contribution mapping
│   ├── architecture/
│   │   ├── frontend-architecture.md  # Production SvelteKit structure
│   │   ├── project-structure.md      # This file
│   │   ├── api-contracts.md          # Endpoint schemas & conventions
│   │   ├── offline-first.md          # IndexedDB, sync algorithm, embedding pull (stub; no comparison)
│   │   ├── security-model.md         # Threat model & mitigations
│   │   ├── data-flow.md              # Mermaid sequence diagrams
│   │   └── migration-strategy.md     # Alembic migration plan
│   ├── deployment/
│   │   ├── deployment-workflow.md    # Deployment guide
│   │   └── backup-strategy.md        # Backup pipeline (Phase 3)
│   ├── design/
│   │   ├── database-er.md            # ERD diagrams
│   │   └── wireframes.md             # Wireframes
│   └── presentations/                # Slides + deck (.pptx, .pdf)
│
├── docker-compose.dev.yml             # Local development: PostgreSQL + migrations + backend + frontend (frontend HMR via CHOKIDAR_USEPOLLING)
├── .github/workflows/ci.yml           # CI: backend suite, alembic drift check, frontend typecheck (ADR-069)
├── AGENTS.md                         # Repo conventions & reference
├── .gitignore
└── README.md                         # Project overview & setup instructions
```

> **Implemented so far:** `model.py` for `src/features/auth/`, `src/features/student/`,
> `src/features/course/`, `src/features/enrollment/`, `src/features/session/`,
> `src/features/attendance/` (incl. evidence/excuse columns: `liveness_evidence`,
> `face_match_score`, `scanned_via`, `original_status`, `excuse_*`), `src/features/sync/`,
> `src/features/program/`, `src/features/course_professor/`, `src/features/excuse/`
> (ExcuseRequest: `initiated_by`/`initiated_via`, `attachment_urls`, `status`,
> `reviewed_by`/`reviewed_at`), plus `src/shared/enums.py` and `src/shared/mixins.py`.
> Model layer is now complete (16/16): `analytics` (StudentRiskScore) + `system`
> (BackupLog) are modeled. Remaining work: `schema.py`/`service.py`/`router.py`
> layers for all features (exception: `course_professor/service.py` exists);
> `liveness` is a frontend-only feature (no backend `features/liveness/` dir).

> **Deferred (frontend):** `src/service-worker.ts` (PWA offline caching & background
> sync), `hooks.server.ts`, `vite-plugin-pwa`, `static/icons/`.

---

## Key Directories & Their CS Concept Mapping

| Directory / File                                                                              | CS Concept                                                                                                                  |
| --------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `backend/src/shared/cache.py` (planned)                                                        | Caching & Indexing Algorithm (O(1) lookup)                                                                                  |
| `frontend/src/lib/features/sync/service.ts` (+ planned `db.ts`/`engine.ts`; service-worker deferred) | Offline-First Architecture                                                                                             |
| `backend/src/features/session/` + `backend/src/core/security.py`                              | HMAC-based Session Auth                                                                                                     |
| `frontend/src/lib/shared/utils/geo.ts` + `backend/src/features/attendance/` (service.py planned) | Geolocation Proximity (Haversine)                                                                                         |
| `frontend/src/lib/features/liveness/components/QRScanner.svelte`                              | QR Code Detection (session code only; no student-ID QR)                                                                     |
| `frontend/src/lib/features/liveness/` (components/ + service.ts)                              | Liveness Protocol: challenge-response, nonce anti-replay, evidence bundle (`gps_lat`/`gps_lng`/`liveness_evidence`), risk fusion |
| `backend/src/features/analytics/` (model.py; aggregation service + nightly `tasks.py` planned) | Data Mining: descriptive/diagnostic aggregation, heuristic at-risk scoring, prescriptive rules, nightly batch scheduling    |
| `backend/src/features/*/model.py`                                                             | Database Design & Normalization (3NF)                                                                                       |
| `frontend/src/lib/features/sync/service.ts` + `backend/src/features/sync/` (router/service planned) | Offline Sync / Eventual Consistency                                                                                    |
| `backend/src/features/program/` + `backend/src/features/course/`                              | Academic Hierarchy: Program → Year Level → CourseOffering (courses = templates)                                             |
| `backend/src/features/student/` + `backend/src/features/face_enrollment/`                      | Biometrics: enrollment service/router (placeholder embedding; real generation/encryption not implemented)                    |
| `backend/src/features/excuse/` (model.py; service/router planned)                             | State Machine: excuse request lifecycle (pending→approved/rejected), permission matrix, audit trail                         |
| `backend/src/features/system/`                                                                | DevOps: backup pipeline (pg_dump→encrypt→store→prune), academic-structure CRUD, system settings                             |
| `frontend/src/lib/features/report/components/`                                       | Data Visualization: hand-rolled SVG charts (`ReportTrendChart.svelte`, `ReportBarChart.svelte`) — no chart library (ADR-091)                            |
| `frontend/src/lib/features/session/components/calendar/` (planned)                            | Calendar UI: month/week grid views, day detail sheets                                                                       |
| `frontend/src/routes/student/scan/` + `frontend/src/lib/features/{student,liveness}/components/` | Sequential UI Pattern: guided scan flow (entry→ID→QR→liveness) with state machine                                          |
| `frontend/src/lib/features/excuse/components/` (planned)                                      | Workflow UI: excuse modals, request forms, review lists                                                                     |
| `frontend/src/routes/admin/students/+page.svelte` (inline modal)                              | Enrollment UI: 3-photo file upload (no quality gates; placeholder embedding)                                                |

---

## Development vs Production Structure

The folder structure is identical in both environments. The differences are in configuration:

| Aspect   | Development               | Production                           |
| -------- | ------------------------- | ------------------------------------ |
| DB       | Local PostgreSQL (Docker) | Supabase (cloud)                     |
| Backend  | `uvicorn --reload`        | Fly.io (Docker)                      |
| Frontend | `npm run dev`             | Vercel (build + deploy)              |
| Env vars | `.env` file               | `fly secrets set` / Vercel dashboard |

