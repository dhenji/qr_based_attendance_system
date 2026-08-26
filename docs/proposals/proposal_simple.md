# Project Proposal: QR-Based Attendance System

**Course**: Software Engineering 1

---

## 1. Project Title

QR-Code Based Offline-Capable Attendance System with Anti-Spoofing

## 2. Project Description

An attendance system that uses the QR codes already printed on student ID cards. Instead of manual calling of names, students scan their ID card QR code using their phone. The system records who is present, who is absent, and generates reports for professors.

## 3. Problem Being Solved

- Manual attendance wastes 5–10 minutes of class time
- Students can fraudulently sign for absent classmates
- Campus internet is not always reliable
- Paper records are easily lost

## 4. Proposed Solution

A web-based application that:

- Scans the QR code on student IDs to identify the student
- Uses a session code (shown by the professor) + GPS location + face verification to prevent cheating
- Organizes courses under a **Program → Year Level → Course** hierarchy with per-year term structures
- Enforces present/late time windows and duration expiry for each session
- Supports a full excuse workflow: professor quick-excuse, professor with evidence, student-initiated request
- Admin-enrolls face embeddings from 3-angle photos (front/left/right) for identity verification
- Provides unified analytics with cascading filters (Program → Year → Term → Course) and at-risk prediction
- Works even without internet by saving attendance locally and uploading later
- Backs up the full database with AES-256-GCM encryption

## 5. Target Users

- Professors — to open sessions and view attendance reports
- Students — to scan their ID and mark attendance
- Administrators — to manage student rosters and generate reports

## 6. Features

| Feature          | Purpose                                                       |
| ---------------- | ------------------------------------------------------------- |
| QR Code Scanning | Scan student ID card QR using phone camera                    |
| Session Code     | Professor shares a code with present/late windows; required to submit attendance |
| GPS Verification | Ensures student is inside the classroom                       |
| Face Liveness    | Blink→left→right challenges to block photo, replay & distortion tricks |
| Face Enrollment  | Admin captures 3-angle photos; 128-d encrypted embeddings     |
| Academic Structure | Program → Year Level → Course hierarchy with term structures |
| Window-Based Attendance | Present/late windows, duration expiry, per-session overrides |
| Excuse Workflow   | 3 paths: professor quick-excuse, with evidence, student request |
| Offline Mode     | Saves attendance locally when no internet; auto-uploads later |
| Student Roster   | Import students from CSV file                                 |
| Analytics        | Unified page: Overview, Course Comparison, Trends, At-Risk, Export |
| At-Risk Prediction | Heuristic thresholds (daily batch), compliance/participation rates |
| Reports          | Download attendance reports (CSV/PDF/Print)                    |
| Data Tables      | Sortable columns, category + date-range filters, search, print  |
| Encrypted Backups | Full DB dump AES-256-GCM encrypted, 30D daily + 12M monthly  |
| Account Security | Strong passwords (bcrypt), Cloudflare Turnstile, OTP, optional MFA, admin reset, lockout |

> **Names & structure**: students use First/Middle/Last names with a Section
> field (from CSV import); section changes are admin-only actions. The academic
> hierarchy (Program → Year Level → Course) is managed by admins through
> Academic Structure Updates (add/rename year levels, adjust term structures,
> move courses) — replacing year-level promotion (D38). **Registration is
> claim-based**: students and professors self-register with email + password;
> the email must match their admin-seeded record (official email) and an OTP
> proves ownership — names are never typed. Admin accounts are seeded at deploy
> / created by an existing admin — never self-registered.

## 7. Technology Stack

| Component | Technology                                |
| --------- | ----------------------------------------- |
| Backend   | Python (FastAPI)                          |
| Frontend | JavaScript (SvelteKit) |
| Database  | PostgreSQL                                |
| Charts    | Chart.js (analytics dashboards)           |
| Face Embeddings | face-api.js (pretrained, 128-d)     |
| Platform  | Progressive Web App (works on any device) |

## 8. CS Concepts Used

- **Caching & Indexing** — fast student lookup when scanning QR
- **Offline-First Architecture** — local storage + auto-sync with session-expired rejection
- **HMAC Hashing** — secure session codes
- **Geolocation Algorithms** — GPS classroom validation (Haversine)
- **Liveness Protocol** — fixed-challenge anti-spoofing with offline deferred validation
- **Biometric Template Protection** — 3-photo encrypted embeddings, pull-on-login distribution
- **Attendance Policy Engine** — window-based present/late/absent determination with duration expiry
- **State Machine** — excuse workflow (pending → approved/rejected) with audit trail
- **Heuristic Analytics** — env-configurable thresholds for at-risk prediction (future ML upgrade path)
- **Data Analytics** — descriptive, diagnostic, predictive, and prescriptive reporting with compliance/participation rates
- **Relational Database Design** — normalized tables with academic hierarchy (Program → Year Level → Course)
- **Encrypted Backups** — AES-256-GCM full-database dumps with retention policy

## 9. Expected Outcome

A fully functional attendance system that:

- Speeds up attendance to under 1 second per student
- Prevents cheating through session codes + GPS + QR liveness + face liveness
- Blocks photo, screen-recorder, video-replay, and distortion attacks
- Works with or without internet (liveness evidence re-validated after sync; expired scans rejected)
- Manages academic programs with per-year term structures and multi-program course sharing
- Enforces present/late windows and duration-based session expiry
- Supports 3-path excuse workflow with evidence attachments and audit trail
- Provides unified analytics with cascading filters and at-risk prediction
- Encrypts full-database backups with configurable retention
- Works on any phone with a camera (no app installation needed)

## 10. Team Members

| Name   | Role   |
| ------ | ------ |
| [Name] | [Role] |
| [Name] | [Role] |
| [Name] | [Role] |

---

_Submitted for Software Engineering 1_
