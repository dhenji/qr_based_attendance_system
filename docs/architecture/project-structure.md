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
│   │   │   ├── enums.py              # UserRole, OtpPurpose, ValidationStatus, SyncStatus, QueueStatus
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
│   │   │   ├── router.py             # (planned) mounts all features' routers under /prefixes
│   │   │   └── deps.py               # Dependency injection helpers
│   │   │
│   │   ├── features/                 # Vertical slices — one folder per domain,
│   │   │   │                         # each owning all four layers:
│   │   │   ├── auth/                 # │ ├─ model.py   (SQLAlchemy ORM)
│   │   │   ├── student/              # │ ├─ schema.py  (Pydantic v2)
│   │   │   ├── course/               # │ ├─ service.py (business logic)
│   │   │   ├── enrollment/           # │ └─ router.py  (endpoints)
│   │   │   ├── professor/            #   claim-based self-registration (OTP)
│   │   │   ├── program/              #   program CRUD, year-level management,
│   │   │   │                         #   term structure editing
│   │   │   ├── session/              #   HMAC session codes & expiry
│   │   │   ├── attendance/           #   validation pipeline (HMAC→GPS→liveness→uniqueness→enrollment)
│   │   │   ├── face_enrollment/      #   3-photo capture, embedding generation,
│   │   │   │                         #   versioned storage, revocation
│   │   │   ├── liveness/             #   face challenges, evidence bundles,
│   │   │   │                         #   nonce registry, risk-fusion scoring
│   │   │   ├── excuse/               #   excuse state machine (3 initiation paths),
│   │   │   │                         #   bulk excuse-all, evidence attachments
│   │   │   ├── analytics/            #   aggregations, at-risk heuristic scoring,
│   │   │   │                         #   prescriptive rule engine, nightly batch
│   │   │   │   └── tasks.py          #   APScheduler jobs (risk batch nightly, retention prune)
│   │   │   ├── system/               #   backup pipeline, academic-structure updates,
│   │   │   │                         #   system settings, audit logging
│   │   │   └── sync/                 #   offline SyncQueue processing
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
├── frontend/                         # SvelteKit PWA frontend
│   ├── src/
│   │   ├── app.html                  # Main HTML template
│   │   ├── app.d.ts                  # Global TypeScript declarations
│   │   ├── hooks.server.ts           # Auth, authorization, request hooks
│   │   ├── hooks.client.ts           # Theme, analytics, reconnect handling
│   │   ├── service-worker.ts         # PWA offline caching & background sync
│   │   │
│   │   ├── routes/
│   │   │   ├── +layout.svelte        # Root application layout
│   │   │   ├── +error.svelte         # Global error page
│   │   │   ├── +page.svelte          # Landing page
│   │   │   │
│   │   │   ├── (auth)/
│   │   │   │   ├── +layout.svelte    # Authentication layout
│   │   │   │   ├── login/            # Login page (+page.ts redirects authed)
│   │   │   │   ├── register/         # Registration page + loader
│   │   │   │   ├── forgot-password/  # Forgot password
│   │   │   │   └── reset-password/   # Reset password
│   │   │   │
│   │   │   ├── (student)/
│   │   │   │   ├── +layout.svelte    # Student layout/sidebar
│   │   │   │   ├── dashboard/        # Dashboard overview
│   │   │   │   ├── scan/
│   │   │   │   │   ├── step/         # 5-step scan flow
│   │   │   │   │   │   ├── 1/        # 2.2a Session Entry (code/QR)
│   │   │   │   │   │   ├── 2/        # 2.2b ID Scan
│   │   │   │   │   │   ├── 3/        # 2.2c Location Check
│   │   │   │   │   │   ├── 4/        # 2.2d Face Check
│   │   │   │   │   │   └── 5/        # 2.2e Result
│   │   │   │   │   └── +page.svelte  # Scanner root redirect
│   │   │   │   ├── history/          # 2.7 Attendance history + filters
│   │   │   │   ├── schedule/         # 2.8 Calendar (month/week)
│   │   │   │   ├── excuses/          # Student excuse requests
│   │   │   │   ├── profile/          # 2.10 Read-only profile
│   │   │   │   └── settings/         # 2.11 Appearance/Notifications/Security
│   │   │   │
│   │   │   ├── (professor)/
│   │   │   │   ├── +layout.svelte    # Professor layout
│   │   │   │   ├── dashboard/        # 3.1 Dashboard (today's sessions, quick actions)
│   │   │   │   ├── courses/
│   │   │   │   │   ├── +page.svelte  # 3.6 My Courses (grouped by program)
│   │   │   │   │   └── [id]/         # 3.6 Course detail deep-link
│   │   │   │   ├── sessions/
│   │   │   │   │   ├── new/          # 3.2a/b Session creation (locked vs selector)
│   │   │   │   │   ├── active/[id]/  # 3.3 Active session (dual timers)
│   │   │   │   │   └── history/      # 3.5 Session history
│   │   │   │   ├── attendance/       # 3.4 Attendance list (filters + section)
│   │   │   │   ├── reports/          # 3.7 Reports (3 tabs: All/Course/Trends)
│   │   │   │   ├── excuses/          # Excuse request review
│   │   │   │   ├── profile/          # 3.9 Read-only profile
│   │   │   │   └── settings/         # 3.9 Change password / MFA
│   │   │   │
│   │   │   └── (admin)/
│   │   │       ├── +layout.svelte    # Admin layout
│   │   │       ├── dashboard/        # 4.1 Dashboard (KPIs, quick actions)
│   │   │       ├── students/         # Student management (CRUD/import/archive)
│   │   │       ├── professors/       # Professor management
│   │   │       ├── programs/
│   │   │       │   ├── +page.svelte  # 4.5a Programs list
│   │   │       │   └── [id]/
│   │   │       │       ├── +page.svelte  # 4.5b Program detail (year tabs)
│   │   │       │       ├── years/[yid]/
│   │   │       │       │   └── courses/  # 4.5c Year-level courses
│   │   │       │       │       └── [cid]/ # 4.5d Course detail (tabs)
│   │   │       │       └── courses/[cid]/ # Direct course access
│   │   │       ├── analytics/        # 4.7 Analytics & Reports (5 tabs)
│   │   │       ├── audit-logs/       # Audit trail viewer
│   │   │       ├── system/
│   │   │       │   ├── settings/     # 4.10 System settings
│   │   │       │   └── backups/      # Backup management
│   │   │       └── face-enrollment/  # Face enrollment admin tool
│   │   │
│   │   ├── lib/
│   │   │   ├── components/
│   │   │   │   ├── attendance/       # Attendance UI components
│   │   │   │   ├── scanner/          # QR scanner module
│   │   │   │   │   ├── QRScanner.svelte       # Camera QR scanner
│   │   │   │   │   ├── CameraView.svelte      # Camera preview
│   │   │   │   │   ├── ScannerOverlay.svelte  # Scanner guide
│   │   │   │   │   ├── SessionCodeInput.svelte# Session code input
│   │   │   │   │   ├── GPSStatus.svelte       # GPS indicator
│   │   │   │   │   ├── FaceChallenge.svelte   # Blink/head-turn liveness challenges
│   │   │   │   │   ├── ChallengePrompt.svelte # Live challenge instruction overlay
│   │   │   │   │   ├── LivenessStatus.svelte  # Liveness evidence status
│   │   │   │   │   ├── PermissionPrompt.svelte# Camera/GPS permissions
│   │   │   │   │   ├── ScanResult.svelte      # Result message
│   │   │   │   │   ├── OfflineStatus.svelte   # Pending sync/liveness queue
│   │   │   │   │   ├── Step1SessionEntry.svelte   # 2.2a code/QR entry
│   │   │   │   │   ├── Step2IdScan.svelte         # 2.2b student-ID QR
│   │   │   │   │   ├── Step3LocationCheck.svelte  # 2.2c GPS validation
│   │   │   │   │   ├── Step4FaceCheck.svelte      # 2.2d liveness challenge
│   │   │   │   │   └── Step5Result.svelte         # 2.2e success/fail overlay
│   │   │   │   ├── charts/
│   │   │   │   │   └── ChartCanvas.svelte    # Reusable Chart.js wrapper (D41)
│   │   │   │   ├── calendar/
│   │   │   │   │   ├── MonthGrid.svelte      # 2.8 Month calendar view
│   │   │   │   │   ├── WeekGrid.svelte       # 2.8 Week calendar view
│   │   │   │   │   └── DaySheet.svelte       # 2.8 Day detail sheet
│   │   │   │   ├── excuse/
│   │   │   │   │   ├── QuickModal.svelte     # Prof quick-excuse (D21 path a)
│   │   │   │   │   ├── RequestForm.svelte    # Student excuse request (D21 path c)
│   │   │   │   │   └── ReviewList.svelte     # Prof review pending requests
│   │   │   │   ├── face-enrollment/
│   │   │   │   │   └── FaceEnrollmentModal.svelte  # 3-photo capture modal
│   │   │   │   ├── dashboard/         # Dashboard widgets
│   │   │   │   ├── forms/             # Form components
│   │   │   │   ├── modals/            # Modal dialogs
│   │   │   │   ├── navigation/        # Navbar/Sidebar
│   │   │   │   ├── ui/                # Generic UI
│   │   │   │   └── common/            # Loading/Error states
│   │   │   │
│   │   │   ├── services/             # API communication layer
│   │   │   │   ├── api.ts            # HTTP client (fetch wrapper)
│   │   │   │   ├── auth.ts           # Auth API
│   │   │   │   ├── attendance.ts     # Attendance API
│   │   │   │   ├── student.ts        # Student API
│   │   │   │   ├── professor.ts      # Professor API
│   │   │   │   ├── course.ts         # Course API
│   │   │   │   ├── report.ts         # Reports API
│   │   │   │   ├── session.ts        # Session API
│   │   │   │   ├── liveness.ts       # Liveness evidence API
│   │   │   │   ├── analytics.ts      # Analytics API (aggregations, forecasts)
│   │   │   │   ├── gps.ts            # GPS helpers
│   │   │   │   └── qr.ts             # QR helpers
│   │   │   │
│   │   │   ├── stores/               # Global reactive stores (auth, offline, attendance)
│   │   │   ├── offline/              # IndexedDB & sync logic
│   │   │   ├── validators/           # Zod validators
│   │   │   ├── constants/            # Roles, routes, status
│   │   │   ├── types/                # TypeScript models
│   │   │   ├── utils/                # Shared utilities (hmac, geolocation, format)
│   │   │   └── server/
│   │   │       ├── auth.ts           # Server auth helpers
│   │   │       ├── cookies.ts        # Cookie helpers
│   │   │       ├── permissions.ts    # RBAC utilities
│   │   │       └── session.ts        # Server session utilities
│   │   │
│   │   └── ...                       # NOTE: src/ source files not yet written (scaffold only)
│   │
│   ├── static/                       # Static assets
│   │   ├── icons/                    # PWA icons (192x192, 512x512)
│   │   ├── images/                   # Images & logos
│   │   ├── fonts/                    # Custom fonts
│   │   ├── manifest.json             # PWA manifest file
│   │   ├── robots.txt                # Robots rules
│   │   └── favicon.png               # Website icon
│   │
│   ├── svelte.config.js              # SvelteKit configuration
│   ├── vite.config.ts                # Vite + PWA plugin configuration
│   ├── tsconfig.json                 # TypeScript strict config
│   ├── package.json                  # Node dependencies
│   ├── .env.example                  # PUBLIC_API_URL template
│   └── .env                          # PUBLIC_API_URL (gitignored)
│
├── docs/                             # Documentation
│   ├── project/
│   │   ├── decision-log.md           # ADR-format decision log (D1–D43)
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
├── docker-compose.yml                # Local development: PostgreSQL + migrations + backend
├── AGENTS.md                         # Repo conventions & reference
├── .gitignore
└── README.md                         # Project overview & setup instructions
```

> **Implemented so far:** `model.py` for `src/features/auth/`, `src/features/student/`,
> `src/features/course/`, `src/features/enrollment/`, `src/features/session/`,
> `src/features/attendance/`, `src/features/sync/` (all 7 tables created by the initial
> Alembic migration), plus `src/shared/enums.py` and `src/shared/mixins.py`. Planned
> next: `professors` + `otp_codes` tables, account-security fields on `users`
> (security question, MFA, lockout, `must_change_password`), `email/middle_name/section`
> on `students`, and the missing `schema.py`, `service.py`, `router.py`, `liveness/`,
> `analytics/` layers.

---

## Key Directories & Their CS Concept Mapping

| Directory / File                                                                              | CS Concept                                                                                                                  |
| --------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `backend/src/shared/cache.py`                                                                 | Caching & Indexing Algorithm (O(1) lookup)                                                                                  |
| `frontend/src/lib/stores/offline.ts` + `frontend/src/service-worker.ts`                       | Offline-First Architecture                                                                                                  |
| `backend/src/features/session/` + `backend/src/core/security.py`                              | HMAC-based Session Auth                                                                                                     |
| `frontend/src/lib/utils/geolocation.ts` + `backend/src/features/attendance/service.py`        | Geolocation Proximity (Haversine)                                                                                           |
| `frontend/src/lib/components/scanner/QRScanner.svelte`                                        | Live QR Detection (Liveness)                                                                                                |
| `frontend/src/lib/components/scanner/FaceChallenge.svelte` + `backend/src/features/liveness/` | Liveness Protocol: challenge-response, evidence bundles, nonce anti-replay, risk fusion                                     |
| `backend/src/features/analytics/` + `tasks.py`                                                | Data Mining: descriptive/diagnostic aggregation, heuristic at-risk scoring, prescriptive rules, nightly batch scheduling    |
| `backend/src/features/*/model.py`                                                             | Database Design & Normalization (3NF)                                                                                       |
| `backend/src/features/sync/service.py` + `frontend/src/lib/services/sync.ts`                  | Offline Sync / Eventual Consistency                                                                                         |
| `backend/src/features/program/`                                                               | Academic Hierarchy: Program → Year Level → Course (tree structure, FK constraints)                                          |
| `backend/src/features/face_enrollment/`                                                       | Biometrics: face embedding generation (pretrained ResNet), template protection (AES-GCM encryption), versioned distribution |
| `backend/src/features/excuse/`                                                                | State Machine: excuse request lifecycle (pending→approved/rejected), permission matrix, audit trail                         |
| `backend/src/features/system/`                                                                | DevOps: backup pipeline (pg_dump→encrypt→store→prune), academic-structure CRUD, system settings                             |
| `frontend/src/lib/components/charts/ChartCanvas.svelte`                                       | Data Visualization: Chart.js wrapper for analytics dashboards                                                               |
| `frontend/src/lib/components/calendar/`                                                       | Calendar UI: month/week grid views, day detail sheets                                                                       |
| `frontend/src/lib/components/scanner/Step[1-5]*.svelte`                                       | Sequential UI Pattern: guided 5-step scan flow with state machine                                                           |
| `frontend/src/lib/components/excuse/`                                                         | Workflow UI: excuse modals, request forms, review lists                                                                     |
| `frontend/src/lib/components/face-enrollment/FaceEnrollmentModal.svelte`                      | Capture UI: 3-photo quality gates, live preview                                                                             |

---

## Development vs Production Structure

The folder structure is identical in both environments. The differences are in configuration:

| Aspect   | Development               | Production                           |
| -------- | ------------------------- | ------------------------------------ |
| DB       | Local PostgreSQL (Docker) | Supabase (cloud)                     |
| Backend  | `uvicorn --reload`        | Fly.io (Docker)                      |
| Frontend | `npm run dev`             | Vercel (build + deploy)              |
| Env vars | `.env` file               | `fly secrets set` / Vercel dashboard |

