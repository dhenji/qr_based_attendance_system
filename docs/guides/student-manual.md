# Student Manual

> QR-Based Attendance System — Student Guide
>
> Covers: 5-step scan flow (both entry modes), offline behavior, requesting excuses, calendar/schedule, settings limits.
>
> **Glossary**: All italicized terms are defined in the [Glossary](../project/glossary.md).
>
> **Routes** match the [Wireframes](../design/wireframes.md) screen map.

---

## Table of Contents

1. [Getting Started](#1-getting-started)
2. [Dashboard](#2-dashboard)
3. [The 5-Step Scan Flow](#3-the-5-step-scan-flow)
4. [Offline Behavior](#4-offline-behavior)
5. [Attendance History](#5-attendance-history)
6. [Requesting Excuses](#6-requesting-excuses)
7. [Schedule / Calendar](#7-schedule--calendar)
8. [Notifications](#8-notifications)
9. [Profile & Settings](#9-profile--settings)

---

## 1. Getting Started

### 1.1 First-Time Registration (Claim-Based)

1. Open the app and click **Register**
2. Select **Student** role
3. Enter your **official university email** (must match an admin-seeded roster record)
4. You will receive a 6-digit **OTP** — enter it within 5 minutes
5. Set your password (policy: 8+ chars, 1 upper, 1 lower, 1 number, 1 symbol)
6. Your name, _program_, _section_, and _year level_ are pulled from the roster automatically — nothing is typed

> **Important**: Your **Student ID QR** contains only your _student number_ ([D19](../project/decision-log.md)). Course context always comes from the verified _session_, never from the QR.

### 1.2 Permissions

Before scanning, you will be prompted to allow:

- **Camera**: Required for QR scanning and face verification
- **GPS**: Required for _geofence_ validation

---

## 2. Dashboard

### 2.1 Student Dashboard — `/student/dashboard`

[FIG: Dashboard showing greeting, KPI cards (Rate, Today's count, Total scans), Scan QR Attendance button, Today's Schedule with status icons, Recent Activity feed]

**KPI Cards**:

| Card      | Meaning                                                              |
| --------- | -------------------------------------------------------------------- |
| **Rate**  | Your overall _compliance rate_ (`present / total_expected_sessions`) |
| **Today** | Number of sessions scheduled for today                               |
| **Total** | Total scans across all _courses_                                     |

**Today's Schedule**: Shows each session for today with status:

- 🟢 Scanned (Present)
- 🟡 Pending Sync (Offline)
- 🔴 Missed / Absent
- 📝 Excused

---

## 3. The 5-Step Scan Flow

The scan flow is **strictly sequential** per [D27](../project/decision-log.md). You cannot skip steps.

**Route**: `/student/scan/step/[1-5]` — screens advance automatically on success.

### Step 1: Session Entry — `/student/scan/step/1`

[FIG: Two equal options — [Type code] input + Verify button OR [Scan Session QR] camera tile; verifying spinner; error states]

**Two ways to join**:

#### Option A: Type Session Code

1. Look at the projector in your classroom — the _session code_ is displayed (e.g., `A7X-9K2M`)
2. Enter the code in the text field
3. Click **Verify Code**

#### Option B: Scan Session QR

1. Click the camera tile
2. Point your camera at the QR code projected on screen
3. The app reads the QR payload automatically

> **Session QR payload** ([D18](../project/decision-log.md)): `{"v":1,"code":"A7X-9K2M","offering":123,"radius":30,"pw":5,"lw":10}` — versioned for future migration.

**What happens**: Server verifies the code, fetches the _session_ config (windows, duration, _geofence_ radius, classroom). On failure, a generic "Invalid code" message is shown (no detail leak about wrong program or expired _session_).

### Step 2: Student ID Scan — `/student/scan/step/2`

[FIG: Verified session card showing course name, cohort badge, scan window times, expiry; camera preview for scanning student ID QR; "Fetching your record…" spinner]

1. **Header** shows the verified _course_ info (name, _program·year_, windows, expiry)
2. Scan the QR on your **student ID card**
3. The QR contains your _student number only_ ([D19](../project/decision-log.md))
4. Server resolves your number → fetches your record (enrollment check + duplicate-scan check)

**Possible Failures**:

- "Not enrolled in this course" — you are not registered for this _course_
- "Already scanned for this session" — duplicate scan rejected

### Step 3: Location Check — `/student/scan/step/3`

[FIG: Auto-running GPS check with accuracy pill, distance-to-boundary meter, required radius, pass/fail indicator, [Retry Location] button]

1. Runs **automatically in parallel** with Step 2
2. Uses **Haversine formula** vs the _session_ (or _course_ default) _geofence_ center + radius ([D17](../project/decision-log.md))
3. Shows: GPS accuracy (±m), distance to boundary (m), required radius (m)

**If You're Outside the Geofence**:

- [Retry Location] button to try again after moving
- If you believe the coordinates are wrong, contact your professor

> **Privacy Note**: GPS is used only for attendance validation during active scans. Your location is not tracked outside of scan sessions.

### Step 4: Face Check — `/student/scan/step/4`

[FIG: Live camera with face detected indicator, fixed liveness challenge stepper (Blink → Turn Left → Turn Right) with progress dots, "Verifying identity…" message, match score bands, offline badge variant]

**Liveness Challenge** ([D31](../project/decision-log.md)):

```
● ○ ○  Blink          (Step 1 of 3)
○ ● ○  Turn Left      (Step 2 of 3)
○ ○ ●  Turn Right     (Step 3 of 3)
```

1. Camera activates — detects your face
2. Follow the prompts: **Blink** → **Turn Left** → **Turn Right**
3. Progress dots advance on success
4. Server compares your face against your _admin-enrolled embedding_ (cosine similarity ≥ 0.70)

**Score Bands**:

| Score     | Result                                                 |
| --------- | ------------------------------------------------------ |
| ≥ 0.70    | ✅ **Pass** — proceeds to Step 5                       |
| 0.65–0.70 | ⚠ **Review** — flagged for admin liveness review queue |
| < 0.65    | ❌ **Fail** — rejection with reason `face_mismatch`    |

> **Known Limitation**: Sibling confusion is acknowledged but not solved ([D31](../project/decision-log.md)). Liveness checks mitigate photo/video replay.

> **Offline Mode**: If you're offline, your device compares your face against the _cached embedding_ ([D29](../project/decision-log.md)) stored encrypted in IndexedDB. The server re-validates on sync.

### Step 5: Result — `/student/scan/step/5`

[FIG: Success overlay (status word PRESENT/LATE prominent + time), failure overlay with specific reason + [Try Again]/[Request Excuse], offline queued variant with pending count]

**Three possible outcomes**:

#### ✅ Success

- Status displayed: **PRESENT** or **LATE** (determined by _window timing_ per [D13](../project/decision-log.md))
- Time recorded
- Course name + cohort badge shown

#### ❌ Failure

- Reason displayed:
  - `duplicate` — already scanned for this _session_
  - `outside_geofence` — GPS distance > radius
  - `liveness_failed` — failed the blink/turn challenge
  - `face_mismatch` — embedding score < threshold
  - `not_enrolled` — not registered for this _course_
  - `session_expired` — scanned after `expires_at`
- **[Try Again]** — restart from Step 1
- **[Request Excuse]** — opens excuse request form (for `absent`/`rejected` paths)

#### ⏳ Offline Queued

- "Saved Offline" message with pending count
- Records sync when you regain connectivity

---

## 4. Offline Behavior

### 4.1 How Offline Scanning Works

When your device is offline:

1. Scan proceeds normally through all 5 steps using local data
2. Face verification uses your **cached embedding** (pulled on last login, [D29](../project/decision-log.md), stored encrypted in IndexedDB)
3. The attendance record is queued locally in the `sync_queue`
4. On reconnection, background sync sends the queue to the server

### 4.2 Offline Sync Status Banner

[FIG: Floating banner showing offline/syncing/partial-failure states]

| Banner                               | Meaning                                                           |
| ------------------------------------ | ----------------------------------------------------------------- |
| ✅ Synced — All caught up!           | Auto-dismisses after brief sync                                   |
| ⚠ You are offline                    | Persistent while offline; shows pending count                     |
| 🔄 Syncing… N of M                   | Progress indicator                                                |
| ⚠ 1 record rejected: session_expired | Partial failure — expired-window scan rejected                    |
| 👁 N awaiting verification (face)     | Offline scans with liveness evidence pending server re-validation |

> **Expired Offline Scans** ([D16](../project/decision-log.md)): If `scanned_at` (device time) > `expires_at`, the server rejects the scan with reason `session_expired`. Offline scans with liveness evidence are tagged "N awaiting verification (face)".

### 4.3 What to Do If Offline

- Continue scanning — your records are safely queued
- Check the **Notifications** screen for sync status
- If a scan is rejected after sync, you'll see the reason and can **[Request Excuse]**

---

## 5. Attendance History

### 5.1 History — `/student/attendance/history`

[FIG: Summary strip (Compliance %, Participation %, per-status counts), filters (Program, Year, Term, Course, Status, Date Range), sortable table (Date, Course, Section, Status, Time), [Request Excuse] on Absent/Late/Rejected rows, Export/Print buttons]

### 5.2 Summary Strip

| Metric                 | Formula                              | Meaning                                 |
| ---------------------- | ------------------------------------ | --------------------------------------- |
| **Compliance Rate**    | `present / total`                    | Strict — only on-time scans             |
| **Participation Rate** | `(present + late + excused) / total` | Broader — includes _late_ and _excused_ |

### 5.3 Filters

| Filter         | Options                                                         |
| -------------- | --------------------------------------------------------------- |
| **Program**    | Your _program_ (pre-filled)                                     |
| **Year**       | Your _year level_ (pre-filled)                                  |
| **Term**       | Select from _term structure_                                    |
| **Course**     | Your enrolled _courses_                                         |
| **Status**     | Multi-select: Present, Late, Excused, Absent, Pending, Rejected |
| **Date Range** | From / To                                                       |

### 5.4 Row Actions

- **[Request Excuse]**: Available on rows with status Absent, Late, or Rejected — opens the excuse request form ([Section 6](#6-requesting-excuses))

---

## 6. Requesting Excuses

### 6.1 When to Request an Excuse

You may request an excuse if:

- You were **Absent** and had a valid reason (illness, emergency, etc.)
- You were **Late** and want to explain why
- You were **Rejected** due to a technical issue you couldn't control

### 6.2 How to Submit a Request

[FIG: Excuse Request form with Reason text field, optional Evidence file upload, [Submit Request] button, and original status display]

1. Go to **Attendance History** (`/student/attendance/history`)
2. Find the row with status Absent, Late, or Rejected
3. Click **[Request Excuse]**
4. Fill in:
   - **Reason**: Free-text explanation
   - **Evidence** (optional): Upload a file (e.g., doctor's note, photo, receipt)
5. Submit → status changes to `pending`

### 6.3 What Happens Next

| Step                  | What You See                                                                |
| --------------------- | --------------------------------------------------------------------------- |
| Submitted             | Status shows "⏳ Pending"                                                   |
| Approved by professor | Status changes to `📝 Excused` (counts as present for _Participation Rate_) |
| Rejected by professor | Status stays as original (Absent/Late/Rejected); reason shown               |

### 6.4 Checking Request Status

- Go to **Excuse Requests** (`/student/excuse-requests`)
- Filter by `Pending` / `Approved` / `Rejected`
- Click any row to view details and evidence

> **Important**: Excuse requests require professor review ([D21](../project/decision-log.md) path c). They are not automatic. Only professors may approve/reject.

---

## 7. Schedule / Calendar

### 7.1 Schedule — `/student/schedule`

[FIG: Month grid (default) with week toggle, day cells holding color-coded course pills (time·code·room), tap-day sheet with detail cards (professor, cohort badge, status if past), "Static/read-only — syncs from admin setup" caption]

### 7.2 Viewing Your Schedule

**Month View** (default):

- Calendar grid showing the current month
- Each day cell shows **color-coded course pills** (time · code · room)

**Week View**:

- Toggle to weekly view via **[Week]** button

### 7.3 Tap-to-Detail

Click any day to see:

- All _courses_ scheduled for that day
- Each showing: _course_ name, professor name, _cohort badge_ (e.g., `BSCS·Y1`)
- If the day is in the past: status (Attended / Excused / Absent)

### 7.4 Important Notes

- **Static/read-only** — your schedule syncs from admin setup; you cannot modify it
- Schedule reflects your enrolled _courses_ from the admin roster
- If a _course_ is missing, contact your admin to check enrollment

---

## 8. Notifications

### 8.1 Notifications — `/student/notifications`

[FIG: Notification list with types (Attendance Recorded, Pending Sync, New Class Added, Session Expired), [Mark all as read] button]

**Notification Types**:

| Icon | Type                | Meaning                                 |
| ---- | ------------------- | --------------------------------------- |
| ✅   | Attendance Recorded | Scan was successfully synced            |
| ⏳   | Pending Sync (N)    | N records queued; syncs when online     |
| 📅   | New Class Added     | Admin added a _course_ to your schedule |
| ❌   | Session Expired     | A _session_ you didn't scan has expired |

---

## 9. Profile & Settings

### 9.1 Profile — `/student/profile` (Read-Only)

[FIG: Profile showing student ID, name, section, program, year level, email, face enrollment status, student number QR tile, "Changes handled by Admin" note]

**All identity fields are read-only** per [D32](../project/decision-log.md). Contact your admin for:

- Name changes
- Program/section updates
- Student ID corrections

**Face Enrollment Status** ([D28](../project/decision-log.md)):

- ✅ Enrolled — 3 photos captured, embedding stored, version tracked
- ❌ Not enrolled — contact admin for face enrollment

**My QR**: Your _student number QR_ tile — your ID card's QR is used in Step 2 of the scan flow.

### 9.2 Settings — `/student/settings`

[FIG: Settings with Appearance (theme toggle), Notifications (push/email toggles), Privacy (GPS/camera toggles), Security (Change Password, MFA, Security Question), Face Enrollment status, app version footer]

| Section             | Options                                                                                                     |
| ------------------- | ----------------------------------------------------------------------------------------------------------- |
| **Appearance**      | Theme: Light / Dark                                                                                         |
| **Notifications**   | Push (on/off), Email (on/off)                                                                               |
| **Privacy**         | Share GPS for attendance (on/off), Enable camera scanning (on/off)                                          |
| **Security**        | Change Password (policy: 8+ chars, 1 upper, 1 lower, 1 number, 1 symbol), Set Up MFA, Set Security Question |
| **Face Enrollment** | Status: Enrolled / Not enrolled — contact admin to re-enroll                                                |
| **App Version**     | Display only                                                                                                |

> **No Delete Account** option — removed per plan. If you need account removal, contact your admin.

---

## Quick Reference: Key Routes

| Task                          | Route                         |
| ----------------------------- | ----------------------------- |
| Dashboard                     | `/student/dashboard`          |
| Scan — Step 1 (Session Entry) | `/student/scan/step/1`        |
| Scan — Step 2 (ID Scan)       | `/student/scan/step/2`        |
| Scan — Step 3 (Location)      | `/student/scan/step/3`        |
| Scan — Step 4 (Face)          | `/student/scan/step/4`        |
| Scan — Step 5 (Result)        | `/student/scan/step/5`        |
| Attendance History            | `/student/attendance/history` |
| Schedule / Calendar           | `/student/schedule`           |
| Notifications                 | `/student/notifications`      |
| Profile                       | `/student/profile`            |
| Settings                      | `/student/settings`           |

---

## Troubleshooting

| Issue                        | Possible Cause                                       | Solution                                                            |
| ---------------------------- | ---------------------------------------------------- | ------------------------------------------------------------------- |
| "Invalid code" in Step 1     | Wrong code typed; _session_ expired; wrong _program_ | Check code on projector; ask professor to generate new _session_    |
| "Not enrolled" in Step 2     | Email in wrong _course_ roster                       | Contact admin to verify enrollment                                  |
| "Outside geofence" in Step 3 | Too far from classroom                               | Move closer; check classroom location with professor                |
| "Liveness failed" in Step 4  | Camera angle; lighting; did not complete challenge   | Ensure face is centered; complete all 3 challenges; retry           |
| "Face mismatch" in Step 4    | Embedding changed; not enrolled                      | Contact admin for re-enrollment if appearance changed significantly |
| "Session expired" in Step 5  | Scanned after `expires_at`                           | Cannot be undone; submit excuse request if valid reason             |
| Offline scan rejected        | `scanned_at` > `expires_at`                          | Submit excuse request; check device time is correct                 |

---

_For technical details on the scan pipeline, face embedding distribution, or offline-first sync, see the [Architecture Docs](../architecture/)._

