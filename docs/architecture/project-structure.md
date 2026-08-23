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
│   │   │   ├── security.py           # (planned) HMAC signing, bcrypt hashing, TOTP
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
│   │   │   ├── session/              #   HMAC session codes & expiry
│   │   │   ├── attendance/           #   validation pipeline (HMAC→GPS→liveness→uniqueness→enrollment)
│   │   │   ├── liveness/             #   face challenges, evidence bundles,
│   │   │   │                         #   nonce registry, risk-fusion scoring
│   │   │   ├── analytics/            #   aggregations, at-risk forecasting,
│   │   │   │                         #   prescriptive rule engine
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
│   │   │   │   ├── dashboard/        # Dashboard, attendance, history, schedule,
│   │   │   │   │                     #  notifications, profile, settings
│   │   │   │   └── scan/             # QR scanner, success, failed
│   │   │   │
│   │   │   ├── (professor)/
│   │   │   │   ├── +layout.svelte    # Professor layout
│   │   │   │   └── dashboard/        # Attendance (list/live/history/export),
│   │   │   │                         #  sessions (create/active/history), courses,
│   │   │   │                         #  reports (daily/weekly/monthly/export),
│   │   │   │                         #  profile, settings
│   │   │   │
│   │   │   └── (admin)/
│   │   │       ├── +layout.svelte    # Admin layout
│   │   │       └── dashboard/        # Students (create/edit/import/archive),
│   │   │                             #  professors, courses (create/edit/schedule),
│   │   │                             #  attendance (overview/analytics), reports
│   │   │                             #  (attendance/students/professors/export),
│   │   │                             #  audit-logs, system (settings/backup/maintenance),
│   │   │                             #  profile
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
│   │   │   │   │   └── OfflineStatus.svelte   # Pending sync/liveness queue
│   │   │   │   ├── dashboard/         # Dashboard widgets
│   │   │   │   ├── charts/            # Chart components
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
│   ├── proposals/
│   │   ├── proposal.md               # Full project proposal
│   │   └── proposal_simple.md        # Simplified proposal (1st week)
│   ├── architecture/
│   │   ├── frontend-architecture.md  # Production SvelteKit structure
│   │   └── project-structure.md      # This file
│   ├── deployment/
│   │   └── deployment-workflow.md    # Deployment guide
│   ├── design/
│   │   ├── frontend-architecture.md  # Clean copy of frontend structure
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

| Directory / File | CS Concept |
|-----------------|------------|
| `backend/src/shared/cache.py` | Caching & Indexing Algorithm (O(1) lookup) |
| `frontend/src/lib/stores/offline.ts` + `frontend/src/service-worker.ts` | Offline-First Architecture |
| `backend/src/features/session/` + `backend/src/core/security.py` | HMAC-based Session Auth |
| `frontend/src/lib/utils/geolocation.ts` + `backend/src/features/attendance/service.py` | Geolocation Proximity (Haversine) |
| `frontend/src/lib/components/scanner/QRScanner.svelte` | Live QR Detection (Liveness) |
| `frontend/src/lib/components/scanner/FaceChallenge.svelte` + `backend/src/features/liveness/` | Liveness Protocol: challenge-response, evidence bundles, nonce anti-replay, risk fusion |
| `backend/src/features/analytics/` | Data Mining: descriptive/diagnostic aggregation, predictive forecasting, prescriptive rules |
| `backend/src/features/*/model.py` | Database Design & Normalization (3NF) |
| `backend/src/features/sync/service.py` + `frontend/src/lib/services/sync.ts` | Offline Sync / Eventual Consistency |

---

## Development vs Production Structure

The folder structure is identical in both environments. The differences are in configuration:

| Aspect | Development | Production |
|--------|------------|------------|
| DB | Local PostgreSQL (Docker) | Supabase (cloud) |
| Backend | `uvicorn --reload` | Fly.io (Docker) |
| Frontend | `npm run dev` | Vercel (build + deploy) |
| Env vars | `.env` file | `fly secrets set` / Vercel dashboard |