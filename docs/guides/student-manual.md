# Student Manual

> QR-Based Attendance System — Student Guide
>
> Covers: the scan flow, offline behavior, requesting excuses, calendar/schedule, settings limits.
>
> **Glossary**: All italicized terms are defined in the [Glossary](../project/glossary.md).
>
> **Routes** match the [Wireframes](../design/wireframes.md) screen map.

---

## Table of Contents

1. [Getting Started](#1-getting-started)
2. [Dashboard](#2-dashboard)
3. [The Scan Flow](#3-the-scan-flow)
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

> **Important**: Your _student number_ ([D19](../project/decision-log.md)) identifies your roster record, but attendance never scans a student-ID QR. Your identity comes from your signed-in account, and the scan's student-number field is only a confirmation check. Course context always comes from the verified _session_.

### 1.2 Permissions

Before scanning, you will be prompted to allow:

- **Camera**: Required for the session QR step and the face-liveness challenge
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

## 3. The Scan Flow

The scan is a guided, single-page flow at `/student/scan` (not five separate
URLs). It is **sequential** per [D27](../project/decision-log.md), as amended by
[ADR-083](../project/decision-log.md): you cannot skip stages. Student identity
always comes from your signed-in account; the student-number field is a
confirmation gate, not an identity source.

### Stage 1: Session Entry

[FIG: Session code input + Verify button; error states]

1. Look at the projector in your classroom — the _session code_ is displayed
   (e.g. `A7X-9K2M`).
2. Type the code into **Session Code (manual entry)**.
3. Click **Verify Code**.

The server verifies the code and fetches the _session_ config (windows,
duration, _geofence_ radius, classroom). On failure, a generic "Invalid code"
message is shown (no detail leak about the wrong program or an expired
_session_).

> **Session QR:** the professor's live page now displays a scannable QR code beside the session code (and offers a join link). Scanning it (camera or image upload) or opening the link auto-populates and verifies the session code, including across login redirects.

### Stage 2: Confirm Student ID

[FIG: Student ID field prefilled from the profile + Check button]

1. Your _student number_ is prefilled from your signed-in profile.
2. Correct it if needed, then click **Check**.
3. The server resolves your student record from your **account**, not from the
   number you type, and compares the number case-insensitively. A mismatch is
   rejected with `student_number_mismatch`.
4. The same call checks enrollment and whether you already scanned this
   _session_.

**Possible failures**:

- `not_enrolled` — you are not registered for this _course_
- `duplicate_scan` — this _session_ is already recorded for you
- `student_number_mismatch` — the number does not match your account
- `session_not_started` — the session has not reached its scheduled start time yet
- `session_expired` — the session's scan window has closed

### Stage 3: Session QR Camera

[FIG: QR scanner with the session QR prompt]

The app opens its camera scanner and asks you to scan the session QR shown on
the projector. A successful scan re-verifies the session and opens the liveness
challenge.

> **Note (current build):** the professor live page now renders a scannable QR code beside the session code, so the camera stage can complete directly. "No thanks, enter manually" still returns to Stage 1 for a typed code.

### Stage 4: Face Liveness

[FIG: Live camera with face detected indicator, fixed liveness challenge stepper (Blink → Turn Left → Turn Right) with progress dots, offline badge variant]

> The live camera preview is mirrored selfie-style, so "Turn Left"/"Turn Right"
> instructions point in the direction you move on screen. The underlying
> detection uses the original (unmirrored) frames.

**Liveness Challenge** ([D31](../project/decision-log.md)):

```
● ○ ○  Blink          (Step 1 of 3)
○ ● ○  Turn Left      (Step 2 of 3)
○ ○ ●  Turn Right     (Step 3 of 3)
```

1. Camera activates — detects your face
2. Follow the prompts: **Blink** → **Turn Left** → **Turn Right**
3. Progress dots advance on success
4. The app sends the evidence bundle to the server, which re-checks the
   submitted signals (the three booleans, the EAR mean, and non-empty PnP
   evidence)

> **Face matching is not implemented in this build.** The app does not compare
> your face with an enrolled embedding, and it does not use a cached embedding
> offline. It sends a placeholder match score (`1.0`); the server only applies
> its score bands to that submitted number. The liveness challenge still runs.
> See [face-enrollment.md](../architecture/face-enrollment.md) §4.2.

### Stage 5: Location Check & Result

[FIG: GPS accuracy pill, distance-to-boundary meter, pass/fail indicator, [Retry Location]; success overlay (PRESENT/LATE + time); failure overlay with reason + [Try Again]/[Request Excuse]; offline queued variant]

After liveness, the app requests your location and pre-checks the distance with
the **Haversine formula** against the _session_ (or _course_ default)
_geofence_ center + radius ([D17](../project/decision-log.md)). The server
repeats the geofence check on submit.

**If You're Outside the Geofence**:

- Move closer and retry
- If you believe the coordinates are wrong, contact your professor

> **Privacy Note**: GPS is used only for attendance validation during active scans. Your location is not tracked outside of scan sessions.

**Three possible outcomes**:

#### ✅ Success

- Status displayed: **PRESENT** or **LATE** (determined by _window timing_ per [D13](../project/decision-log.md))
- Time recorded
- Course name + cohort badge shown

#### ❌ Failure

- Reason displayed:
  - `duplicate_scan` — already scanned for this _session_
  - `outside_geofence` — GPS distance > radius
  - `liveness_failed` — failed the blink/turn challenge
  - `face_mismatch` — only reachable if a client submits a score below 0.65;
    the shipped app sends `1.0`
  - `not_enrolled` — not registered for this _course_
  - `session_expired` — scanned after `expires_at`
  - `student_number_mismatch` — the number does not match your account
  - `stub_embedding` — your face enrollment needs to be updated; contact an administrator to re-enroll
- A scan whose `status` is `rejected` shows "This attendance was submitted outside the permitted time window. Check the attendance schedule with your professor."
- **[Try Again]** — restart from Stage 1
- **[Request Excuse]** — opens the excuse request form (for `absent`/`rejected` paths)

#### ⏳ Offline Queued

- "Saved Offline" message with pending count
- Records sync when you regain connectivity
- The server re-validates the record on sync; it can still be rejected

---

## 4. Offline Behavior

### 4.1 How Offline Scanning Works

Offline support covers a scan that is already in progress when connectivity
drops. It does **not** perform face-embedding matching on the device.

1. If the session was verified earlier on this device, the app can use its
   cached config when you enter the same code offline
2. The student-ID precheck is a server call, so it is skipped offline. Your
   identity is still resolved from the signed-in token when the scan syncs
3. Complete the liveness challenge and GPS capture; if the final upload cannot
   reach the server, the evidence is queued locally in the `sync_queue`
4. On reconnection, background sync replays the queue. The server re-checks the
   session window, geofence, liveness evidence, enrollment, and duplicate

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

- If you can reach the liveness stage, continue — the record is queued safely
- Check the sync banner on the scan page or dashboard for status
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

- ✅ Enrolled — 3 photos uploaded and enrollment/version recorded; the stored
  embedding is a placeholder in this build
- ❌ Not enrolled — contact admin for face enrollment

**My QR**: A device-generated tile from your _student number_. It is **not**
scanned during attendance; identity comes from your signed-in account.

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

| Task                           | Route                         |
| ------------------------------ | ----------------------------- |
| Dashboard                      | `/student/dashboard`          |
| Scan (session entry → result)  | `/student/scan`               |
| Attendance History             | `/student/attendance/history` |
| Schedule / Calendar            | `/student/schedule`           |
| Notifications                  | `/student/notifications`      |
| Profile                        | `/student/profile`            |
| Settings                       | `/student/settings`           |

---

## Troubleshooting

| Issue                        | Possible Cause                                       | Solution                                                            |
| ---------------------------- | ---------------------------------------------------- | ------------------------------------------------------------------- |
| "Invalid code" in Stage 1        | Wrong code typed; _session_ expired; wrong _program_ | Check code on projector; ask professor to generate new _session_    |
| "Not enrolled" in Stage 2        | Email in wrong _course_ roster                       | Contact admin to verify enrollment                                  |
| "Student number mismatch"        | Typed number differs from your account               | Clear the field; use the prefilled number from your profile         |
| QR scanner has no QR to scan     | Professor UI now shows a scannable QR code beside the session code | Scan it, or open the join link / enter the code manually |
| "Outside geofence" after Stage 4 | Too far from classroom                               | Move closer; check classroom location with professor                |
| "Liveness failed" in Stage 4     | Camera angle; lighting; did not complete challenge   | Ensure face is centered; complete all 3 challenges; retry           |
| "Face mismatch" in Stage 4       | Only a non-standard client sending a low score       | The shipped app sends `1.0`; retry or report the client             |
| "Session expired" after submit   | Scanned after `expires_at`                           | Cannot be undone; submit excuse request if valid reason             |
| Offline scan rejected            | `scanned_at` > `expires_at`                          | Submit excuse request; check device time is correct                 |

---

_For technical details on the scan pipeline, face embedding distribution, or offline-first sync, see the [Architecture Docs](../architecture/)._

