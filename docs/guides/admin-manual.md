# Admin Manual

> QR-Based Attendance System — Administrator Guide
>
> Covers: Program setup, CSV imports, professor assignment (incl. mid-term replacement per [D7–D9](../project/decision-log.md)), analytics reading guide (compliance vs participation), academic structure updates, backup/restore.
>
> **Glossary**: All italicized terms are defined in the [Glossary](../project/glossary.md).
>
> **Routes** match the [Wireframes](../design/wireframes.md) screen map.

---

## Table of Contents

1. [Getting Started](#1-getting-started)
2. [Program Management](#2-program-management)
3. [Student & Professor Import](#3-student--professor-import)
4. [Professor Assignment](#4-professor-assignment)
5. [Analytics & Reports](#5-analytics--reports)
6. [Academic Structure Updates](#6-academic-structure-updates)
7. [Backup & Restore](#7-backup--restore)
8. [Other Admin Screens](#8-other-admin-screens)

---

## 1. Getting Started

### 1.1 Accessing the Admin Portal

1. Navigate to the application URL (e.g., `https://attendance.university.edu`)
2. Click **Login** and enter your admin credentials
3. If MFA is enabled, complete the [MFA Verification](../project/glossary.md#mfa-verification) step
4. You will land on the **Admin Dashboard** ([`/admin/dashboard`](../design/wireframes.md#41-admin-dashboard---admindashboard))

### 1.2 Dashboard Overview

[FIG: Admin Dashboard showing KPI cards (Students, Professors, Programs, Rate), Today's Activity, Quick Actions (Import, Backup), Recent Scans feed]

The dashboard provides:

- **KPI Cards**: Total _students_, _professors_, _programs_, and average compliance _rate_
- **Today's Activity**: Active sessions, total scans, pending offline syncs
- **Quick Actions**: [📥 Import] opens CSV Import; [💾 Backup] triggers a full backup
- **Recent Scans**: Last 10 scan events with status indicators

---

## 2. Program Management

The **Program Management** suite replaces the legacy Course Management. It implements the _Program → Year Level → Course_ hierarchy ([D1](../project/decision-log.md)).

### 2.1 Programs List — `/admin/programs`

[FIG: Programs List table with columns Code, Name, Years, Terms, Courses, Status; [+Add Program] button; search and status filter; Archive action]

**Actions**:

- **[+Add Program]**: Opens a modal to create a new _program_ (code, name, description, total years)
- **Click row** → navigates to [Program Detail](#22-program-detail---adminprogramsid)
- **[Archive]**: Soft-deletes the program (sets `is_active=false`)

### 2.2 Program Detail — `/admin/programs/{id}`

[FIG: Program Detail header with code/name/years; Year Level tabs with term chips (editable via modal), course counts, [View Courses] links; [+Add Year] button]

**Year Level Management**:

- Each _year level_ owns its own _term structure_ ([D3](../project/decision-log.md)) — e.g., BSCS Year 3 has three terms (1st Sem, 2nd Sem, Midyear)
- **[Manage Terms]**: Opens a modal to add/remove term rows and rename their display names. A saved term code is an identity key for offerings and cannot be renamed; add a new term instead. Terms are stored in `year_levels.term_structure` JSONB
- **[View Courses]** → navigates to [Year-Level Courses](#23-year-level-courses---adminprogramspidyidcourses)
- **[+Add Year]**: Creates a new year level under this program

### 2.3 Year-Level Courses — `/admin/programs/{pid}/years/{yid}/courses`

[FIG: Course table with Code, Name, Units, Schedule, Students; [+Add Course] button; term chips shown at top]

**Create Course (Template)** ([D4](../project/decision-log.md)):

A _course_ is a reusable template — a subject definition with no schedule, classroom, or program attached.

| Field                 | Description                              |
| --------------------- | ---------------------------------------- |
| `course_code`         | Unique code (e.g., `CS101`)              |
| `course_name`         | Full name (e.g., Software Engineering)   |
| `units`               | Credit units — required scheduled meeting hours per week (D79) |
| `session_duration_hours` | Default session length: attendance window budget + fallback session length (e.g., 1.5) |

**Create Course Offering** (per program / year level / semester):

An _offering_ is a specific instance of a course for a program, year level, and semester. Create one offering per cohort the course spans.

| Field                                                | Description                              |
| ---------------------------------------------------- | ---------------------------------------- |
| `program`                                            | Target _program_ (e.g., BSCS)            |
| `year_level`                                         | Target _year level_ (e.g., Year 2)       |
| `semester`                                           | Term (e.g., 1st Sem)                     |
| `academic_year`                                      | Academic year (e.g., 2025–2026)          |
| `sessions_per_week`                                  | Meetings per week — counted automatically, one per meeting day (D80) |
| `semester_weeks`                                     | Read-only — the term's session length (set per term in _Manage Terms_, D86) |
| `schedule_days`                                      | Pattern (e.g., `MWF`, `TTH`)             |
| `schedule_start_time` / `schedule_end_time`          | Class times                              |
| `classroom_name` / `classroom_lat` / `classroom_lng` | Default _geofence_ center                |
| `default_present_window_minutes`                     | Default _present window_ (default 5)     |
| `default_late_window_minutes`                        | Default _late window_ (default 10)       |

> **Note**: A _course_ template can span multiple programs/year levels ([D6](../project/decision-log.md)). Create a separate _offering_ for each program/year/semester combination, each with its own schedule and classroom.
>
> **Weekly-hours requirement** ([D79](../project/decision-log.md), reshapes per [D81](../project/decision-log.md)): the course's `units` are the required scheduled meeting hours per week across all meetings. New offerings and added meetings must land on the total (or converge toward it); plain meeting edits reshape freely so multi-step changes can pass through a mismatched total, with the over/short panels tracking back to exact. A 3-unit course holds Mon 07:00–08:30 + Tue 13:00–14:30 (3.0h) but a fresh 3.5h or 1.5h schedule is rejected (over/short). The create forms and the offering detail page show the requirement, scheduled, and over/short hours live.
>
> **Already offered, but no row in sight?** One offering covers a course + program + term + academic year regardless of year level, so the existing instance may belong to a different year level than the one filtered. Follow the "Open offering" link in the message, or clear the year filter to reveal it.

### 2.4 Course Detail — `/admin/courses/{cid}`

[FIG: Course Detail with four tabs: Overview, Professors, Enrolled Students, Settings]

#### Overview Tab

Shows template metadata (units, default session length). _Offering_ details (schedule, classroom GPS, weeks, default windows) are shown on the _offering_ overview.

#### Professors Tab (Assignment & History)

[FIG: Professors tab showing Primary and Assistant assignments with effective_from/to dates, semester, assigned_by, history log; [+Assign Professor] button]

**Assignment Rules** ([D7–D9](../project/decision-log.md)):

- _Professor_ assignments are many-to-many via `course_professors` scoped to an _offering_ (`offering_id`) with `is_primary`, `effective_from`, `effective_to` (nullable = ongoing), `semester`, `assigned_by`, `assigned_at`
- **Mid-term replacement**: End the old assignment by setting `effective_to` to the day before the change; create a new assignment with `effective_from` = change date. History is never rewritten — old sessions stay attributed to the original professor
- Any professor with an **active assignment** for the _offering_ + _semester_ may open _sessions_
- Assistants are secondary assignments (`is_primary=false`)

#### Enrolled Students Tab

Shows roster with _section_ filter ([D2](../project/decision-log.md)), bulk CSV enroll action.

#### Settings Tab

Edits _offering_ defaults: _present window_, _late window_, _geofence radius_.

---

## 3. Student & Professor Import

### 3.1 Student CSV Import — `/admin/students/import`

[FIG: Three-step import: Download Template → Upload File → Preview (shows new/duplicates/errors) → Confirm Import]

**CSV Template Columns**:

```
student_id, first_name, middle_name, last_name, email, program_code, section, year_level
```

- **Email** is the _registration lookup key_ — students claim their record by registering with this email + OTP ([Claim-Based Registration](../project/glossary.md#claim-based-registration))
- **Section** is stored on the _student_ only (not on _enrollments_) per [D2](../project/decision-log.md)
- **Program Code** in the CSV maps to the _program_ hierarchy (offering + year level) for initial enrollment

### 3.2 Professor CSV Import — `/admin/professors` → [Import CSV]

**CSV Template Columns**:

```
first_name, middle_name, last_name, email, department
```

- **Email** is the _registration lookup key_ for professors
- After import, assign courses via the Professor Management screen or Course Detail → Professors tab

---

## 4. Professor Assignment

### 4.1 Assigning a Professor to a Course

1. Navigate to **Course Detail** → **Professors Tab** (`/admin/courses/{cid}`)
2. Click **[+Assign Professor]**
3. Select professor, choose _Primary_ or _Assistant_, set:
   - `effective_from` (start date)
   - `effective_to` (optional — leave blank for ongoing)
   - `semester` (must match a term code from the _year level's term structure_)
4. Save → assignment appears with history log

### 4.2 Mid-Term Replacement (Professor Handover)

**Scenario**: Professor Smith is replaced by Professor Garcia mid-semester.

1. Open the existing assignment for Professor Smith
2. Set `effective_to` = day before the handover date
3. Create a new assignment for Professor Garcia with `effective_from` = handover date
4. Both professors can open _sessions_ during the overlap; the system attributes each _session_ to the professor who opened it

> **Key Principle** ([D8](../project/decision-log.md)): History is never rewritten. Sessions opened by Professor Smith remain under Professor Smith's name.

### 4.3 Professor Management — `/admin/professors`

[FIG: Professor Management table with Name, Department, Email, Courses Assigned, Status, Claim status; [+Add], [Import CSV], [Deactivate], [Reset Pwd], [Archive]]

- **Claim status**: `Unclaimed` (professor hasn't registered) / `Claimed` (professor has completed [Claim-Based Registration](../project/glossary.md#claim-based-registration))
- Use **[Reset Pwd]** if a professor loses access

---

## 5. Analytics & Reports

### 5.1 Accessing Analytics — `/admin/analytics`

[FIG: Analytics & Reports with left filter rail (Program ▸ Year ▸ Term ▸ Courses ▸ Date Range ▸ Granularity), seven tabs: Overview, Course Comparison, Trends, At-Risk, Staging, Attendance, Export]

> The **Attendance** tab keeps its own Course ▸ Professor ▸ Date filter row and hides the analytics filter rail — its slice is per course/professor, not per program/year/term ([ADR-083](../project/decision-log.md)).

### 5.2 Filter Rail (Cascading Filters)

| Filter          | Description                                          |
| --------------- | ---------------------------------------------------- |
| **Program**     | Select a _program_ (e.g., BSCS)                      |
| **Year**        | Select _year level_ within that program              |
| **Term**        | Select _term_ from the year level's _term structure_ |
| **Courses**     | Multi-select _courses_ (can span cohorts)            |
| **Date Range**  | From / To date picker                                |
| **Granularity** | Daily / Weekly / Monthly                             |

Click **[Apply Filters]** to refresh all tabs.

### 5.3 Understanding the Two Rate Metrics

| Metric                 | Formula                              | When to Use                                                      |
| ---------------------- | ------------------------------------ | ---------------------------------------------------------------- |
| **Compliance Rate**    | `present / total`                    | **Default display**. Strict measure — only on-time scans count   |
| **Participation Rate** | `(present + late + excused) / total` | Broader measure — includes _late_ and _excused_ as participation |

> **Key Difference** ([D36](../project/decision-log.md)): _Excused_ counts as present for Participation Rate but not for Compliance Rate. Toggle via the metric selector in Trends tab.

### 5.4 Tab Reference

#### Overview Tab

KPI cards: Total Students, Active Sessions, Avg Compliance Rate, Avg Participation Rate.

#### Course Comparison Tab

[FIG: Grouped bars showing same course across cohorts (e.g., BSCS·Y1 CS101 88%, BSIT·Y1 CS101 91%)]

- Implements [D34](../project/decision-log.md): same _course_ shown once per _cohort_ it spans
- Bars represent Compliance Rate (default) or Participation Rate (toggle)

#### Trends Tab

[FIG: Multi-series line chart with granularity toggle (Daily/Weekly/Monthly), metric toggle (Compliance/Participation)]

- Visualizes attendance trends over the selected date range
- Supports comparison across multiple _courses_

#### At-Risk Tab

[FIG: Table with Student, Course, Absence %, Streak, Trend Arrow, Risk Level badge; [Refresh Risk Scores] button]

**Risk Levels** ([D35](../project/decision-log.md)):

| Level      | Criteria (any one triggers)                                            |
| ---------- | ---------------------------------------------------------------------- |
| **High**   | Absence rate > 30% OR streak ≥ 3 consecutive misses                    |
| **Medium** | Absence rate > 15% OR sync-lag pending ≥ 5 OR trend slope < −0.05/week |
| **Low**    | Below all thresholds                                                   |

- Computed nightly via batch job (02:00 default, configurable via `RISK_BATCH_CRON`)
- **[Refresh Risk Scores]** triggers manual recomputation (admin-only)

#### Staging Tab

Dry-run review of staged risk scores: promote or discard batches before they affect the At-Risk tab.

#### Attendance Tab

Per-course attendance snapshot (wireframe 4.6), relocated here from the old `/admin/attendance` page ([ADR-083](../project/decision-log.md)).

- **Filters**: Course ▸ Professor ▸ Date From / Date To (each change re-runs the snapshot)
- **Sortable columns**: Course, Sessions, Avg (compliance), Trend
- **Trend** compares second-half against first-half compliance of the filtered sessions (`↑` rising · `→` flat · `↓` falling)
- Course codes deep-link to the course detail page
- **[Print]** prints the on-screen table · **[Export Overview]** downloads CSV for the current filters (server-first, falling back to the on-screen rows)

> Deep link: `/admin/analytics?tab=attendance` — the dashboard's "Attendance at a glance" strip links here.

#### Export Tab

Downloads CSV/PDF of the current filter set (attendance, students, risk scores).

---

## 6. Academic Structure Updates

### 6.1 What Replaced "Year + Section Promotion"

The legacy "Year + Section Promotion" (grade-dependent) was removed per [D38](../project/decision-log.md). It is replaced by **Academic Structure Updates** — manual, intentional, audited changes through the Program Management screens.

### 6.2 Making Structural Changes

Access via **System Settings** → **Academic Structure Updates** → **[Edit Programs ➜]** (deep-links to `/admin/programs`)

**Supported Operations**:

| Operation                                       | Screen                          | Audited |
| ----------------------------------------------- | ------------------------------- | ------- |
| Add/rename _program_                            | Programs List (4.5a)            | Yes     |
| Add/rename _year level_                         | Program Detail (4.5b)           | Yes     |
| Edit _term structure_ (add/remove/rename terms) | Program Detail → [Manage Terms] | Yes     |
| Create new _offering_ for a program/year/semester | Year-Level Courses (4.5c)       | Yes     |
| Edit _offering_ defaults (schedule, windows, GPS) | Offering Detail → Settings      | Yes     |

**Last Structural Change** is displayed on the System Settings screen with timestamp and admin name.

> **Warning**: These changes affect enrollment validation, _session_ scheduling, and analytics. Perform during breaks, not mid-semester.

---

## 7. Backup & Restore

### 7.1 Full Database Backup

[FIG: System Settings Backup block showing Status, Last Run, [Backup Now], [Download], retention note (30D+12M), encryption badge; Analytics Export section]

**Backup Scope** ([D39](../project/decision-log.md)):

- **Full dump**: `pg_dump -Fc` of **EVERY table** — nothing excluded by default
- **Encryption**: AES-256-GCM with key from `BACKUP_ENCRYPTION_KEY` (key version tracked)
- **Compression**: gzip
- **Storage**: Local (`BACKUP_LOCAL_DIR`) or S3-compatible (`BACKUP_S3_BUCKET`, `BACKUP_S3_ENDPOINT`) via `BACKUP_STORAGE_TYPE`
- **Retention**: Last 30 daily + 12 monthly (pruned automatically)
- **Logging**: Every backup recorded in `backup_log` table

**To Run a Backup**:

1. Go to **System Settings** (`/admin/system/settings`)
2. Click **[💾 Backup Now]** in the Full Database Backup section
3. Wait for completion — status updates to "Healthy" with timestamp
4. Click **[📥 Download]** to retrieve the encrypted `.dump.gz.enc` file

### 7.2 Analytics Export

Separate from backups — exports aggregated reporting data (CSV/PDF) without touching the backup pipeline.

### 7.3 Restore Procedure

**Preconditions**:

- Staging environment available
- Backup file downloaded and decrypted
- `BACKUP_ENCRYPTION_KEY` (matching `encryption_key_version` in `backup_log`)

**Steps**:

1. Decrypt: `openssl enc -d -aes-256-gcm -salt -pbkdf2 -in backup_<TIMESTAMP>.sql.gz.enc -out backup_<TIMESTAMP>.sql.gz -pass env:BACKUP_ENCRYPTION_KEY`
2. Decompress: `gunzip backup_<TIMESTAMP>.sql.gz`
3. Restore: `pg_restore --verbose --clean --no-acl --no-owner -d <target_db> backup_<TIMESTAMP>.sql`
4. Verify: Run integrity checks (row counts, foreign keys, `backup_log` entry)
5. Promote to production after verification

> **Runbook**: See [Operations Runbooks](../operations/runbooks.md#restore-from-backup) for detailed steps.

---

## 8. Other Admin Screens

| Screen                   | Route                                 | Purpose                                               |
| ------------------------ | ------------------------------------- | ----------------------------------------------------- |
| **Student Management**   | `/admin/students`                     | CRUD, search, deactivate, reset password, archive     |
| **Professor Management** | `/admin/professors`                   | CRUD, course assignment, claim status                 |
| **Attendance Snapshot**  | `/admin/analytics?tab=attendance`     | Cross-course attendance summary (Analytics → Attendance tab) |
| **Audit Logs**           | `/admin/audit-logs`                   | System-wide action log with filters                   |
| **Archive**              | `/admin/students/archive`             | View/restore/permanently delete archived students     |
| **Liveness Review**      | `/admin/attendance/liveness-review`   | Manual review of flagged scans (GPS / submitted score band) |
| **Admin Users**          | `/admin/users`                        | Manage admin accounts (Super Admin only)              |
| **Face Enrollment**      | `/admin/students` → **Enroll face**   | Upload 3 photos or capture them via live camera; remove an existing enrollment (modal; placeholder embedding) |

---

## Quick Reference: Key Routes

| Task                | Route                                       |
| ------------------- | ------------------------------------------- |
| Dashboard           | `/admin/dashboard`                          |
| Programs List       | `/admin/programs`                           |
| Program Detail      | `/admin/programs/{id}`                      |
| Year-Level Courses  | `/admin/programs/{pid}/years/{yid}/courses` |
| Course Detail       | `/admin/courses/{cid}`                      |
| Student Import      | `/admin/students/import`                    |
| Analytics & Reports | `/admin/analytics`                          |
| Attendance Review   | `/admin/attendance`                         |
| System Settings     | `/admin/system/settings`                    |
| Audit Logs          | `/admin/audit-logs`                         |
| Face Enrollment     | `/admin/students` → **Enroll face** (modal) |

---

_For technical details on data models, API contracts, or offline-first behavior, see the [Architecture Docs](../architecture/)._

