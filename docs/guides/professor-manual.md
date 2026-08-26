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
5. Set password — your name, department, and assigned *courses* are pulled from the seeded record automatically

---

## 2. Dashboard & Quick Actions

[FIG: Professor Dashboard with KPI cards (Sessions Today, Students, Avg Rate), Today's Sessions list with Program/Year badges, Quick Actions: [+ New Session], [Export Report]]

### 2.1 KPI Cards
- **Sessions Today**: Active / total sessions scheduled for today
- **Students**: Total enrolled across your assigned *courses*
- **Avg Rate**: Average compliance *rate* across recent sessions

### 2.2 Today's Sessions
Each row shows:
- *Course* name with **cohort badge** (e.g., `BSCS·Y1`)
- Section info
- Scan progress (e.g., `18/30 scanned`)
- **[View Live]** for active sessions / **[Open Session]** for upcoming ones

### 2.3 Quick Actions
| Button | Action |
|--------|--------|
| **[+ New Session]** | Opens the *selector variant* ([Section 3.2](#32-session-creation-variants)) |
| **[Export Report]** | Deep-links to [Export](../design/wireframes.md#38-professor-export---professorattendanceexport) with today's date range pre-filled |

---

## 3. Opening Sessions

Per [D11](../project/decision-log.md), there are **two entry points** that determine which variant you see.

### 3.1 Session Creation Variants

| Variant | Entry Point | Course Selection |
|---------|-------------|------------------|
| **Locked** (3.2a) | **My Courses** → [🔐 Open Session] | Fixed — pre-filled from the *course* card |
| **Selector** (3.2b) | **Dashboard** → [+ New Session] | Dropdown limited to your **active assignments this term** |

> **Recommendation**: Use **Locked** (from My Courses) for routine classes. Use **Selector** only when opening a session for a different *course* than the one you're currently viewing.

### 3.2 Locked Variant — `/professor/sessions/create?course={id}`

[FIG: Open Session form with locked course card (code/name, program·year·section, schedule, room), geofence radius presets, duration input with helper text "expires min(now+duration, scheduled end)", present/late window inputs with live validation "Present + Late ≤ Duration", optional classroom override, HMAC preview, [Generate Session Code] button]

**Fields**:
| Field | Description | Default |
|-------|-------------|---------|
| **Course** | 🔒 Locked — shows *course* code, name, *program·year*, section, schedule, room | From *course* card |
| **Geofence Radius** | Preset buttons: 10m, 20m, 30m, 50m, 100m | Course default (typically 30m) |
| **Duration (minutes)** | Session length; expiry = `min(now + duration, scheduled_end_time)` per [D12](../project/decision-log.md) | Scheduled length (e.g., 90 for 1.5h) |
| **Present Window** | Minutes from session start for *present* status | Course `default_present_window_minutes` (5) |
| **Late Window** | Minutes after present window for *late* status | Course `default_late_window_minutes` (10) |
| **Classroom Override** | Optional — overrides *course* GPS/room for this session only | Blank = use *course* defaults |
| **HMAC Preview** | Shows the 6–8 char *session code* that will be generated | Auto-generated |

**Window Math Validation** (live):
```
Present ___ + Late ___ ≤ Duration ___
   5    +    10    ≤     90     ✅
```
Constraint: `present_window_minutes + late_window_minutes ≤ duration_minutes` (enforced by CHECK on `sessions` table).

### 3.3 Selector Variant — `/professor/sessions/create`

[FIG: Same form as Locked but with "Select Course" dropdown at top showing only active assignments for the current term]

**Course Dropdown**: Lists only *courses* where you have an active `course_professors` assignment for the current *term* ([D11](../project/decision-log.md)).

### 3.4 After Generating the Session

1. **Session Code** appears (e.g., `A7X-9K2M`) — display this on the projector
2. **Session QR** is also generated (payload includes code, *course* ID, radius, windows) — students can scan instead of typing
3. The session is now **Active** and appears in [Live Monitoring](#4-live-session-monitoring)

> **Tip**: The *session code* is HMAC-signed and time-bound. It cannot be guessed or reused across sessions.

---

## 4. Live Session Monitoring

### 4.1 Active Session / Projector Mode — `/professor/sessions/active/[id]`

[FIG: Active Session screen with large session code for projector, dual timers (Scan window countdown + Class ends), enrolled/scanned/remaining counters, status legend, live feed table with per-row [Excuse], [Excuse All Absent] button, post-expiry banner "Scanning closed — waiting for offline syncs"]

### 4.2 Dual Timers
| Timer | Meaning |
|-------|---------|
| **⏱ Scan window** | Countdown from `session.created_at + duration_minutes` (or `scheduled_end_time`, whichever is earlier) |
| **🏁 Class ends** | Fixed *scheduled end time* from the *course* schedule |

> **Duration Expiry** ([D12](../project/decision-log.md)): `expires_at = min(created_at + duration_minutes, scheduled_end_time)`. After this, no new scans accepted.

### 4.3 Status Legend
```
✅ Present   ⏰ Late   📝 Excused   ⏳ Pending   ❌ Absent   ⛔ Rejected
```

- **Present**: Scanned within *present window*
- **Late**: Scanned within *late window* (after present window)
- **Excused**: Manually excused via any path (counts as present for *Participation Rate*)
- **Pending**: Offline scan queued, not yet synced
- **Absent**: No scan by *duration expiry*

### 4.4 Live Feed Actions
| Action | When Available | Effect |
|--------|----------------|--------|
| **[📝 Excuse]** (per-row) | Student status = *Absent* or *Late* | Opens quick-excuse modal (reason required) — [D21 path a](../project/decision-log.md) |
| **[Excuse All Absent]** | Any time during/after session | Bulk excused all *Absent* students with single reason — typical for cancelled class [D23](../project/decision-log.md) |

### 4.5 Post-Expiry Behavior
After *duration expiry*:
- Banner appears: **"Scanning closed — waiting for offline syncs"**
- Shows count of *Pending* records
- Offline scans sync in background; expired-window offline scans → *Rejected* with reason `session_expired` ([D16](../project/decision-log.md))
- You can still use **[Excuse All Absent]** or per-row excuses

### 4.6 Closing a Session
Click **[Close]** in the header to formally end the session. This is optional — sessions auto-expire at `expires_at`.

---

## 5. Attendance Records

### 5.1 Attendance List — `/professor/attendance`

[FIG: Attendance Records table with filters (Course, Section, Session, Status, Date Range), sortable columns (Date, Student, Section, Status, Time), per-row [Excuse]/[Edit excuse] for Absent/Late/Rejected rows, Export/Print/View Live buttons]

### 5.2 Filters
| Filter | Options |
|--------|---------|
| **Course** | Your assigned *courses* |
| **Section** | Populated from roster ([D2](../project/decision-log.md): *section* lives on *students*) |
| **Session** | Specific *session* codes |
| **Status** | Present, Late, Absent, Excused, Pending, Rejected |
| **Date Range** | From / To |

### 5.3 Row Actions
- **[📝 Excuse]**: Quick-excuse modal for *Absent* or *Late* (requires reason)
- **[✏️ Edit excuse]**: Modify existing *excuse* (reason, evidence)

### 5.4 Export
Click **[📥 Export]** → [Export screen](#8-export) with current filters pre-applied.

---

## 6. Session History

### 6.1 Session History — `/professor/sessions/history`

[FIG: Session History table with filters (Course, Section, Date Range), columns (Date, Code, Section, Present/Late/Absent breakdown, Rate), clickable rows for detail, Export CSV]

**Rate Column**:
- Shows **Compliance Rate** by default (`present / total`)
- Hover tooltip reveals **Participation Rate** (`(present + late + excused) / total`) — [D36](../project/decision-log.md)

**Section Filter**: Filters sessions by *section* (useful when you teach the same *course* to multiple sections).

---

## 7. My Courses

### 7.1 My Courses — `/professor/courses`

[FIG: My Courses with collapsible Program headers, course cards showing cohort badge, schedule, room, student count, primary/assistant indicator, [Open Session] (locked), [Reports] (deep-linked)]

**Card Information**:
- **Cohort Badge**: `BSCS·Y1` — identifies which program/year this *course* instance belongs to ([D6](../project/decision-log.md))
- **Primary/Assistant**: Shows your role for this *course*
- **[🔐 Open Session]**: Opens Locked variant (Section 3.2)
- **[📊 Reports]**: Deep-links to [Reports](#8-reports) pre-filtered to this *course*

---

## 8. Reports

### 8.1 Professor Reports — `/professor/reports`

[FIG: Reports with shared filters (Program, Year, Course, Section, Granularity), three tabs: All Courses, Per-Course Comparison, Trends]

### 8.2 Shared Filters (Apply to All Tabs)
| Filter | Description |
|--------|-------------|
| **Program** | Filter by *program* |
| **Year** | Filter by *year level* |
| **Course** | Filter by *course* |
| **Section** | Filter by *section* |
| **Granularity** | Daily / Weekly / Monthly |

### 8.3 Tab Details

#### All Courses Tab (Aggregate)
[FIG: Bar chart showing daily/weekly/monthly compliance across ALL assigned courses, with average line]

- Aggregates attendance across every *course* you teach
- Default metric: **Compliance Rate**

#### Per-Course Comparison Tab
[FIG: Grouped bars — same course shown once per cohort (e.g., BSCS·Y1 CS101 88%, BSIT·Y1 CS101 91%)]

- Implements [D37](../project/decision-log.md) and [D6](../project/decision-log.md): *course* appears once per *cohort* it spans
- Enables comparison of the same subject across different programs/year levels

#### Trends Tab
[FIG: Multi-series line chart with metric toggle (Compliance / Participation), granularity toggle]

- Tracks attendance trends over time
- **Metric Toggle**: Switch between *Compliance Rate* (default) and *Participation Rate*

### 8.4 Export
**[📥 Download CSV]** / **[📄 Download PDF]** — exports current filter set.

---

## 9. Excuse Requests

### 9.1 Excuse Requests — `/professor/excuse-requests`

[FIG: Excuse Requests list filtered to status=Pending, columns (Student, Course, Session, Type, Reason, Requested At, [Review])]

### 9.2 Three Initiation Paths ([D21](../project/decision-log.md))

| Path | Initiator | Trigger | Auto-Approved? |
|------|-----------|---------|----------------|
| **Quick Excuse** | Professor | Per-row [Excuse] in Live Feed or Attendance List | Yes — immediate |
| **Prof with Evidence** | Professor | Upload evidence + approve in one action | Yes — immediate |
| **Student Request** | Student | Submits reason + evidence via [Request Excuse] | No — requires your review |

### 9.3 Reviewing Student Requests
1. Go to **Excuse Requests** → filter `Status: Pending`
2. Click **[Review]** on a request
3. View reason, evidence attachments, original *attendance* status
4. Choose **[Approve]** or **[Reject]**
5. If **Approved**: *Attendance* status becomes `excused`; `original_status` preserved for audit ([D22](../project/decision-log.md))

### 9.4 Bulk Excuse All Absent
- Available in **Live Feed** (Section 4.4) and **Attendance List**
- Requires a reason (e.g., "Class cancelled — typhoon")
- Applies to all currently *Absent* students in that *session*
- Idempotent — running twice has no additional effect

### 9.5 Effect on Metrics ([D22](../project/decision-log.md), [D36](../project/decision-log.md))
| Metric | Excused Counts As |
|--------|-------------------|
| **Compliance Rate** | ❌ No (only *Present*) |
| **Participation Rate** | ✅ Yes (counts as present) |

---

## 10. Profile & Settings

### 10.1 Profile — `/professor/profile` (Read-Only)

[FIG: Profile tab showing Name, Department, Employee No., Email, Assigned Courses list with cohort badges and Primary/Assistant labels, Claim Status, "Changes handled by Admin" note]

**All fields are read-only** per [D32](../project/decision-log.md). Contact your admin for changes.

### 10.2 Settings — `/professor/settings` (Security Only)

[FIG: Settings tab with Change Password (policy hint), Two-Factor Auth (MFA setup), Security Question, App version]

**Available Actions**:
- **Change Password**: Policy — 8+ chars, 1 upper, 1 lower, 1 number, 1 symbol
- **Set Up MFA**: TOTP authenticator app + backup codes
- **Set Security Question**: Used for password reset fallback

> **No** appearance, notifications, or account deletion options — security only per [D32](../project/decision-log.md).

---

## Quick Reference: Key Routes

| Task | Route |
|------|-------|
| Dashboard | `/professor/dashboard` |
| Open Session (Locked) | `/professor/sessions/create?course={id}` |
| Open Session (Selector) | `/professor/sessions/create` |
| Live Monitoring | `/professor/sessions/active/[id]` |
| Attendance Records | `/professor/attendance` |
| Session History | `/professor/sessions/history` |
| My Courses | `/professor/courses` |
| Reports | `/professor/reports` |
| Export | `/professor/attendance/export` |
| Profile | `/professor/profile` |
| Settings | `/professor/settings` |

---

## Window Tuning Cheat Sheet

| Scenario | Present Window | Late Window | Duration |
|----------|----------------|-------------|----------|
| Standard 1.5h lecture | 5 min | 10 min | 90 min |
| Short 1h class | 3 min | 7 min | 60 min |
| Lab (lenient) | 10 min | 15 min | 180 min |
| **Constraint** | `P + L ≤ Duration` | | |

> **Defaults** come from the *course* (`default_present_window_minutes`, `default_late_window_minutes`) and are overridable per session ([D14](../project/decision-log.md)).

---

*For technical details on the scan flow, offline-first sync, or face verification, see the [Architecture Docs](../architecture/).*