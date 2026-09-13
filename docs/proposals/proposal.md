# Project Proposal: QR-Code Based Offline-Capable Attendance System with Anti-Spoofing

> **Note:** Schema design has evolved since this proposal was submitted. See `docs/architecture/migration-strategy.md` for the current target schema (a `course_offerings` table now decouples courses from program/year/schedule, and professor assignments/enrollments reference offerings).

---

## 1. Introduction

### 1.1 Background & Context

Manual attendance checking in classrooms is time-consuming, error-prone, and disrupts lectures. Modern student IDs issued by our campus already contain QR codes encoding student ID numbers, yet this resource remains underutilized. There is an opportunity to build a system that leverages these existing QR codes to automate attendance taking while addressing common problems like network reliability and QR spoofing.

### 1.2 Problem Statement

- Manual attendance takes 5–10 minutes of class time
- Roll call is prone to errors and fraudulent signing
- Students can photograph a classmate's QR code or share session codes to submit attendance remotely
- Internet connectivity on campus is not always stable
- Student data changes yearly (new enrollees, graduating students) and academic structures vary by program (different term counts per year level)

### 1.3 Proposed Solution

A Progressive Web Application (PWA) that:

- Scans the QR code from existing campus student ID cards
- Extracts the student ID number embedded in the QR code and matches it against a student roster in the database
- Validates attendance through multi-layer anti-spoofing: session code, GPS geofencing, live QR detection, face liveness verification, one-scan-per-session enforcement, and an enrollment check
- Enforces an academic hierarchy (**Program → Year Level → Course**) with per-year term structures, enabling multi-program and multi-cohort course sharing (D1–D6)
- Applies a window-based attendance policy engine: present/late windows, duration-expiry respecting scheduled class end, per-session overrides of course defaults (D11–D19)
- Supports a full excuse workflow: professor quick-excuse, professor-initiated with evidence, student-initiated request — all with audit trail and attachment storage (D20–D26)
- Performs admin-enrolled face verification using 3-angle photo embeddings (front/left/right) stored encrypted on the server and pulled by devices on login (D27–D32)
- Provides unified analytics and reporting with cascading filters (Program → Year → Term → Course), heuristic at-risk prediction, and compliance/participation rate metrics (D33–D37)
- Works offline by storing records locally and auto-syncing when connectivity is restored
- Provides dashboards and reports for professors and administrators

---

## 2. Objectives

### 2.1 General Objective

To design and develop a QR-code based attendance system that automates the attendance process, prevents spoofing, and remains functional even without internet connectivity.

### 2.2 Specific Objectives

1. Develop a QR scanning module that decodes student ID numbers from existing campus ID cards
2. Implement a caching and indexing algorithm for efficient student data retrieval (O(1) lookup)
3. Design a multi-layer anti-spoofing mechanism: HMAC session codes, GPS geofencing, live QR detection, face liveness verification, duplicate scan prevention, and enrollment verification
4. Implement offline-first local storage with automatic synchronization when internet is restored
5. Build an admin dashboard for attendance monitoring, reports, and student roster management
6. Model the academic hierarchy (Program → Year Level → Course) with per-year term structures and multi-program course sharing
7. Implement window-based attendance policy: present/late windows, duration expiry respecting scheduled class end, per-session overrides of course defaults
8. Build a full excuse workflow with three initiation paths (professor quick-excuse, professor-initiated with evidence, student-initiated request) and audit trail
9. Implement admin-enrolled face verification using 3-angle photo capture and encrypted embeddings distributed via pull-on-login
10. Provide unified analytics and reporting with cascading filters, heuristic at-risk prediction, and compliance/participation rate metrics
11. Provide CSV-import functionality for student rosters from the registrar

---

## 3. CS Concepts Applied

### 3.1 Caching & Indexing Algorithm

- **Concept**: Hash-map based indexing with LRU (Least Recently Used) cache
- **Application**: When a QR code is scanned, the student ID number is extracted and used as a key into a hash-indexed cache. On cache miss, the database is queried and the result is promoted to the cache. This achieves O(1) average lookup time.
- **Why**: Hundreds of students scan within minutes; slow database queries per scan would introduce lag. The cache is indexed in memory so lookups are near-instantaneous.

### 3.2 Offline-First Architecture

- **Concept**: Local-first data strategy with eventual consistency
- **Application**: Attendance records are written to IndexedDB (browser) immediately. A background sync worker checks connectivity periodically and pushes queued records to the server when online. Conflict resolution uses timestamp-based ordering.
- **Why**: Campus internet is unreliable; attendance should never be blocked by connectivity issues.

### 3.3 HMAC-based Session Authentication

- **Concept**: Hash-based Message Authentication Code (HMAC-SHA256)
- **Application**: When a professor opens a session, the server generates a time-bound HMAC-signed token using a secret key. Students must submit this token along with their QR scan. The server verifies the HMAC signature and expiry before recording attendance.
- **Why**: Prevents unauthorized students from submitting attendance without a valid session code, and ensures codes expire after class.

### 3.4 Geolocation Proximity Algorithm

- **Concept**: Haversine distance formula
- **Application**: The student's device GPS coordinates are checked against the saved classroom coordinates. Attendance is only accepted if the distance is within a configurable radius (e.g., 30 meters).
- **Why**: Ensures the student is physically present in the classroom, preventing remote attendance submissions.

### 3.5 Liveness Verification Protocol (QR + Face Anti-Spoofing)

Liveness verification is the system's core anti-spoofing mechanism. It operates at two levels — the physical ID card and the physical person — and remains functional even when no server is reachable.

#### 3.5.1 QR-Level Liveness (Card Check)

- **Concept**: Computer vision reflection analysis / QR error correction pattern analysis
- **Application**: The QR scanner analyzes reflections, micro-texture, and lighting patterns to distinguish a physical ID card from a screen (photo/screenshot). Libraries like `html5-qrcode` support this via focus and reflection heuristics.
- **Why**: Prevents students from scanning a screenshot of a classmate's ID card.

#### 3.5.2 Face-Level Liveness (Person Check)

- **Concept**: Challenge-response verification using facial landmark tracking (Eye Aspect Ratio, head-pose estimation via Perspective-n-Point)
- **Application**: After a successful QR scan, the camera captures a short live video. The client runs a **fixed challenge sequence** (blink → turn head left → turn head right) using MediaPipe Face Mesh WASM locally. The client tracks face landmarks and returns an evidence transcript (EAR time series + head-pose angles + timing). The server grades the transcript against the expected sequence.
- **Why**: Defeats image/printed-photo attacks (no live blink) and distorted prints (fail 3D pose/motion checks). The **fixed** sequence (blink → left → right) is chosen over random challenges specifically for offline operability — no server round-trip is needed to receive the challenge (D31). Video-replay and screen-recorder attacks are mitigated by the other cross-modal layers (enrolled-face match, geofence, per-session uniqueness), not by challenge unpredictability.

#### 3.5.3 Offline Liveness Protocol (Deferred Validation)

- **Concept**: Asynchronous verification with anti-replay evidence bundling
- **Application**: Each scan produces a signed evidence bundle `{scan_id, nonce, timestamp, session_ref, challenge transcript, landmark series, QR liveness score, GPS, HMAC}`. When offline, bundles are stored locally with status `pending` (D16) and re-validated server-side after sync. The server keeps a nonce registry so replayed bundles are rejected. Expired-window offline scans are rejected with reason `session_expired` (D16).
- **Why**: Standard liveness detection assumes an always-online server; this protocol preserves both liveness layers in an offline-first environment — the project's defining constraint.

#### 3.5.4 Known Limitation — Identical Twins

A live twin passes face-liveness checks by definition. The system mitigates this through cross-modal fusion — enrolled-face match, physical card liveness, GPS presence, and per-session uniqueness — but twin separation is acknowledged as a known limitation per the instructor's guidance (D31): treated as a future assignment, not a solved claim in this system.

#### 3.5.5 Empirical Evaluation (PAD Benchmarking)

- **Concept**: Presentation Attack Detection (PAD) benchmarking per ISO/IEC 30107-3
- **Application**: A self-built attack corpus (screenshot, printed photo, folded/distorted print, screen recording, video replay, twin pair) is run against the pipeline; results are reported using APCER and BPCER (± FAR/FRR).
- **Why**: Provides quantitative evidence for the protocol's defenses instead of qualitative claims.

### 3.6 Database Design & Normalization

- **Concept**: Relational database normalization (3NF)
- **Application**: Tables for Students, Courses, Enrollments, AttendanceRecords, Sessions, and SyncQueue with proper foreign keys and constraints.
- **Why**: Ensures data integrity, avoids redundancy, and supports efficient queries.

### 3.7 Predictive & Prescriptive Attendance Analytics

- **Concept**: Heuristic threshold engine (MVP) with upgrade path to lightweight ML; four-level analytics framework
- **Application**: Historical attendance (including offline-synced records) is aggregated into per-student features — absence rate, consecutive-miss streak, sync-lag pending count, and 4-week trend slope. At-risk prediction starts as **env-configurable heuristic thresholds** (D35): absence_rate > 0.30 → high; > 0.15 → medium; streak ≥ 3 consecutive misses → high; sync-lag pending ≥ 5 → medium; trend slope < −0.05/week → medium. Expected sessions derive from course metadata: `semester_weeks × sessions_per_week`. A daily batch job (nightly) writes scores to `student_risk_scores`; a manual refresh endpoint exists for admins. ML (logistic regression) is a planned upgrade using the identical feature vector. Two rate metrics are displayed everywhere: **Compliance Rate** = present / total (default) and **Participation Rate** = (present + late + excused) / total (toggle). The admin portal merges Reports and Analytics into one "Analytics & Reports" page with cascading filters: Program → Year → Term → Courses (multi) → Date range → Granularity (daily/weekly/monthly), with tabs for Overview, Course Comparison, Trends, At-Risk, and Export. Professor reports add an "All Courses" aggregate tab with the same granularity controls.
- **Why**: Converts raw attendance into actionable intelligence across all four analytics levels — descriptive (what happened), diagnostic (why), predictive (what's next), prescriptive (what to do) — while keeping the initial implementation interpretable and auditable.

### 3.8 Software Engineering Lifecycle

- **Concept**: Agile/Scrum methodology
- **Application**: The project is developed in sprints: requirements gathering, system design, iterative implementation, testing, deployment, and maintenance.
- **Why**: Provides a structured approach to software development with stakeholder feedback loops.

---

## 4. Application Data Flow

### 4.1 Setup Phase (One-Time)

Setup happens in two phases. The rosters and the accounts are separate;
students and professors connect the two by **claiming** their imported record
at registration, using the **official email** as the lookup key.

```
PHASE 1 — Roster seeding (admin)
Registrar provides student roster (CSV)
  └→ Columns: student_id, first_name, middle_name, last_name,
     email, program_code, section, year_level
    └→ Imported into database as `students` rows (no accounts yet)
      └→ Each student_id is the same one encoded in the student's ID card QR
      └→ students.user_id = NULL (unclaimed)
Professors are seeded manually [+Add] or via CSV on the Admin Professor
Management screen
  └→ Columns: first_name, middle_name, last_name,
     email, department
    └→ professors.user_id = NULL (unclaimed)

PHASE 2 — Claim-based registration (same flow for both roles)
Student / Professor registers with email + password
  └→ Role decides which table is looked up (students / professors)
    └→ Look up the official email (must exist & be active, unclaimed)
      └→ Else 409 — contact admin to be added to the roster
        └→ Send OTP to that email (ownership proof, 5-min expiry)
          └→ Verified → create `users` row + link the record in one transaction
            └→ Name, course, section are pulled from the seeded record
Admin — NOT self-registered (never offered on the Register form)
  └→ First admin is seeded at deployment as **Super Admin** (env/seed script)
  └→ Additional admins are created by an existing admin (Admin Users)
```

**Key insight**: The QR code on student IDs already encodes the student ID
number. No QR generation or re-encoding is needed. The CSV provides the
student's name, course, section and official email — the QR provides the
attendance key. **Email is both the registration lookup key and the login
identity**; the student ID is used only as the QR/attendance key and is
**never entered at registration**. The OTP sent to the official email proves
the registrant is the real owner of the seeded record (students claim by
holding their ID, professors claim by holding their school email).

### 4.2 Per-Class Session Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                       PROFESSOR                                  │
│  Logs in → Selects course (locked from My Courses, or           │
│    choose from Dashboard "New Session")                          │
│    → Sets duration (minutes), present window, late window       │
│    → Optional classroom override (blank = course default)       │
│    → Server computes: expires_at = min(now + duration,          │
│        scheduled_end_time) per D12                               │
│    → Server generates HMAC-signed session code + QR payload     │
│      {"v":1,"code":"A7X-9K2M","offering":123,"radius":30,      │
│       "pw":5,"lw":10} per D18                                   │
│    → Professor displays code/QR on projector                    │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                       STUDENT — 5-Step Scan Flow                 │
│                                                                   │
│  Step 1: Session Entry — type code OR scan session QR            │
│    → Verify → fetch session config (windows, expiry, course)     │
│                                                                   │
│  Step 2: ID Scan — scan student-ID QR → resolve student number  │
│    → fetch student record, enrollment check, duplicate check     │
│                                                                   │
│  Step 3: Location Check — GPS geofence (Haversine vs radius)    │
│    → runs in parallel with steps 2–3                             │
│                                                                   │
│  Step 4: Face Check — fixed challenge: blink → turn left →      │
│    turn right (MediaPipe Face Mesh WASM client-side)             │
│    → embedding comparison vs enrolled embedding (cosine ≥ 0.7)  │
│    → offline: evidence saved, verified after sync                │
│                                                                   │
│  Step 5: Result — PRESENT / LATE / PENDING (offline) / REJECTED │
│    → status determined by present/late windows (D13)             │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                     SERVER VALIDATION                            │
│                                                                   │
│  1. Session Validity ── HMAC check, not expired (D12)           │
│  2. Enrollment Check ── student enrolled in course?              │
│  3. Duplicate Scan  ── one scan per session enforced             │
│  4. GPS Geofence    ── within classroom radius (D17)            │
│  5. Face Match      ── cosine similarity ≥ threshold (D27)      │
│  6. Window Timing   ── present_window / late_window (D13)       │
│                                                                   │
│  ALL CHECKS → write attendance record with status                │
│  (present / late / absent when session expires / pending offline)│
└─────────────────────────────────────────────────────────────────┘
```

### 4.3 Offline Scenario

```
┌─────────────────────────────────────────────────────────────────┐
│                     INTERNET DOWN                                │
│                                                                   │
│  Student completes 5-step scan flow (session entry, ID scan,     │
│    GPS check, face challenge)                                    │
│    → Connection fails → Evidence bundle saved to IndexedDB       │
│    → Status: "Pending" (face evidence captured, D16)             │
│    → Student sees: "Attendance saved locally"                     │
│                                                                   │
│  ─── When internet returns ───                                   │
│                                                                   │
│  Service Worker detects connectivity                             │
│    → Pushes pending evidence bundles to server                   │
│    → Server re-validates each:                                   │
│       - scanned_at vs session window (D16)                       │
│       - HMAC, GPS, face match score, uniqueness, enrollment      │
│    → Within window → marked as "Synced" (present/late by timing) │
│    → Window expired → "Rejected" with reason "session_expired"   │
│    → Invalid evidence → rejected with specific reason             │
│    → Student notified of outcome                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.4 Anti-Spoofing Layer Summary

| Layer                | What It Prevents                                         | CS Concept                             |
| -------------------- | -------------------------------------------------------- | -------------------------------------- |
| Session Code         | Outsiders submitting attendance                          | HMAC-SHA256                            |
| GPS Geofencing       | Remote/fake submissions                                  | Haversine Algorithm                    |
| Live QR Detection    | Screenshot of a classmate's ID                           | Liveness Analysis                                |
| Face Liveness        | Photo, video-replay, screen-recorder, distortion attacks | Challenge-Response + Landmark Tracking |
| Offline Evidence     | Replayed/forged scans after sync                         | Nonce + HMAC Evidence Bundles          |
| One Scan Per Session | Same ID used multiple times                              | Database Constraint                    |
| Enrollment Check     | Non-enrolled students marking attendance                 | Relational FK Constraint               |
| Window Timing        | Scans outside allowed timeframes                         | Present/Late window engine (D13)       |

**Attendance statuses** (D15): `present`, `late`, `absent`, `excused`, `pending`, `rejected`.
Rejection reasons: `duplicate`, `outside_geofence`, `liveness_failed`, `face_mismatch`, `not_enrolled`, `session_expired`.

---

## 5. Features

| #   | Feature                      | Description                                                                           |
| --- | ---------------------------- | ------------------------------------------------------------------------------------- |
| 1   | QR Code Scanning             | Decodes student ID number from campus ID card QR using device camera                  |
| 2   | HMAC Session Codes           | Professor generates time-limited session with present/late windows                    |
| 3   | GPS Geofencing               | Validates student is within classroom perimeter                                       |
| 4   | Live QR Detection            | Distinguishes physical card from screen (screenshot prevention)                       |
| 5   | Face Liveness Challenge      | Fixed blink→left→right challenges verified against face landmarks                     |
| 6   | Offline Liveness Protocol    | Evidence bundles queued and anti-replay validated after sync                          |
| 7   | One Scan Per Session         | Prevents duplicate submissions                                                        |
| 8   | Offline Mode                 | Attendance stored locally, auto-synced when online                                    |
| 9   | Academic Structure           | Program → Year Level → Course hierarchy with term structures (D1–D6)                  |
| 10  | Window-Based Attendance      | Present/late windows, duration expiry, per-session overrides (D11–D19)                |
| 11  | Excuse Workflow              | 3 initiation paths with audit trail and evidence attachments (D20–D26)                |
| 12  | Face Enrollment              | Admin-enrolled 3-photo embeddings (front/left/right), pull-on-login (D27–D32)         |
| 13  | Student Roster Management    | CSV import (incl. official email), add/edit/remove students                           |
| 14  | Analytics & Reports          | Unified page: Overview, Course Comparison, Trends, At-Risk, Export (D33–D37)          |
| 15  | At-Risk Prediction           | Heuristic thresholds (daily batch), upgradeable to ML (D35)                           |
| 16  | Reports Export               | Download attendance reports as CSV/PDF, or print them                                 |
| 17  | Account Security             | Cloudflare Turnstile, OTP, optional MFA, strong-password policy, admin reset, lockout |
| 18  | Data Table Controls          | Sortable columns, category + date-range filters, search, print                        |
| 19  | User Provisioning & Claiming | Students/professors self-register by claiming admin-seeded email                      |
| 20  | Encrypted Backups            | Full DB dump AES-256-GCM encrypted, retention 30D daily + 12M monthly (D39)           |
| 21  | Academic Structure Updates   | Admin bulk-edit programs/year levels replacing year-level promotion (D38)             |

---

## 6. System Architecture

### 6.1 Tech Stack

| Layer           | Technology                                         | Purpose                                                         |
| --------------- | -------------------------------------------------- | --------------------------------------------------------------- |
| Frontend        | SvelteKit + PWA (Service Workers)                  | Cross-platform UI, offline support, camera/GPS access           |
| Backend         | Python FastAPI                                     | REST API server, async request handling                         |
| Database        | PostgreSQL (server) + IndexedDB (client)           | Persistent storage + local cache                                |
| QR Library      | html5-qrcode                                       | QR decoding and live detection in browser                       |
| Face Tracking   | MediaPipe Face Mesh / face-api.js                  | Landmark tracking, blink & head-pose challenges                 |
| Face Embeddings | face-api.js (ResNet-34-like, pretrained)           | 128-d face embeddings for enrolled-face matching                |
| Charts          | Chart.js (+ date adapter)                          | Analytics dashboards wrapped in reusable Svelte component (D41) |
| Analytics       | Heuristic thresholds (MVP), scikit-learn (upgrade) | At-risk scoring, compliance/participation metrics               |
| Auth / Sessions | HMAC-SHA256                                        | Session code generation & verification                          |
| Encryption      | AES-256-GCM (backup), pgcrypto (embeddings)        | Backup encryption, face embedding encryption at rest            |
| Hosting         | Docker + cloud VPS                                 | Deployment and scaling                                          |

### 6.2 High-Level Architecture

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  Student Device   │     │ Professor Device │     │     Server       │
│  (PWA - Browser)  │     │  (PWA - Browser) │     │  (FastAPI + DB)  │
│                   │     │                  │     │                  │
│  ┌─────────────┐  │     │ ┌──────────────┐ │     │ ┌──────────────┐ │
│  │ QR Scanner   │  │     │ │ Open Session │ │     │ │ HMAC Verify  │ │
│  │ GPS Reader   │  │     │ │ View Reports │ │     │ │ Liveness Ver │ │
│  │ Face Check   │  │     │ │ Manage Course│ │     │ │ GPS Verify   │ │
│  │ Face Cache   │  │     │ │ Excuse Actions│ │     │ │ Window Timer │ │
│  │ IndexedDB   │  │     │ └──────────────┘ │     │ │ DB Lookup    │ │
│  │ Offline Queue│  │     └──────────────────┘     │ │ Cache Layer  │ │
│  └─────────────┘  │                               │ │ Sync Handler │ │
└──────────────────┘                               │ │ Risk Batch   │ │
        │                                           │ │ Backup Job   │ │
        │                                           │ └──────────────┘ │
        └────────────── HTTPS ──────────────────────┘
```

**Key subsystems added (D1–D40)**:

- **Academic Structure Service**: Programs, Year Levels, Courses with term structures
- **Session Policy Engine**: Duration, present/late windows, expiry calculation
- **Excuse Workflow**: 3 initiation paths, evidence storage, state machine
- **Face Embedding Pipeline**: Admin 3-photo capture → server 128-d embedding → encrypted storage → pull-on-login
- **Analytics Pipeline**: Daily batch risk scoring, unified Analytics & Reports page
- **Backup Pipeline**: pg_dump → encrypt (AES-256-GCM) → upload → log → retention prune

### 6.3 Database Schema

```
Users
  - id (PK)
  - role (super_admin / admin / professor / student)
  - username (unique)
  - email (unique — login identity)
  - password_hash (Argon2id)
  - security_question_hash   (for password reset)
  - security_answer_hash     (for password reset)
  - mfa_enabled              (optional two-factor auth)
  - mfa_secret               (authenticator-app secret, encrypted)
  - failed_login_attempts    (5 → temporary lockout)
  - is_active                (deactivate instead of delete)
  - created_at
  - last_login

Students
  - id (PK)
  - user_id (FK → users, nullable, unique — set when student claims record)
  - student_id (unique — same value encoded in ID card QR)
  - email (unique — official email, registration lookup key)
  - first_name, middle_name, last_name
  - year_level_id (FK → year_levels)
  - section (VARCHAR, retained per D2 — changes only via admin action)
  - is_active
  - face_embedding (BYTEA, nullable — encrypted JSON blob: {"mean":[128f],"angles":{"front":[...],"left":[...],"right":[...]}} per D28/D43)
  - face_enrolled_at (TIMESTAMPTZ, nullable)
  - face_embedding_version (INT, default 0 — bumped on every write)
  - created_at, updated_at
  -- legacy `course` string column dropped after backfill to FK-based courses

Professors
  - id (PK)
  - user_id (FK → users, nullable, unique — set when professor claims record)
  - email (unique — official email, registration lookup key)
  - first_name, middle_name, last_name
  - department
  - is_active
  - created_at, updated_at

OtpCodes
  - id (PK)
  - email (index — lookup key; user may not exist yet during claim)
  - purpose (claim / forgot_password)
  - otp_hash (Argon2id-hashed 6-digit code, never stored plaintext)
  - expires_at (5-minute TTL)
  - consumed_at (null until used — single-use)
  - user_id (FK → users, nullable — set when code targets existing account)
  - created_at

Programs (NEW — D1)
  - id (PK)
  - code (UNIQUE — e.g. "BSCS", "BSIT")
  - name (e.g. "Bachelor of Science in Computer Science")
  - description
  - total_years (e.g. 4)
  - is_active
  - created_at, updated_at

YearLevels (NEW — D1/D3)
  - id (PK)
  - program_id (FK → programs, CASCADE)
  - year_number (INT — 1, 2, 3, 4)
  - label (e.g. "1st Year", "2nd Year")
  - term_structure (JSONB — e.g. {"terms":[{"code":"1st_sem","label":"1st Semester"},{"code":"2nd_sem","label":"2nd Semester"}]})
  - sort_order
  - UNIQUE(program_id, year_number)

Courses (REDESIGNED — D1/D2/D4)
  - id (PK)
  - program_id (FK → programs, RESTRICT)
  - year_level_id (FK → year_levels, RESTRICT)
  - course_code, course_name
  - units (INT)
  - sessions_per_week (INT)
  - session_duration_hours (NUMERIC(3,1))
  - semester_weeks (INT)
  - schedule_days (VARCHAR — e.g. "MWF")
  - schedule_start_time (TIME)
  - schedule_end_time (TIME)
  - classroom_name
  - classroom_lat, classroom_lng (for GPS geofencing)
  - default_present_window_minutes (INT, default 5 — D14)
  - default_late_window_minutes (INT, default 10 — D14)
  - is_active
  - created_at, updated_at
  -- A course can be taken by multiple programs/year levels (D6)

CourseProfessors (NEW — D7/D8/D9, FK updated per D45)
  - offering_id (FK → course_offerings, CASCADE)
  - professor_id (FK → professors, CASCADE)
  - is_primary (BOOLEAN)
  - effective_from (DATE)
  - effective_to (DATE, nullable — null = ongoing)
  - semester (VARCHAR — e.g. "1st_sem")
  - assigned_by (FK → users)
  - assigned_at (TIMESTAMPTZ)
  - PK(offering_id, professor_id, effective_from)
  -- Overlapping effective ranges for same (offering, professor) rejected at service layer

Enrollments (REDESIGNED — D5, course_id dropped per Step 5)
  - id (PK)
  - student_id (FK → students)
  - offering_id (FK → course_offerings)
  - academic_year
  - semester (VARCHAR — validated against year_level.term_structure)

Sessions (EXTENDED — D11/D12/D13/D17, course_id dropped per Step 6)
  - id (PK)
  - offering_id (FK → course_offerings)
  - professor_id (FK → professors)
  - session_code (HMAC token)
  - duration_minutes (INT)
  - present_window_minutes (INT)
  - late_window_minutes (INT)
  -- CHECK (present_window_minutes + late_window_minutes <= duration_minutes)
  - scheduled_start_time (TIMESTAMPTZ — copied from course schedule at open)
  - scheduled_end_time (TIMESTAMPTZ — copied from course schedule at open)
  - expires_at (TIMESTAMPTZ — LEAST(created_at + duration_minutes, scheduled_end_time) per D12)
  - classroom_name (NULL — session-level override, D17)
  - classroom_lat (NULL), classroom_lng (NULL)
  - created_at

AttendanceRecords (EXTENDED — D15/D16)
  - id (PK)
  - student_id (FK → students)
  - session_id (FK → sessions)
  - timestamp
  - gps_lat, gps_lng (recorded at scan time)
  - validation_status (present / late / absent / excused / pending / rejected — D15)
  - rejection_reason (duplicate / outside_geofence / liveness_failed / face_mismatch / not_enrolled / session_expired — D16)
  - sync_status (synced / pending / failed)
  - liveness_evidence (JSONB)
  - face_match_score (NUMERIC(5,4))
  - scanned_via ('qr_camera' | 'manual_code')
  - original_status (VARCHAR, nullable — preserved when excused, D22)
  - excuse_reason (TEXT, nullable)
  - excused_by (FK → users, nullable)
  - excused_at (TIMESTAMPTZ, nullable)
  - excuse_type ('quick' | 'prof_with_evidence' | 'request_approved', nullable)
  - excuse_request_id (FK, nullable)
  - created_at

ExcuseRequests (NEW — D20/D21)
  - id (PK)
  - student_id (FK → students)
  - session_id (FK → sessions)
  - initiated_by ('professor' | 'student')
  - initiated_via ('quick' | 'prof_with_evidence' | 'request')
  - reason (TEXT)
  - attachment_urls (JSONB — S3-compatible storage references, D24)
  - status ('pending' | 'approved' | 'rejected', default pending)
  - requested_at (TIMESTAMPTZ)
  - reviewed_by (FK → users, nullable)
  - reviewed_at (TIMESTAMPTZ, nullable)
  - review_notes (TEXT, nullable)

StudentRiskScores (NEW — D35)
  - id (PK)
  - student_id (FK → students)
  - offering_id (FK → course_offerings)
  - semester (VARCHAR)
  - risk_probability (NUMERIC(5,4))
  - risk_level ('low' | 'medium' | 'high')
  - features (JSONB — absence_rate, max_streak, sync_lag, trend_slope)
  - computed_at (TIMESTAMPTZ)
  - UNIQUE(student_id, offering_id, semester, computed_at::date)

BackupLog (NEW — D39)
  - id (PK)
  - filename (VARCHAR)
  - kind ('full' | 'analytics')
  - size_bytes (BIGINT)
  - sha256 (VARCHAR)
  - storage_backend ('local' | 's3')
  - encryption_key_version (INT)
  - started_at (TIMESTAMPTZ)
  - finished_at (TIMESTAMPTZ)
  - status (VARCHAR)
  - error (TEXT, nullable)

SyncQueue
  - id (PK)
  - record_data (JSON — serialized attendance record)
  - status (pending / synced / failed)
  - retry_count
  - created_at
```

### 6.4 Account Security & Password Policy

To protect accounts and attendance data, the system enforces the following
policies across every role:

- **Strong password policy**: minimum **8 characters** with at least **1
  uppercase, 1 lowercase, 1 number and 1 symbol** (alphanumeric + symbol).
  Enforced at registration, on password change, and on password reset.
- **Password hashing**: all passwords (and OTP codes) are hashed with
  **Argon2id**; plaintext is never stored or logged.
- **Cloudflare Turnstile** (free, invisible captcha) at login and on the first
  step of password recovery to deter automated attacks.
- **Forgot Password flow** (4 steps): email + captcha → **security question**
  (max **3 attempts** before abort/lock) → **OTP** (6-digit, expires in 5
  min; stored Argon2id-hashed in the `otp_codes` table, single-use) → **enter
  new password + confirm new password**.
- **MFA / OTP**: optional two-factor authentication via an authenticator app
  (TOTP secret + backup codes). When enabled, login requires a second OTP step.
- **Multiple-attempt lockout**: accounts are temporarily locked after **5
  failed login attempts**.
- **Admin password reset**: an admin can reset any user's password — a
  temporary password is set and the user is prompted to change it on next
  login.
- **Deactivate instead of delete**: accounts/records are soft-deleted via
  `is_active`; permanent deletion only from the Archive screen.
- **Read-only profiles (D32)**: student and professor identity fields are
  admin-managed; users may only change password and security settings.
- **Claim-based registration**: students and professors self-register with
  email + password. The email must match an **admin-seeded record** (student
  roster CSV / professor management) — the role decides which table is
  looked up — and an **OTP sent to that email** proves ownership before the
  account is linked. Name, course and section are pulled from the seeded
  record; nothing is typed at registration. **Admin accounts are never
  self-registered** — the first admin is seeded at deployment, and
  additional admins are created by an existing admin via the Admin Users
  screen.

### 6.5 Data Tables

Every data table (history, attendance lists, session history, student /
professor / course management, overviews, reports, audit logs, archive)
shares the same controls:

- **Sortable column headers** — click a header to toggle ascending/
  descending order (▲/▼ indicator on the active column)
- **Category filters** — dropdowns (Course, Status, Section, Year, Action…)
- **Date-range filter** — From/To pickers for historical data
- **Search** — free-text search field
- **Print** — print the current filtered view; **CSV/PDF export** on
  report/management screens

---

## 7. Methodology (Agile/Scrum)

The project will follow an Agile approach with 2-week sprints:

| Sprint    | Focus                                                                                                |
| --------- | ---------------------------------------------------------------------------------------------------- |
| Sprint 1  | Requirements gathering, database design, wireframing                                                 |
| Sprint 2  | Backend API setup, student CRUD, CSV import, academic hierarchy (Program/YearLevel/Course)           |
| Sprint 3  | QR scanning module, caching layer, basic attendance recording                                        |
| Sprint 4  | HMAC session authentication, GPS geofencing, window-based attendance policy                          |
| Sprint 5  | QR liveness detection, face enrollment (3-photo admin capture), duplicate prevention                 |
| Sprint 6  | Liveness protocol: challenge-response, evidence bundles, nonce registry                              |
| Sprint 7  | Offline storage, background sync with deferred liveness, session-expired rejection                   |
| Sprint 8  | Excuse workflow (3 paths, bulk excuse-all, evidence attachments)                                     |
| Sprint 9  | Analytics: heuristic at-risk batch, unified Analytics & Reports page, compliance/participation rates |
| Sprint 10 | Encrypted backups, academic structure updates, admin system settings                                 |
| Sprint 11 | Testing, bug fixes, deployment                                                                       |
| Sprint 12 | User acceptance testing, documentation                                                               |

---

## 8. Scope & Limitations

### In Scope

- QR scanning from existing campus ID cards (no QR generation needed)
- HMAC-based session code anti-spoofing
- GPS geofencing for classroom validation
- Live QR detection (physical card vs screen)
- Face liveness verification (challenge-response against image, video-replay, screen-recorder, and distortion attacks)
- Offline liveness protocol with nonce anti-replay deferred validation
- Admin-enrolled face verification (3-photo capture, 128-d encrypted embeddings, pull-on-login)
- Academic hierarchy: Programs → Year Levels (with term structures) → Courses (multi-program sharing)
- Window-based attendance policy: present/late windows, duration expiry, per-session overrides
- Excuse workflow: professor quick-excuse, professor-initiated with evidence, student-initiated request (3 paths)
- Unified analytics and reports: Overview, Course Comparison, Trends, At-Risk, Export with cascading filters
- Heuristic at-risk prediction (daily batch, env-configurable thresholds)
- Encrypted full-database backups (AES-256-GCM) with retention policy
- Predictive at-risk analytics and prescriptive recommendations
- One-scan-per-session enforcement
- Offline attendance storage with auto-sync
- CSV-based student roster import
- Attendance dashboard and report export

### Out of Scope (Future Work)

- Facial recognition as a standalone identity replacement (this system uses face liveness + enrolled-face match only as additional anti-spoofing layers)
- Identical-twin separation (documented limitation — solvable only with cross-modal biometrics)
- Integration with school's existing LMS or registrar API
- Push notification system
- Biometric authentication (fingerprint, iris)
- Mobile native apps (iOS/Android)
- Real-time QR code generation (dynamic QR)

---

## 9. Timeline

| Phase                  | Duration     | Deliverable                                                          |
| ---------------------- | ------------ | -------------------------------------------------------------------- |
| Planning & Design      | 2 weeks      | SRS document, system design, UI mockups                              |
| Core Development       | 4 weeks      | Backend API + frontend with QR scan, sessions, GPS                   |
| Liveness Protocol      | 3 weeks      | Face challenges, evidence bundles, nonce registry                    |
| Analytics & Dashboards | 2 weeks      | Aggregation, at-risk forecasting, prescriptive rules, dashboards     |
| Evaluation & Testing   | 3 weeks      | Attack corpus + APCER/BPCER, unit/integration tests, UAT, deployment |
| **Total**              | **14 weeks** | Fully functional attendance system                                   |

---

## 10. Team Roles (if applicable)

| Role               | Responsibilities                                                 |
| ------------------ | ---------------------------------------------------------------- |
| Project Manager    | Sprint planning, progress tracking, documentation                |
| Backend Developer  | FastAPI, database, caching, HMAC, sync logic                     |
| Frontend Developer | SvelteKit PWA, QR scanning, GPS, offline storage, live detection |
| QA Tester          | Test cases, bug tracking, UAT coordination                       |

---

## 11. Summary

This project proposes a QR-code based attendance system that eliminates manual roll call, prevents spoofing through multiple verification layers (session code, GPS, QR liveness, face liveness, offline evidence anti-replay, duplicate prevention), and works reliably even with intermittent internet connectivity. The system leverages existing student ID cards without requiring any new QR generation, extends liveness verification to offline environments via a deferred-validation protocol, and enforces a structured academic hierarchy (Program → Year Level → Course) with per-year term structures. Attendance is governed by a window-based policy engine (present/late windows, duration expiry) and a full excuse workflow with three initiation paths and audit trail. Face enrollment is admin-driven (3-angle photo capture, encrypted embeddings) with pull-on-login distribution. Analytics and reporting are unified into a single page with cascading filters, heuristic at-risk prediction, and compliance/participation rate metrics. The system is built as a cross-platform PWA using Python (FastAPI) and SvelteKit, with encrypted backups and academic structure management replacing year-level promotion.

---

_Prepared for Software Engineering 1_
