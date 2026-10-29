# Professor Manual

> QR-Based Attendance System — Professor Guide
>
> Covers: Locked vs selector session creation, window tuning, live monitoring, excuse paths (incl. bulk excuse-all), reports.
>
> **Glossary**: All italicized terms are defined in the [Glossary](../project/glossary.md).
>
> **Routes** match the [Wireframes](../design/wireframes.md) screen map.

---

## Table of Contents

1. [Getting Started](#1-getting-started)
2. [Dashboard & Quick Actions](#2-dashboard--quick-actions)
3. [Opening Sessions](#3-opening-sessions)
4. [Live Session Monitoring](#4-live-session-monitoring)
5. [Attendance Records](#5-attendance-records)
6. [Session History](#6-session-history)
7. [My Courses](#7-my-courses)
8. [Reports](#8-reports)
9. [Excuse Requests](#9-excuse-requests)
10. [Profile & Settings](#10-profile--settings)

---

## 1. Getting Started

### 1.1 Accessing the Professor Portal

1. Navigate to the application URL
2. Click **Login** and enter your professor credentials
3. Complete [MFA Verification](../project/glossary.md#mfa-verification) if enabled
4. You will land on the **Professor Dashboard** ([`/professor/dashboard`](../design/wireframes.md#31-professor-dashboard---professordashboard))

### 1.2 Claim-Based Registration (First Time)

If you haven't registered yet:

1. Click **Register** on the login page
2. Select **Professor** role
3. Enter your official university email (must match the admin-seeded record)
4. Complete OTP verification sent to that email
5. Set password — your name, department, and assigned _courses_ are pulled from the seeded record automatically

---

## 2. Dashboard & Quick Actions

[FIG: Professor Dashboard with KPI cards (Sessions Today, Students, Avg Rate), Today's Sessions list with Program/Year badges, Quick Actions: [+ New Session], [Export Report]]

### 2.1 KPI Cards

- **Sessions Today**: Active / total sessions scheduled for today
- **Students**: Total enrolled across your assigned _courses_
- **Avg Rate**: Average compliance _rate_ across recent sessions

### 2.2 Today's Sessions

Each row shows:

- _Course_ name with **cohort badge** (e.g., `BSCS·Y1`)
- Section info
- Scan progress (e.g., `18/30 scanned`)
- **[View Live]** for active sessions / **[Open Session]** for upcoming ones

### 2.3 Quick Actions

| Button              | Action                                                                                                                             |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| **[+ New Session]** | Opens the _selector variant_ ([Section 3.2](#32-session-creation-variants))                                                        |
| **[Export Report]** | Deep-links to [Export](../design/wireframes.md#38-professor-export---professorattendanceexport) with today's date range pre-filled |

---

## 3. Opening Sessions

Per [D11](../project/decision-log.md), there are **two entry points** that determine which variant you see.

### 3.1 Session Creation Variants

| Variant             | Entry Point                        | Course Selection                                          |
| ------------------- | ---------------------------------- | --------------------------------------------------------- |
| **Locked** (3.2a)   | **My Courses** → [🔐 Open Session] | Fixed — pre-filled from the _course_ card                 |
| **Selector** (3.2b) | **Dashboard** → [+ New Session]    | Dropdown limited to your **active assignments this term** |

> **Recommendation**: Use **Locked** (from My Courses) for routine classes. Use **Selector** only when opening a session for a different _course_ than the one you're currently viewing.

### 3.2 Locked Variant — `/professor/sessions/create?course={id}`

[FIG: Open Session form with locked course card (code/name, program·year·section, schedule, room), geofence radius presets, duration input with helper text "expires min(now+duration, scheduled end)", present/late window inputs with live validation "Present + Late ≤ Duration", optional classroom override, HMAC preview, [Generate Session Code] button]

**Fields**:

| Field                  | Description                                                                                              | Default                                     |
| ---------------------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| **Course**             | 🔒 Locked — shows _course_ code, name, _program·year_, section, schedule, room                           | From _offering_ card                        |
| **Geofence Radius**    | Preset buttons: 10m, 20m, 30m, 50m, 100m                                                                 | Offering default (typically 30m)            |
| **Duration (minutes)** | Session length; expiry = `min(max(scheduled_start, now) + duration, scheduled_end_time)` per [D12](../project/decision-log.md)/[D49](../project/decision-log.md) | Scheduled length (e.g., 90 for 1.5h)        |
| **Present Window**     | Minutes from session start for _present_ status                                                          | Offering `default_present_window_minutes` (5) |
| **Late Window**        | Minutes after present window for _late_ status                                                           | Offering `default_late_window_minutes` (10)   |
| **Classroom Override** | Optional — overrides _offering_ GPS/room for this session only                                           | Blank = use _offering_ defaults             |
| **HMAC Preview**       | Shows the 6–8 char _session code_ that will be generated                                                 | Auto-generated                              |

**Window Math Validation** (live):

```
Present ___ + Late ___ ≤ Duration ___
   5    +    10    ≤     90     ✅
```

Constraint: `present_window_minutes + late_window_minutes ≤ duration_minutes` (enforced by CHECK on `sessions` table).

### 3.3 Selector Variant — `/professor/sessions/create`

[FIG: Same form as Locked but with "Select Course" dropdown at top showing only active assignments for the current term]

**Course Dropdown**: Lists only _offerings_ where you have an active `course_professors` assignment for the current _term_ ([D11](../project/decision-log.md)).

### 3.4 After Generating the Session

On a successful generation a confirmation panel appears on the form with the session code,
scheduled time and scan-window close. It stays open until you either dismiss it (returning to the
form with the code shown) or confirm it, which navigates to the live session view
(`/professor/sessions/active/{id}`) for the exact newly created session. If the response is missing
a valid session ID, an error is shown and you stay on the form.

Before the code is generated, **Generate Session Code** asks once more: it shows the course, type,
scheduled time and duration, and notes any override that differs from the offering's plan. Opening
a session starts the scan window and cannot be undone, so a stray click on a half-configured form
does not reach it.

1. **Session Code** appears (e.g., `A7X-9K2M`) — display this on the projector
2. The API also returns a **session QR payload** (code, _course_ ID, radius, windows). The current active-session screen displays the code only, not a QR image — students enter the code.
3. The session is now **Active** and appears in [Live Monitoring](#4-live-session-monitoring)

> **Tip**: The _session code_ is HMAC-derived and time-bound. It cannot be guessed or reused across sessions.

> **Already open**: opening the same course while a session is still live returns **409
> `session_already_active`** naming the course and the active session's scheduled window
> (e.g. `CS101 2026-10-26 08:03–09:03`) rather than the offering id. Close the active session
> or wait for it to expire before opening another.

---

## 4. Live Session Monitoring

### 4.1 Active Session / Projector Mode — `/professor/sessions/active/[id]`

[FIG: Active Session screen with large session code for projector, dual timers (Scan window countdown + Class ends), enrolled/scanned/remaining counters, status legend, live feed table with per-row [Excuse], [Excuse All Absent] button, post-expiry banner "Scanning closed — waiting for offline syncs"]

### 4.2 Dual Timers

| Timer             | Meaning                                                                                                |
| ----------------- | ------------------------------------------------------------------------------------------------------ |
| **⏱ Scan window** | Countdown from `session.created_at + duration_minutes` (or `scheduled_end_time`, whichever is earlier) |
| **🏁 Class ends** | Fixed _scheduled end time_ from the _offering_ schedule                                                  |

> **Duration Expiry** ([D12](../project/decision-log.md)): `expires_at = min(max(scheduled_start_time, created_at) + duration_minutes, scheduled_end_time)`. After this, no new scans accepted.
>
> **Scheduled sessions**: a session opened for a future class shows status **Scheduled** with a "Class starts in" countdown to `scheduled_start_time`; it is not scannable until then (`session_not_started`). Once the start time is reached it becomes **Active**.

### 4.3 Status Legend

```
✅ Present   ⏰ Late   📝 Excused   ⏳ Pending   ❌ Absent   ⛔ Rejected
```

- **Present**: Scanned within _present window_
- **Late**: Scanned within _late window_ (after present window)
- **Excused**: Manually excused via any path (counts as present for _Participation Rate_)
- **Pending**: Offline scan queued, not yet synced
- **Absent**: No scan by _duration expiry_

### 4.4 Live Feed Actions

| Action                    | When Available                      | Effect                                                                                                                |
| ------------------------- | ----------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| **[📝 Excuse]** (per-row) | Student status = _Absent_ or _Late_ | Opens quick-excuse modal (reason required) — [D21 path a](../project/decision-log.md)                                 |
| **[Excuse All Absent]**   | Any time during/after session       | Bulk excused all _Absent_ students with single reason — typical for cancelled class [D23](../project/decision-log.md) |

### 4.5 Post-Expiry Behavior

After _duration expiry_:

- Banner appears: **"Scanning closed — waiting for offline syncs"**
- Shows count of _Pending_ records
- Offline scans sync in background; expired-window offline scans → _Rejected_ with reason `session_expired` ([D16](../project/decision-log.md))
- You can still use **[Excuse All Absent]** or per-row excuses

### 4.6 Closed-Session Header & Timer Behavior

When `session.status` is `closed` (manually closed via **[Close]** or auto-expired at `expires_at`):

- The header label reads **"Closed:"** instead of "Active:" (driven by `session.status`, not the URL).
- The scan-window countdown freezes at `00:00:00`.
- The class-end timer shows the **actual end time** from `expires_at` (falls back to the scheduled end time) instead of a running countdown.
- The **[Close]** button is disabled.
- The page still renders fully (attendance review remains available).

Click **[Close]** in the header to formally end the session. This is optional — sessions auto-expire at `expires_at`.

---

## 5. Attendance Records

### 5.1 Attendance List — `/professor/attendance`

[FIG: Attendance Records table with filters (Course, Section, Session, Status, Date Range), sortable columns (Date, Student, Section, Status, Time), per-row [Excuse]/[Edit excuse] for Absent/Late/Rejected rows, Export/Print/View Live buttons]

### 5.2 Filters

| Filter         | Options                                                                                 |
| -------------- | --------------------------------------------------------------------------------------- |
| **Course**     | Your assigned _courses_                                                                 |
| **Section**    | Populated from roster ([D2](../project/decision-log.md): _section_ lives on _students_) |
| **Session**    | Specific _session_ codes                                                                |
| **Status**     | Present, Late, Absent, Excused, Pending, Rejected                                       |
| **Date Range** | From / To                                                                               |

### 5.3 Row Actions

- **[📝 Excuse]**: Quick-excuse modal for _Absent_ or _Late_ (requires reason)
- **[✏️ Edit excuse]**: Modify existing _excuse_ (reason, evidence)

### 5.4 Export

Click **[📥 Export]** → [Export screen](#8-export) with current filters pre-applied.

---

## 6. Session History

### 6.1 Session History — `/professor/sessions/history`

[FIG: Session History table with filters (Course, Section, Date Range), columns (Date, Code, Section, Present/Late/Absent breakdown, Rate), clickable rows for detail, Export CSV]

**Rate Column**:

- Shows **Compliance Rate** by default (`present / total`)
- Hover tooltip reveals **Participation Rate** (`(present + late + excused) / total`) — [D36](../project/decision-log.md)

**Section Filter**: Filters sessions by _section_ (useful when you teach the same _course_ to multiple sections).

---

## 7. My Courses

### 7.1 My Courses — `/professor/courses`

[FIG: My Courses with collapsible Program headers, offering cards showing course code/name, cohort badge (program·year·semester), schedule, room, student count, primary/assistant indicator, [Open Session] (locked), [Reports] (deep-linked)]

**Card Information**:

- **Cohort Badge**: `BSCS·Y2 1st Sem` — identifies which _offering_ this card represents (program, year level, semester) ([D6](../project/decision-log.md))
- **Primary/Assistant**: Shows your role for this _offering_
- **[🔐 Open Session]**: Opens Locked variant (Section 3.2)
- **[📊 Reports]**: Deep-links to [Reports](#8-reports) pre-filtered to this _offering_
- **[👥 Students]**: Opens the enrolled-student roster for this _offering_ (`/professor/courses/{offeringId}/students`), with search by name, student ID, or email

---

## 8. Reports

### 8.1 Professor Reports — `/professor/reports`

[FIG: Reports with shared filters (Program, Year, Course, Section, Granularity), three tabs: All Courses, Per-Course Comparison, Trends]

### 8.2 Shared Filters (Apply to All Tabs)

| Filter          | Description              |
| --------------- | ------------------------ |
| **Program**     | Filter by _program_      |
| **Year**        | Filter by _year level_   |
| **Course**      | Filter by _course_       |
| **Section**     | Filter by _section_      |
| **Granularity** | Daily / Weekly / Monthly |

### 8.3 Tab Details

#### All Courses Tab (Aggregate)

[FIG: Bar chart showing daily/weekly/monthly compliance across ALL assigned courses, with average line]

- Aggregates attendance across every _course_ you teach
- Default metric: **Compliance Rate**

#### Per-Course Comparison Tab

[FIG: Grouped bars — same course shown once per cohort (e.g., BSCS·Y1 CS101 88%, BSIT·Y1 CS101 91%)]

- Implements [D37](../project/decision-log.md) and [D6](../project/decision-log.md): _course_ appears once per _cohort_ it spans
- Enables comparison of the same subject across different programs/year levels

#### Trends Tab

[FIG: Multi-series line chart with metric toggle (Compliance / Participation), granularity toggle]

- Tracks attendance trends over time
- **Metric Toggle**: Switch between _Compliance Rate_ (default) and _Participation Rate_

### 8.4 Export

**[📥 Download CSV]** / **[📄 Download PDF]** — exports current filter set.

---

## 9. Excuse Requests

### 9.1 Excuse Requests — `/professor/excuse-requests`

[FIG: Excuse Requests list filtered to status=Pending, columns (Student, Course, Session, Type, Reason, Requested At, [Review])]

### 9.2 Three Initiation Paths ([D21](../project/decision-log.md))

| Path                   | Initiator | Trigger                                          | Auto-Approved?            |
| ---------------------- | --------- | ------------------------------------------------ | ------------------------- |
| **Quick Excuse**       | Professor | Per-row [Excuse] in Live Feed or Attendance List | Yes — immediate           |
| **Prof with Evidence** | Professor | Upload evidence + approve in one action          | Yes — immediate           |
| **Student Request**    | Student   | Submits reason + evidence via [Request Excuse]   | No — requires your review |

### 9.3 Reviewing Student Requests

1. Go to **Excuse Requests** → filter `Status: Pending`
2. Click **[Review]** on a request
3. View reason, evidence attachments, original _attendance_ status
4. Choose **[Approve]** or **[Reject]**
5. If **Approved**: _Attendance_ status becomes `excused`; `original_status` preserved for audit ([D22](../project/decision-log.md))

### 9.4 Bulk Excuse All Absent

- Available in **Live Feed** (Section 4.4) and **Attendance List**
- Requires a reason (e.g., "Class cancelled — typhoon")
- Applies to all currently _Absent_ students in that _session_
- Idempotent — running twice has no additional effect

### 9.5 Effect on Metrics ([D22](../project/decision-log.md), [D36](../project/decision-log.md))

| Metric                 | Excused Counts As          |
| ---------------------- | -------------------------- |
| **Compliance Rate**    | ❌ No (only _Present_)     |
| **Participation Rate** | ✅ Yes (counts as present) |

---

## 10. Profile & Settings

### 10.1 Profile — `/professor/profile` (Read-Only)

[FIG: Profile tab showing Name, Department, Employee No., Email, Assigned Courses list with cohort badges and Primary/Assistant labels, Claim Status, "Changes handled by Admin" note]

**All fields are read-only** per [D32](../project/decision-log.md). Contact your admin for changes.

### 10.2 Settings — `/professor/settings`

[FIG: Settings tab with Appearance (theme toggle), Notifications (push/email toggles), Privacy (GPS/camera toggles), Change Password (policy hint), Two-Factor Auth (MFA setup), Security Question, App version]

**Available Actions**:

- **Change Password**: Policy — 8+ chars, 1 upper, 1 lower, 1 number, 1 symbol
- **Set Up MFA**: TOTP authenticator app + backup codes
- **Set Security Question**: Used for password reset fallback

> Alongside security, the page carries device-local preferences — Appearance (Light/Dark theme), Notifications, and Privacy (GPS/camera) toggles. They are stored per browser, never per account, and the theme resets to Light at logout. Identity fields stay admin-managed per [D32](../project/decision-log.md).

---

## Quick Reference: Key Routes

| Task                    | Route                                    |
| ----------------------- | ---------------------------------------- |
| Dashboard               | `/professor/dashboard`                   |
| Open Session (Locked)   | `/professor/sessions/create?course={id}` |
| Open Session (Selector) | `/professor/sessions/create`             |
| Live Monitoring         | `/professor/sessions/active/[id]`        |
| Attendance Records      | `/professor/attendance`                  |
| Session History         | `/professor/sessions/history`            |
| My Courses              | `/professor/courses`                     |
| Reports                 | `/professor/reports`                     |
| Export                  | `/professor/attendance/export`           |
| Profile                 | `/professor/profile`                     |
| Settings                | `/professor/settings`                    |

---

## Window Tuning Cheat Sheet

| Scenario              | Present Window     | Late Window | Duration |
| --------------------- | ------------------ | ----------- | -------- |
| Standard 1.5h lecture | 5 min              | 10 min      | 90 min   |
| Short 1h class        | 3 min              | 7 min       | 60 min   |
| Lab (lenient)         | 10 min             | 15 min      | 180 min  |
| **Constraint**        | `P + L ≤ Duration` |             |          |

> **Defaults** come from the _offering_ (`default_present_window_minutes`, `default_late_window_minutes`) and are overridable per session ([D14](../project/decision-log.md)).

---

_For technical details on the scan flow, offline-first sync, or the current biometric limitations, see the [Architecture Docs](../architecture/)._


## Remote / online sessions

When opening a session, tick "Remote / online session" for classes with no physical classroom. This disables geofencing and removes the classroom coordinate fields; the session is recorded as remote for audit and reporting. In-person sessions still require classroom coordinates for labs and apply the geofence when coordinates are present.
