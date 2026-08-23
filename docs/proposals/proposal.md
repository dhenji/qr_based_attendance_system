# Project Proposal: QR-Code Based Offline-Capable Attendance System with Anti-Spoofing

---

## 1. Introduction

### 1.1 Background & Context

Manual attendance checking in classrooms is time-consuming, error-prone, and disrupts lectures. Modern student IDs issued by our campus already contain QR codes encoding student ID numbers, yet this resource remains underutilized. There is an opportunity to build a system that leverages these existing QR codes to automate attendance taking while addressing common problems like network reliability and QR spoofing.

### 1.2 Problem Statement

- Manual attendance takes 5–10 minutes of class time
- Roll call is prone to errors and fraudulent signing
- Students can photograph a classmate's QR code or share session codes to submit attendance remotely
- Internet connectivity on campus is not always stable
- Student data changes yearly (new enrollees, graduating students)

### 1.3 Proposed Solution

A Progressive Web Application (PWA) that:

- Scans the QR code from existing campus student ID cards
- Extracts the student ID number embedded in the QR code and matches it against a student roster in the database
- Validates attendance through multi-layer anti-spoofing: session code, GPS geofencing, live QR detection, face liveness verification, one-scan-per-session enforcement, and an enrollment check
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
6. Design an auto-advancement feature that updates student year levels at the end of each academic year
7. Provide CSV-import functionality for student rosters from the registrar

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
- **Application**: After a successful QR scan, the camera captures a short live video. The server issues one or more random challenges (blink, turn head left/right); the client tracks face landmarks (MediaPipe Face Mesh) and returns an evidence transcript (EAR time series + head-pose angles + timing).
- **Why**: Defeats image/printed-photo attacks (no live blink), screen-recorder and video-replay attacks (the attacker cannot answer an unknown random challenge), and distorted prints (fail 3D pose/motion checks).

#### 3.5.3 Offline Liveness Protocol (Deferred Validation)

- **Concept**: Asynchronous verification with anti-replay evidence bundling
- **Application**: Each scan produces a signed evidence bundle `{scan_id, nonce, timestamp, session_ref, challenge transcript, landmark series, QR liveness score, GPS, HMAC}`. When offline, bundles are stored locally with status `pending-liveness` and re-validated server-side after sync. The server keeps a nonce registry so replayed bundles are rejected.
- **Why**: Standard liveness detection assumes an always-online server; this protocol preserves both liveness layers in an offline-first environment — the project's defining constraint.

#### 3.5.4 Risk-Fusion Scoring

- **Concept**: Weighted decision-level fusion of independent verification layers
- **Application**: Each layer (QR liveness, face challenges, enrolled-face match, GPS proximity, uniqueness) produces a confidence score. A weighted scorer computes a composite risk score and maps it to a decision band: `accept` / `flag-for-review` / `reject`, in O(1) per scan.
- **Why**: A hard pass/fail cascade is brittle; confidence fusion tolerates borderline cases and routes them to manual review instead of silently rejecting.

#### 3.5.5 Known Limitation — Identical Twins

A live twin passes face-liveness checks by definition. The system mitigates this through cross-modal fusion — enrolled-face match, physical card liveness, GPS presence, and per-session uniqueness — but twin separation is an open research problem and is documented as a limitation rather than a solved claim.

#### 3.5.6 Empirical Evaluation (PAD Benchmarking)

- **Concept**: Presentation Attack Detection (PAD) benchmarking per ISO/IEC 30107-3
- **Application**: A self-built attack corpus (screenshot, printed photo, folded/distorted print, screen recording, video replay, twin pair) is run against the pipeline; results are reported using APCER and BPCER (± FAR/FRR).
- **Why**: Provides quantitative evidence for the protocol's defenses instead of qualitative claims.

### 3.6 Database Design & Normalization

- **Concept**: Relational database normalization (3NF)
- **Application**: Tables for Students, Courses, Enrollments, AttendanceRecords, Sessions, and SyncQueue with proper foreign keys and constraints.
- **Why**: Ensures data integrity, avoids redundancy, and supports efficient queries.

### 3.7 Predictive & Prescriptive Attendance Analytics

- **Concept**: Applied machine learning (time-series forecasting) + threshold rule engine
- **Application**: Historical attendance (including offline-synced records) is aggregated into per-student features — scan-streak gaps, per-session absence patterns, sync-lag corrections. A lightweight interpretable model (e.g., logistic regression / gradient boosting) predicts at-risk students for upcoming sessions; a prescriptive rule engine converts predictions into actions (professor alerts, student reminders) with effectiveness tracking.
- **Why**: Converts raw attendance into actionable intelligence across all four analytics levels — descriptive (what happened), diagnostic (why), predictive (what's next), prescriptive (what to do).

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
     email, course, section, year_level
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
│  Logs in → Selects course → Clicks "Open Session"                │
│    → Server generates HMAC-signed session code (valid ~2 hrs)    │
│    → Professor displays code on projector / whiteboard           │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                       STUDENT                                    │
│  Opens PWA → Enters session code → Clicks "Scan QR"              │
│    → Camera scans QR on own physical ID card                     │
│    → System extracts student_id from QR                          │
│    → Face challenge: blink / turn head (live video)              │
│    → Device also grabs current GPS coordinates                   │
│    → Sends evidence bundle: { student_id, session_code, gps,     │
│                               challenge transcript, nonce }      │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                     SERVER VALIDATION                            │
│                                                                   │
│  1. HMAC Check  ── Is session_code valid and not expired?        │
│  2. GPS Check   ── Is student within classroom geofence?         │
│  3. QR Liveness ── Was QR scanned from a physical card?          │
│  4. Face Liveness─ Were challenges answered & nonce fresh?       │
│  5. Uniqueness  ── Has this student already scanned?             │
│  6. Enrollment  ── Is student enrolled in this course?           │
│                                                                   │
│  ALL SCORES → Risk fusion → accept / flag-for-review / reject    │
└─────────────────────────────────────────────────────────────────┘
```

### 4.3 Offline Scenario

```
┌─────────────────────────────────────────────────────────────────┐
│                     INTERNET DOWN                                │
│                                                                   │
│  Student scans QR + answers face challenge                       │
│    → Connection fails → Evidence bundle saved to IndexedDB       │
│    → Status: "Pending Liveness" (face evidence captured)         │
│    → Student sees: "Attendance saved locally"                     │
│                                                                   │
│  ─── When internet returns ───                                   │
│                                                                   │
│  Service Worker detects connectivity                             │
│    → Pushes pending evidence bundles to server                   │
│    → Server re-validates each (HMAC, GPS, QR liveness,           │
│       face evidence + nonce anti-replay, uniqueness, enrollment) │
│    → Valid ones → marked as "Synced"                             │
│    → Borderline ones → "Flagged for review"                     │
│    → Invalid ones → rejected + student notified                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.4 Anti-Spoofing Layer Summary

| Layer                | What It Prevents                | CS Concept                   |
| -------------------- | ------------------------------- | ---------------------------- |
| Session Code         | Outsiders submitting attendance | HMAC-SHA256                  |
| GPS Geofencing       | Remote/fake submissions         | Haversine Algorithm          |
| Live QR Detection    | Screenshot of a classmate's ID  | Reflection/Liveness Analysis |
| Face Liveness        | Photo, video-replay, screen-recorder, distortion attacks | Challenge-Response + Landmark Tracking |
| Offline Evidence     | Replayed/forged scans after sync | Nonce + HMAC Evidence Bundles |
| One Scan Per Session | Same ID used multiple times     | Database Constraint          |
| Enrollment Check     | Non-enrolled students marking attendance | Relational FK Constraint     |

---

## 5. Features

| #   | Feature                     | Description                                                          |
| --- | --------------------------- | -------------------------------------------------------------------- |
| 1   | QR Code Scanning            | Decodes student ID number from campus ID card QR using device camera |
| 2   | HMAC Session Codes          | Professor generates time-limited session; required for attendance    |
| 3   | GPS Geofencing              | Validates student is within classroom perimeter                      |
| 4   | Live QR Detection           | Distinguishes physical card from screen (screenshot prevention)      |
| 5   | Face Liveness Challenge     | Random blink/head-turn challenges verified against face landmarks     |
| 6   | Offline Liveness Protocol   | Evidence bundles queued and anti-replay validated after sync          |
| 7   | One Scan Per Session        | Prevents duplicate submissions                                       |
| 8   | Offline Mode                | Attendance stored locally, auto-synced when online                   |
| 9   | Student Roster Management   | CSV import (incl. official email), add/edit/remove students        |
| 10  | Year-Level Auto-Advancement | Batch-updates student year levels at academic year end               |
| 11  | Attendance Dashboard        | Real-time view of attendance per session, per course, per student    |
| 12  | Predictive Analytics        | At-risk student forecasting from attendance patterns                 |
| 13  | Prescriptive Analytics      | Recommended actions (alerts/reminders) from predictive output        |
| 14  | Reports Export              | Download attendance reports as CSV/PDF, or print them            |
| 15  | Account Security            | Cloudflare Turnstile, OTP, optional MFA, strong-password policy (bcrypt), admin reset, lockout |
| 16  | Data Table Controls         | Sortable columns, category + date-range filters, search, print on all data tables |
| 17  | User Provisioning & Claiming | Students/professors self-register by claiming their admin-seeded official email (OTP-verified); admins seeded at deploy / created by admins |

---

## 6. System Architecture

### 6.1 Tech Stack

| Layer           | Technology                               | Purpose                                               |
| --------------- | ---------------------------------------- | ----------------------------------------------------- |
| Frontend        | SvelteKit + PWA (Service Workers) | Cross-platform UI, offline support, camera/GPS access |
| Backend         | Python FastAPI                           | REST API server, async request handling               |
| Database        | PostgreSQL (server) + IndexedDB (client) | Persistent storage + local cache                      |
| QR Library      | html5-qrcode                             | QR decoding and live detection in browser             |
| Face Tracking   | MediaPipe Face Mesh / face-api.js        | Landmark tracking, blink & head-pose challenges       |
| Analytics       | pandas + scikit-learn                    | Aggregation, at-risk forecasting, rule engine         |
| Auth / Sessions | HMAC-SHA256                              | Session code generation & verification                |
| Hosting         | Docker + cloud VPS                       | Deployment and scaling                                |

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
│  │ IndexedDB   │  │     │ └──────────────┘ │     │ │ DB Lookup    │ │
│  │ Offline Queue│  │     └──────────────────┘     │ │ Cache Layer  │ │
│  └─────────────┘  │                               │ │ Sync Handler │ │
└──────────────────┘                               │ └──────────────┘ │
        │                                           └──────────────────┘
        │                                                    │
        └────────────── HTTPS ──────────────────────────────┘
```

### 6.3 Database Schema

```
Users
  - id (PK)
  - role (super_admin / admin / professor / student)
  - username (unique)
  - email (unique — login identity)
  - password_hash (bcrypt)
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
  - user_id (FK → users, nullable, unique — set when the student claims this record at registration)
  - student_id (unique — the same value encoded in the ID card QR)
  - email (unique — official email, the registration lookup key)
  - first_name, middle_name, last_name
  - course, section, year_level
  - is_active
  - created_at, updated_at

Professors
  - id (PK)
  - user_id (FK → users, nullable, unique — set when the professor claims this record at registration)
  - email (unique — official email, the registration lookup key and professor identifier)
  - first_name, middle_name, last_name
  - department
  - is_active
  - created_at, updated_at

OtpCodes
  - id (PK)
  - email (index — the lookup key; the user may not exist yet during claim)
  - purpose (claim / forgot_password)
  - otp_hash (bcrypt-hashed 6-digit code, never stored plaintext)
  - expires_at (5-minute TTL)
  - consumed_at (null until used — single-use)
  - user_id (FK → users, nullable — set when the code targets an existing account)
  - created_at

Courses
  - id (PK)
  - course_code, course_name
  - classroom_lat, classroom_lng (for GPS geofencing)
  - schedule (day/time)

Enrollments
  - id (PK)
  - student_id (FK → Students)
  - course_id (FK → Courses)
  - academic_year

Sessions
  - id (PK)
  - course_id (FK → Courses)
  - professor_id
  - session_code (HMAC token)
  - expires_at
  - classroom_radius_meters (default: 30)

AttendanceRecords
  - id (PK)
  - student_id (FK → Students)
  - session_id (FK → Sessions)
  - timestamp
  - gps_lat, gps_lng (recorded at scan time)
  - validation_status (valid / pending / pending_liveness / rejected)
  - sync_status (synced / pending / failed)
  - created_at

FaceEnrollment
  - id (PK)
  - student_id (FK → Students)
  - face_embedding (vector — enrolled reference photo)
  - status (active / pending / disabled)
  - created_at, updated_at

LivenessAttempt
  - id (PK)
  - student_id (FK → Students)
  - attendance_record_id (FK → AttendanceRecords)
  - evidence_bundle (JSON — challenge transcript, landmark series, nonce)
  - qr_liveness_score, face_liveness_score, gps_score
  - verdict (accept / review / reject)
  - review_status (auto / flagged / reviewed)
  - created_at

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
  **bcrypt**; plaintext is never stored or logged.
- **Cloudflare Turnstile** (free, invisible captcha) at login and on the first
  step of password recovery to deter automated attacks.
- **Forgot Password flow** (4 steps): email + captcha → **security question**
  (max **3 attempts** before abort/lock) → **OTP** (6-digit, expires in 5
  min; stored bcrypt-hashed in the `otp_codes` table, single-use) → **enter
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

| Sprint   | Focus                                                         |
| -------- | ------------------------------------------------------------- |
| Sprint 1 | Requirements gathering, database design, wireframing          |
| Sprint 2 | Backend API setup, student CRUD, CSV import                   |
| Sprint 3 | QR scanning module, caching layer, basic attendance recording |
| Sprint 4 | HMAC session authentication, GPS geofencing                   |
| Sprint 5 | QR liveness detection, face enrollment, duplicate prevention  |
| Sprint 6 | Liveness protocol: challenge-response, evidence bundles, nonce registry, risk fusion |
| Sprint 7 | Offline storage, background sync with deferred liveness       |
| Sprint 8 | Analytics: aggregation, at-risk forecasting, prescriptive rules |
| Sprint 9 | Attack corpus + APCER/BPCER evaluation, dashboard polish      |
| Sprint 10 | Testing, bug fixes, deployment                                |
| Sprint 11 | User acceptance testing, documentation                        |

---

## 8. Scope & Limitations

### In Scope

- QR scanning from existing campus ID cards (no QR generation needed)
- HMAC-based session code anti-spoofing
- GPS geofencing for classroom validation
- Live QR detection (physical card vs screen)
- Face liveness verification (challenge-response against image, video-replay, screen-recorder, and distortion attacks)
- Offline liveness protocol with nonce anti-replay deferred validation and risk-fusion scoring
- Face enrollment (selfie capture with LMS-verified student match)
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

| Phase                   | Duration     | Deliverable                                        |
| ----------------------- | ------------ | -------------------------------------------------- |
| Planning & Design       | 2 weeks      | SRS document, system design, UI mockups            |
| Core Development        | 4 weeks      | Backend API + frontend with QR scan, sessions, GPS |
| Liveness Protocol       | 3 weeks      | Face challenges, evidence bundles, nonce registry, risk fusion |
| Analytics & Dashboards  | 2 weeks      | Aggregation, at-risk forecasting, prescriptive rules, dashboards |
| Evaluation & Testing    | 3 weeks      | Attack corpus + APCER/BPCER, unit/integration tests, UAT, deployment |
| **Total**               | **14 weeks** | Fully functional attendance system                 |

---

## 10. Team Roles (if applicable)

| Role               | Responsibilities                                             |
| ------------------ | ------------------------------------------------------------ |
| Project Manager    | Sprint planning, progress tracking, documentation            |
| Backend Developer  | FastAPI, database, caching, HMAC, sync logic                 |
| Frontend Developer | SvelteKit PWA, QR scanning, GPS, offline storage, live detection |
| QA Tester          | Test cases, bug tracking, UAT coordination                   |

---

## 11. Summary

This project proposes a QR-code based attendance system that eliminates manual roll call, prevents spoofing through multiple verification layers (session code, GPS, QR liveness, face liveness, offline evidence anti-replay, duplicate prevention), and works reliably even with intermittent internet connectivity. It leverages existing student ID cards without requiring any new QR generation, extends liveness verification to offline environments via a deferred-validation protocol, and provides predictive/prescriptive attendance analytics. The system is built as a cross-platform PWA using Python (FastAPI) and SvelteKit, making it accessible on any device with a browser and camera.

---

_Prepared for Software Engineering 1_
