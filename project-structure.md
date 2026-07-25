# Project Folder Structure — QR Attendance System

```
attendance-system/
│
├── backend/                          # FastAPI Python backend
│   ├── app/
│   │   ├── api/                      # Route handlers (endpoints)
│   │   │   ├── __init__.py
│   │   │   ├── auth.py               # Login, registration, token management
│   │   │   ├── students.py           # CRUD operations for students
│   │   │   ├── courses.py            # CRUD operations for courses
│   │   │   ├── attendance.py         # Record and query attendance records
│   │   │   └── sessions.py           # HMAC session code generation & validation
│   │   │
│   │   ├── core/                     # Core configuration & utilities
│   │   │   ├── __init__.py
│   │   │   ├── config.py             # App settings, environment variables
│   │   │   ├── security.py           # HMAC hashing, password hashing
│   │   │   └── database.py           # Database connection & session management
│   │   │
│   │   ├── models/                   # SQLAlchemy ORM models (database tables)
│   │   │   ├── __init__.py
│   │   │   ├── student.py
│   │   │   ├── course.py
│   │   │   ├── enrollment.py
│   │   │   ├── session.py
│   │   │   └── attendance_record.py
│   │   │
│   │   ├── schemas/                  # Pydantic schemas (request/response validation)
│   │   │   ├── __init__.py
│   │   │   ├── student.py
│   │   │   ├── attendance.py
│   │   │   └── session.py
│   │   │
│   │   ├── services/                 # Business logic layer
│   │   │   ├── __init__.py
│   │   │   ├── student_service.py    # Student lookup, roster management
│   │   │   ├── attendance_service.py # Attendance recording & validation
│   │   │   ├── cache_service.py      # LRU caching / indexing algorithm (O(1) lookup)
│   │   │   └── sync_service.py       # Offline sync processing
│   │   │
│   │   └── main.py                   # FastAPI application entry point
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
| `backend/app/services/cache_service.py` | Caching & Indexing Algorithm (O(1) lookup) |
| `frontend/src/stores/offline.ts` + `frontend/src/service-worker.ts` | Offline-First Architecture |
| `backend/app/api/sessions.py` + `backend/app/core/security.py` | HMAC-based Session Auth |
| `frontend/src/lib/utils/geolocation.ts` + `backend/app/services/attendance_service.py` | Geolocation Proximity (Haversine) |
| `frontend/src/lib/components/QRScanner.svelte` | Live QR Detection (Liveness) |
| `backend/app/models/` | Database Design & Normalization (3NF) |
| `backend/app/services/sync_service.py` + `frontend/src/lib/services/sync.ts` | Offline Sync / Eventual Consistency |

---

## Development vs Production Structure

The folder structure is identical in both environments. The differences are in configuration:

| Aspect | Development | Production |
|--------|------------|------------|
| DB | Local PostgreSQL (Docker) | Supabase (cloud) |
| Backend | `uvicorn --reload` | Fly.io (Docker) |
| Frontend | `npm run dev` | Vercel (build + deploy) |
| Env vars | `.env` file | `fly secrets set` / Vercel dashboard |
