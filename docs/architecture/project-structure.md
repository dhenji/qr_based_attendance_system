# Project Folder Structure — QR Attendance System

```
attendance-system/
│
├── backend/                          # FastAPI Python backend — vertical feature slicing
│   ├── main.py                       # FastAPI app entry point (uvicorn main:app)
│   │
│   ├── core/                         # Cross-cutting infrastructure (no business logic)
│   │   ├── __init__.py
│   │   ├── config.py                 # App settings, environment variables
│   │   ├── database.py               # Async SQLAlchemy engine + session factory + Base
│   │   ├── security.py               # HMAC signing, password hashing
│   │   └── exceptions.py             # Domain exceptions + error handlers
│   │
│   ├── shared/                       # Cross-feature helpers
│   │   ├── __init__.py
│   │   ├── dependencies.py           # get_db, pagination dependencies
│   │   ├── cache.py                  # LRU cache (O(1) student lookup)
│   │   └── base.py                   # Base model mixins, shared schemas
│   │
│   ├── api/                          # Router aggregation
│   │   ├── __init__.py
│   │   └── router.py                 # Mounts all features' routers under /prefixes
│   │
│   ├── features/                     # Vertical slices — one folder per domain,
│   │   │                             # each owning all four layers:
│   │   ├── auth/                     # │ ├─ model.py   (SQLAlchemy ORM)
│   │   ├── student/                  # │ ├─ schema.py  (Pydantic v2)
│   │   ├── course/                   # │ ├─ service.py (business logic)
│   │   ├── enrollment/               # │ └─ router.py  (endpoints)
│   │   ├── session/                  #   HMAC session codes & expiry
│   │   ├── attendance/               #   validation pipeline (HMAC→GPS→uniqueness→enrollment)
│   │   └── sync/                     #   offline SyncQueue processing
│   │
│   ├── tests/                        # Unit & integration tests
│   │   ├── test_students.py
│   │   ├── test_attendance.py
│   │   ├── test_cache.py
│   │   └── test_sessions.py
│   │
│   ├── alembic/                      # Database migration files
│   │   ├── versions/
│   │   └── env.py
│   │
│   ├── requirements.txt              # Python dependencies
│   ├── Dockerfile                    # Container image for Fly.io
│   ├── fly.toml                      # Fly.io deployment config
│   └── .env                          # Local environment variables (gitignored)
│
├── frontend/                         # SvelteKit PWA frontend
│   ├── src/
│   │   ├── routes/                   # Page-based routing (SvelteKit)
│   │   │   ├── +page.svelte          # Landing page / login
│   │   │   ├── +layout.svelte        # Main layout wrapper
│   │   │   ├── professor/
│   │   │   │   ├── +page.svelte      # Professor dashboard
│   │   │   │   └── session/
│   │   │   │       └── +page.svelte  # Create & manage session
│   │   │   ├── student/
│   │   │   │   └── scan.svelte       # QR scanner page
│   │   │   └── admin/
│   │   │       ├── students.svelte   # Student roster management
│   │   │       ├── courses.svelte    # Course management
│   │   │       └── reports.svelte    # Attendance reports
│   │   │
│   │   ├── lib/
│   │   │   ├── components/           # Reusable UI components
│   │   │   │   ├── QRScanner.svelte       # Camera QR scanner
│   │   │   │   ├── GPSReader.svelte       # Geolocation reader
│   │   │   │   ├── SessionCodeInput.svelte
│   │   │   │   ├── AttendanceTable.svelte
│   │   │   │   ├── Navbar.svelte
│   │   │   │   └── OfflineBanner.svelte   # Shows when offline
│   │   │   │
│   │   │   ├── stores/               # Svelte reactive stores (state management)
│   │   │   │   ├── auth.ts           # Authentication state
│   │   │   │   ├── offline.ts        # IndexedDB offline queue management
│   │   │   │   └── attendance.ts     # Current session attendance state
│   │   │   │
│   │   │   ├── services/             # API communication layer
│   │   │   │   ├── api.ts            # HTTP client (fetch wrapper)
│   │   │   │   └── sync.ts           # Background sync service worker logic
│   │   │   │
│   │   │   └── utils/                # Helper functions
│   │   │       ├── hmac.ts           # Client-side HMAC helpers
│   │   │       ├── geolocation.ts    # GPS utility functions
│   │   │       └── format.ts         # Date/time formatting
│   │   │
│   │   ├── service-worker.ts         # PWA service worker (offline caching + sync)
│   │   └── app.html                  # HTML shell
│   │
│   ├── static/                       # Static assets
│   │   ├── manifest.json             # PWA manifest file
│   │   └── icons/                    # App icons (192x192, 512x512)
│   │       ├── 192.png
│   │       └── 512.png
│   │
│   ├── svelte.config.js              # SvelteKit configuration
│   ├── vite.config.ts                # Vite + PWA plugin configuration
│   ├── package.json                  # Node dependencies
│   └── .env                          # PUBLIC_API_URL (gitignored)
│
├── database/                         # Database related files
│   ├── schema.sql                    # Full database schema (reference)
│   └── seed.sql                      # Sample/test data
│
├── docs/                             # Documentation
│   ├── proposal.md                   # Full project proposal
│   ├── proposal_simple.md            # Simplified proposal (1st week)
│   ├── deployment-workflow.md        # Deployment guide
│   └── project-structure.md          # This file
│
├── docker-compose.yml                # Local development: PostgreSQL + backend
├── .gitignore
└── README.md                         # Project overview & setup instructions
```

---

## Key Directories & Their CS Concept Mapping

| Directory / File | CS Concept |
|-----------------|------------|
| `backend/shared/cache.py` | Caching & Indexing Algorithm (O(1) lookup) |
| `frontend/src/stores/offline.ts` + `frontend/src/service-worker.ts` | Offline-First Architecture |
| `backend/features/session/` + `backend/core/security.py` | HMAC-based Session Auth |
| `frontend/src/lib/utils/geolocation.ts` + `backend/features/attendance/service.py` | Geolocation Proximity (Haversine) |
| `frontend/src/lib/components/QRScanner.svelte` | Live QR Detection (Liveness) |
| `backend/features/*/model.py` | Database Design & Normalization (3NF) |
| `backend/features/sync/service.py` + `frontend/src/lib/services/sync.ts` | Offline Sync / Eventual Consistency |

---

## Development vs Production Structure

The folder structure is identical in both environments. The differences are in configuration:

| Aspect | Development | Production |
|--------|------------|------------|
| DB | Local PostgreSQL (Docker) | Supabase (cloud) |
| Backend | `uvicorn --reload` | Fly.io (Docker) |
| Frontend | `npm run dev` | Vercel (build + deploy) |
| Env vars | `.env` file | `fly secrets set` / Vercel dashboard |
