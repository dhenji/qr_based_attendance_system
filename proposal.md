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
- Validates attendance through multi-layer anti-spoofing: session code, GPS geofencing, live QR detection, and one-scan-per-session enforcement
- Works offline by storing records locally and auto-syncing when connectivity is restored
- Provides dashboards and reports for professors and administrators

---

## 2. Objectives

### 2.1 General Objective

To design and develop a QR-code based attendance system that automates the attendance process, prevents spoofing, and remains functional even without internet connectivity.

### 2.2 Specific Objectives

1. Develop a QR scanning module that decodes student ID numbers from existing campus ID cards
2. Implement a caching and indexing algorithm for efficient student data retrieval (O(1) lookup)
3. Design a multi-layer anti-spoofing mechanism: HMAC session codes, GPS geofencing, live QR detection, and duplicate scan prevention
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

### 3.5 Live QR Detection (Liveness Check)

- **Concept**: Computer vision reflection analysis / QR error correction pattern analysis
- **Application**: The QR scanner analyzes reflections, micro-texture, and lighting patterns to distinguish a physical ID card from a screen (photo/screenshot). Libraries like `html5-qrcode` support this via focus and reflection heuristics.
- **Why**: Prevents students from scanning a screenshot of a classmate's ID card.

### 3.6 Database Design & Normalization

- **Concept**: Relational database normalization (3NF)
- **Application**: Tables for Students, Courses, Enrollments, AttendanceRecords, Sessions, and SyncQueue with proper foreign keys and constraints.
- **Why**: Ensures data integrity, avoids redundancy, and supports efficient queries.

### 3.7 Software Engineering Lifecycle

- **Concept**: Agile/Scrum methodology
- **Application**: The project is developed in sprints: requirements gathering, system design, iterative implementation, testing, deployment, and maintenance.
- **Why**: Provides a structured approach to software development with stakeholder feedback loops.

---

## 4. Application Data Flow

### 4.1 Setup Phase (One-Time)

```
Registrar provides student roster (CSV)
  └→ Columns: student_id, first_name, last_name, course, year_level
    └→ Imported into database
      └→ Each student_id is the same one encoded in the student's ID card QR
```

**Key insight**: The QR code on student IDs already encodes the student ID number. No QR generation or re-encoding is needed. The CSV provides the student's name, course, and year — the QR provides the key to match them.

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
│    → Device also grabs current GPS coordinates                   │
│    → Sends to server: { student_id, session_code, gps }          │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                     SERVER VALIDATION                            │
│                                                                   │
│  1. HMAC Check  ── Is session_code valid and not expired?        │
│  2. GPS Check   ── Is student within classroom geofence?         │
│  3. Liveness    ── Was QR scanned from a physical card?          │
│  4. Uniqueness  ── Has this student already scanned?             │
│  5. Enrollment  ── Is student enrolled in this course?           │
│                                                                   │
│  ALL PASS? → Attendance recorded ✅                              │
│  ANY FAIL?  → Attendance rejected ❌                             │
└─────────────────────────────────────────────────────────────────┘
```

### 4.3 Offline Scenario

```
┌─────────────────────────────────────────────────────────────────┐
│                     INTERNET DOWN                                │
│                                                                   │
│  Student scans QR → System attempts server validation            │
│    → Connection fails → Record saved to local IndexedDB          │
│    → Status: "Pending Sync"                                      │
│    → Student sees: "Attendance saved locally"                     │
│                                                                   │
│  ─── When internet returns ───                                   │
│                                                                   │
│  Service Worker detects connectivity                             │
│    → Pushes all pending records to server                        │
│    → Server validates each (HMAC, GPS, liveness, uniqueness)     │
│    → Valid ones → marked as "Synced"                             │
│    → Invalid ones → flagged for review                           │
└─────────────────────────────────────────────────────────────────┘
```

### 4.4 Anti-Spoofing Layer Summary

| Layer                | What It Prevents                | CS Concept                   |
| -------------------- | ------------------------------- | ---------------------------- |
| Session Code         | Outsiders submitting attendance | HMAC-SHA256                  |
| GPS Geofencing       | Remote/fake submissions         | Haversine Algorithm          |
| Live QR Detection    | Screenshot of a classmate's ID  | Reflection/Liveness Analysis |
| One Scan Per Session | Same ID used multiple times     | Database Constraint          |

---

## 5. Features

| #   | Feature                     | Description                                                          |
| --- | --------------------------- | -------------------------------------------------------------------- |
| 1   | QR Code Scanning            | Decodes student ID number from campus ID card QR using device camera |
| 2   | HMAC Session Codes          | Professor generates time-limited session; required for attendance    |
| 3   | GPS Geofencing              | Validates student is within classroom perimeter                      |
| 4   | Live QR Detection           | Distinguishes physical card from screen (screenshot prevention)      |
| 5   | One Scan Per Session        | Prevents duplicate submissions                                       |
| 6   | Offline Mode                | Attendance stored locally, auto-synced when online                   |
| 7   | Student Roster Management   | CSV import, add/edit/remove students                                 |
| 8   | Year-Level Auto-Advancement | Batch-updates student year levels at academic year end               |
| 9   | Attendance Dashboard        | Real-time view of attendance per session, per course, per student    |
| 10  | Reports Export              | Download attendance reports as CSV/PDF                               |

---

## 6. System Architecture

### 6.1 Tech Stack

| Layer           | Technology                               | Purpose                                               |
| --------------- | ---------------------------------------- | ----------------------------------------------------- |
| Frontend        | React + PWA (Service Workers)            | Cross-platform UI, offline support, camera/GPS access |
| Backend         | Python FastAPI                           | REST API server, async request handling               |
| Database        | PostgreSQL (server) + IndexedDB (client) | Persistent storage + local cache                      |
| QR Library      | html5-qrcode                             | QR decoding and live detection in browser             |
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
│  │ GPS Reader   │  │     │ │ View Reports │ │     │ │ GPS Verify   │ │
│  │ IndexedDB   │  │     │ │ Manage Course│ │     │ │ DB Lookup    │ │
│  │ Offline Queue│  │     │ └──────────────┘ │     │ │ Cache Layer  │ │
│  └─────────────┘  │     └──────────────────┘     │ │ Sync Handler │ │
└──────────────────┘                               │ └──────────────┘ │
        │                                            └──────────────────┘
        │                                                    │
        └────────────── HTTPS ──────────────────────────────┘
```

### 6.3 Database Schema

```
Students
  - id (PK)
  - student_id (unique — the same value encoded in the ID card QR)
  - first_name, last_name
  - course, year_level
  - is_active
  - created_at, updated_at

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
  - validation_status (valid / pending / rejected)
  - sync_status (synced / pending_sync / failed)
  - created_at

SyncQueue
  - id (PK)
  - record_data (JSON — serialized attendance record)
  - status (pending / synced / failed)
  - retry_count
  - created_at
```

---

## 7. Methodology (Agile/Scrum)

The project will follow an Agile approach with 2-week sprints:

| Sprint   | Focus                                                         |
| -------- | ------------------------------------------------------------- |
| Sprint 1 | Requirements gathering, database design, wireframing          |
| Sprint 2 | Backend API setup, student CRUD, CSV import                   |
| Sprint 3 | QR scanning module, caching layer, basic attendance recording |
| Sprint 4 | HMAC session authentication, GPS geofencing                   |
| Sprint 5 | Live QR detection, duplicate scan prevention                  |
| Sprint 6 | Offline storage, background sync service                      |
| Sprint 7 | Dashboard, reports, year-level auto-advance                   |
| Sprint 8 | Testing, bug fixes, deployment                                |
| Sprint 9 | User acceptance testing, documentation                        |

---

## 8. Scope & Limitations

### In Scope

- QR scanning from existing campus ID cards (no QR generation needed)
- HMAC-based session code anti-spoofing
- GPS geofencing for classroom validation
- Live QR detection (physical card vs screen)
- One-scan-per-session enforcement
- Offline attendance storage with auto-sync
- CSV-based student roster import
- Attendance dashboard and report export

### Out of Scope (Future Work)

- Facial recognition verification
- Integration with school's existing LMS or registrar API
- Push notification system
- Biometric authentication
- Mobile native apps (iOS/Android)
- Real-time QR code generation (dynamic QR)

---

## 9. Timeline

| Phase                   | Duration     | Deliverable                                        |
| ----------------------- | ------------ | -------------------------------------------------- |
| Planning & Design       | 2 weeks      | SRS document, system design, UI mockups            |
| Core Development        | 4 weeks      | Backend API + frontend with QR scan, sessions, GPS |
| Offline & Anti-Spoofing | 2 weeks      | Offline queue, live QR detection, sync service     |
| Dashboard & Reports     | 2 weeks      | Admin dashboard, year-level auto-advance           |
| Testing & Deployment    | 2 weeks      | Unit tests, integration tests, UAT, deployment     |
| **Total**               | **12 weeks** | Fully functional attendance system                 |

---

## 10. Team Roles (if applicable)

| Role               | Responsibilities                                             |
| ------------------ | ------------------------------------------------------------ |
| Project Manager    | Sprint planning, progress tracking, documentation            |
| Backend Developer  | FastAPI, database, caching, HMAC, sync logic                 |
| Frontend Developer | React PWA, QR scanning, GPS, offline storage, live detection |
| QA Tester          | Test cases, bug tracking, UAT coordination                   |

---

## 11. Summary

This project proposes a QR-code based attendance system that eliminates manual roll call, prevents spoofing through multiple verification layers (session code, GPS, live QR detection, duplicate prevention), and works reliably even with intermittent internet connectivity. It leverages existing student ID cards without requiring any new QR generation. The system is built as a cross-platform PWA using Python (FastAPI) and JavaScript (React), making it accessible on any device with a browser and camera.

---

_Prepared for Software Engineering 1_
