# Project Folder Structure — QR Attendance System

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
│   │   │   ├── security.py           # (planned) HMAC signing, Argon2id hashing, TOTP
│   │   │   └── exceptions.py         # (planned) Domain exceptions + error handlers
│   │   │
│   │   ├── shared/                   # Cross-feature helpers
│   │   │   ├── __init__.py
│   │   │   ├── enums.py              # UserRole, OtpPurpose, ValidationStatus, ExcuseInitiatedBy, ExcuseInitiatedVia, ExcuseStatus, RiskLevel, BackupKind, BackupStorage, BackupStatus, ScannedVia, SyncStatus, QueueStatus
│   │   │   ├── mixins.py             # CreatedAtMixin, TimestampMixin
│   │   │   ├── dependencies.py       # (planned) get_db, pagination dependencies
│   │   │   ├── otp.py                # (planned) 6-digit OTP generate/verify vs otp_codes table
│   │   │   ├── captcha.py            # (planned) Cloudflare Turnstile siteverify
│   │   │   ├── email.py              # (planned) SMTP sender (OTP emails)
│   │   │   ├── cache.py              # (planned) LRU cache (O(1) student lookup)
│   │   │   └── base.py               # (planned) shared schemas
│   │   │
│   │   ├── api/                      # Router aggregation
│   │   │   ├── __init__.py
│   │   │   ├── router.py             # mounts auth, student, session, attendance, professor; course & enrollment routers exist unmounted
│   │   │   └── deps.py               # Dependency injection helpers
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
│   │       ├── test_students.py
│   │       ├── test_attendance.py
│   │       ├── test_cache.py
│   │       └── test_sessions.py
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
│   │   ├── decision-log.md           # ADR-format decision log (D1–D48)
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
│   │   ├── offline-first.md          # IndexedDB, sync algorithm, embedding pull
│   │   ├── security-model.md         # Threat model & mitigations
│   │   ├── data-flow.md              # Mermaid sequence diagrams
│   │   └── migration-strategy.md     # Alembic migration plan
│   ├── deployment/
│   │   ├── deployment-workflow.md    # Deployment guide
│   │   └── backup-strategy.md        # Backup pipeline (Phase 3)
│   ├── design/
│   │   ├── frontend-architecture.md  # Clean copy of frontend structure
│   │   ├── database-er.md            # ERD diagrams
│   │   └── wireframes.md             # Wireframes
│   └── presentations/                # Slides + deck (.pptx, .pdf)
│
├── docker-compose.dev.yml             # Local development: PostgreSQL + migrations + backend + frontend (frontend HMR via CHOKIDAR_USEPOLLING)
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
| `frontend/src/lib/features/liveness/components/QRScanner.svelte`                              | QR Code Detection (student-ID & session codes)                                                                              |
| `frontend/src/lib/features/liveness/` (components/ + service.ts)                              | Liveness Protocol: challenge-response, nonce anti-replay, evidence bundle (`gps_lat`/`gps_lng`/`liveness_evidence`), risk fusion |
| `backend/src/features/analytics/` (model.py; aggregation service + nightly `tasks.py` planned) | Data Mining: descriptive/diagnostic aggregation, heuristic at-risk scoring, prescriptive rules, nightly batch scheduling    |
| `backend/src/features/*/model.py`                                                             | Database Design & Normalization (3NF)                                                                                       |
| `frontend/src/lib/features/sync/service.ts` + `backend/src/features/sync/` (router/service planned) | Offline Sync / Eventual Consistency                                                                                    |
| `backend/src/features/program/` + `backend/src/features/course/`                              | Academic Hierarchy: Program → Year Level → CourseOffering (courses = templates)                                             |
| `backend/src/features/student/` (face columns; admin face-enrollment service/router planned)  | Biometrics: face embedding generation (pretrained ResNet), template protection (AES-GCM encryption), versioned distribution |
| `backend/src/features/excuse/` (model.py; service/router planned)                             | State Machine: excuse request lifecycle (pending→approved/rejected), permission matrix, audit trail                         |
| `backend/src/features/system/`                                                                | DevOps: backup pipeline (pg_dump→encrypt→store→prune), academic-structure CRUD, system settings                             |
| `frontend/src/lib/features/analytics/components/` (planned)                                   | Data Visualization: Chart.js wrapper for analytics dashboards                                                               |
| `frontend/src/lib/features/session/components/calendar/` (planned)                            | Calendar UI: month/week grid views, day detail sheets                                                                       |
| `frontend/src/routes/student/scan/` + `frontend/src/lib/features/{student,liveness}/components/` | Sequential UI Pattern: guided 5-step scan flow with state machine                                                          |
| `frontend/src/lib/features/excuse/components/` (planned)                                      | Workflow UI: excuse modals, request forms, review lists                                                                     |
| `frontend/src/lib/features/student/components/FaceEnrollmentModal.svelte` (planned)          | Capture UI: 3-photo quality gates, live preview                                                                             |

---

## Development vs Production Structure

The folder structure is identical in both environments. The differences are in configuration:

| Aspect   | Development               | Production                           |
| -------- | ------------------------- | ------------------------------------ |
| DB       | Local PostgreSQL (Docker) | Supabase (cloud)                     |
| Backend  | `uvicorn --reload`        | Fly.io (Docker)                      |
| Frontend | `npm run dev`             | Vercel (build + deploy)              |
| Env vars | `.env` file               | `fly secrets set` / Vercel dashboard |

