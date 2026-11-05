# Wireframes — QR Attendance System

> 47 screens across 4 user roles + public pages.
> ASCII wireframes for proposal presentation.

---

## Table of Contents

1. [Public & Auth](#1-public--auth)
2. [Student](#2-student)
3. [Professor](#3-professor)
4. [Admin](#4-admin)
5. [Shared & Global](#5-shared--global)
6. [Screen Map](#6-screen-map)

---

## Design System

| Element        | Style                                                                    |
| -------------- | ------------------------------------------------------------------------ |
| Canvas         | 700×520px, white bg                                                      |
| Sidebar        | 140px, `#1e293b` bg, white text                                          |
| Primary button | `#2563eb`, white text                                                    |
| Table header   | `#f1f5f9`                                                                |
| Border radius  | 6px cards, 4px inputs                                                    |
| Status colors  | green `#16a34a`, yellow `#ca8a04`, red `#dc2626`, blue `#2563eb`         |
| Cohort badge   | `BSCS·Y1` compact chip wherever a course row could span cohorts          |
| Locked field   | Draw value inside box with 🔒 suffix, e.g. `│ CS101 — Software Eng 🔒 │` |

---

## 1. Public & Auth

### 1.1 Landing Page — `/`

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│                    ┌───────────────────────┐                    │
│                    │    Attendance System  │                    │
│                    │  QR-based · Offline   │                    │
│                    │  Anti-spoofing PWA    │                    │
│                    └───────────────────────┘                    │
│                                                                 │
│                    ┌───────────────────────┐                    │
│                    │        Login          │                    │
│                    └───────────────────────┘                    │
│                         Don't have account?                     │
│                         Register                                │
│                                                                 │
│                ──────────────────────────────────               │
│                                                                 │
│         ┌─────────┐        ┌─────────┐       ┌─────────┐        │
│         │ 📷 QR   │        │ 🛡️ Anti │       │ 🌐 Off  │        │
│         │ Scanning│        │ -Spoof  │       │ -line   │        │
│         └─────────┘        └─────────┘       └─────────┘        │
│                                                                 │
│               A PWA — no app installation required              │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Login — `/login`

```
┌─────────────────────────────────────────────────────────────────┐
│                    ┌──────────────────────────┐                 │
│                    │      Welcome Back        │                 │
│                    │   Sign in to account     │                 │
│                    │                          │                 │
│                    │  Email                 │                 │
│                    │  ┌─────────────────┐     │                 │
│                    │  │ student@...     │     │                 │
│                    │  └─────────────────┘     │                 │
│                    │                          │                 │
│                    │  Password                │                 │
│                    │  ┌─────────────────┐     │                 │
│                    │  │ ••••••••••••    │     │                 │
│                    │  └─────────────────┘     │                 │
│                    │                          │                 │
│                    │  Captcha (Turnstile,     │                 │
│                    │  invisible — auto)       │                 │
│                    │  ┌─────────────────┐     │                 │
│                    │  │ [✓ Turnstile]   │     │                 │
│                    │  └─────────────────┘     │                 │
│                    │                          │                 │
│                    │  ┌─────────────────┐     │                 │
│                    │  │     Login       │     │                 │
│                    │  └─────────────────┘     │                 │
│                    │                          │                 │
│                    │     Forgot Password?     │                 │
│                    │     ───── OR ──────      │                 │
│                    │  Don't have account?     │                 │
│                    │     Register             │                 │
│                    └──────────────────────────┘                 │
└─────────────────────────────────────────────────────────────────┘
```

> If MFA is enabled, successful login proceeds to the MFA Verification
> screen (1.6) before the dashboard loads. After 5 failed attempts the
> account is temporarily locked (rate-limiting / lockout).

### 1.3 Register — `/register`

```
┌─────────────────────────────────────────────────────────────────┐
│                    ┌──────────────────────────┐                 │
│                    │     Create Account       │                 │
│                    │                          │                 │
│                    │  Email      [________]   │                 │
│                    │  Password   [________]   │                 │
│                    │  Confirm    [________]   │                 │
│                    │  Role       [Student ▼]  │  Student or     │
│                    │                          │  Professor only │
│                    │  🔒 8+ chars · 1 upper · │                 │
│                    │     1 lower · 1 number · │                 │
│                    │     1 symbol             │                 │
│                    │                          │                 │
│                    │  ┌─────────────────┐     │                 │
│                    │  │    Register     │     │                 │
│                    │  └─────────────────┘     │                 │
│                    │                          │                 │
│                    │  Already have account?   │                 │
│                    │     Login                │                 │
│                    └──────────────────────────┘                 │
└─────────────────────────────────────────────────────────────────┘
```

**After submitting → OTP step** (same screen as 1.4 Step 3: 6-digit code,
expires in 5 min, resend allowed) → account created.

> **Claim-based registration**: the Role selector offers **Student** and
> **Professor** only. The email must match an **admin-seeded record** — the
> official email imported by the admin (students: CSV roster; professors:
> 4.4 manual/CSV entry). The role decides which table is looked up. If the
> email does not exist, is inactive, or is already claimed → registration
> fails (contact admin to be added to the roster). On match, an **OTP is
> sent to that email** to prove ownership; once verified, the account is
> created and linked to the seeded record — name, course and section are
> pulled from the record, **nothing is typed**. Email is both the
> registration lookup key and the login identity. The **student number is never
> entered at registration** — it is the roster/attendance key, not a QR code.
> **Admin accounts are never self-registered**: the first admin is seeded at
> deployment (env/seed script) and additional admins are created by an
> existing admin on the Admin Users screen (4.13). **Password policy**:
> minimum 8 characters with at least 1 uppercase, 1 lowercase, 1 number and
> 1 symbol (alphanumeric + symbol).

### 1.4 Forgot Password — `/forgot-password`

Four-step flow. Each step advances after verification.

**Step 1 — Email + Turnstile**

```
┌─────────────────────────────────────────────────────────────────┐
│                    ┌─────────────────────────┐                  │
│                    │   🔑 Forgot Password    │                  │
│                    │      Step 1 of 4        │                  │
│                    │                         │                  │
│                    │  Email:                 │                  │
│                    │  ┌─────────────────┐    │                  │
│                    │  │ your@email.com  │    │                  │
│                    │  └─────────────────┘    │                  │
│                    │                         │                  │
│                    │  Captcha (Turnstile)    │                  │
│                    │  ┌──────────┐  ┌───┐    │                  │
│                    │  │ 2D8MQA   │  │↻  │    │                  │
│                    │  └──────────┘  └───┘    │                  │
│                    │  ┌─────────────────┐    │                  │
│                    │  │ Enter code above│    │                  │
│                    │  └─────────────────┘    │                  │
│                    │                         │                  │
│                    │  ┌─────────────────┐    │                  │
│                    │  │     Continue    │    │                  │
│                    │  └─────────────────┘    │                  │
│                    │                         │                  │
│                    │     ← Back to Login     │                  │
│                    └─────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────┘
```

**Step 2 — Security Question (multiple attempts)**

```
┌─────────────────────────────────────────────────────────────────┐
│                    ┌──────────────────────────┐                 │
│                    │   🔑 Verify Identity     │                 │
│                    │      Step 2 of 4         │                 │
│                    │                          │                 │
│                    │  Answer the security     │                 │
│                    │  question set at sign-up:│                 │
│                    │                          │                 │
│                    │  "What was your first    │                 │
│                    │   pet's name?"           │                 │
│                    │  ┌─────────────────┐     │                 │
│                    │  │                 │     │                 │
│                    │  └─────────────────┘     │                 │
│                    │                          │                 │
│                    │  ⚠ 2 attempts left       │                 │
│                    │  (3 max — then lock)     │                 │
│                    │                          │                 │
│                    │  ┌─────────────────┐     │                 │
│                    │  │     Verify      │     │                 │
│                    │  └─────────────────┘     │                 │
│                    └──────────────────────────┘                 │
└─────────────────────────────────────────────────────────────────┘
```

**Step 3 — OTP**

```
┌────────────────────────────────────────────────────────────────┐
│                    ┌─────────────────────────┐                 │
│                    │   📧 One-Time Code      │                 │
│                    │      Step 3 of 4        │                 │
│                    │                         │                 │
│                    │  A 6-digit code was     │                 │
│                    │  sent to your email.    │                 │
│                    │                         │                 │
│                    │  ┌───┐ ┌───┐ ┌───┐      │                 │
│                    │  │ 4 │ │ 2 │ │ 8 │ ...  │                 │
│                    │  └───┘ └───┘ └───┘      │                 │
│                    │                         │                 │
│                    │  Expires in 05:00       │                 │
│                    │  [Resend code]          │                 │
│                    │                         │                 │
│                    │  ┌─────────────────┐    │                 │
│                    │  │     Verify      │    │                 │
│                    │  └─────────────────┘    │                 │
│                    └─────────────────────────┘                 │
└────────────────────────────────────────────────────────────────┘
```

**Step 4 — New Password + Confirm**

```
┌─────────────────────────────────────────────────────────────────┐
│                    ┌───────────────────────────┐                │
│                    │   🔐 New Password         │                │
│                    │      Step 4 of 4          │                │
│                    │                           │                │
│                    │  New Password             │                │
│                    │  ┌─────────────────┐      │                │
│                    │  │ ••••••••••••    │      │                │
│                    │  └─────────────────┘      │                │
│                    │                           │                │
│                    │  Confirm Password         │                │
│                    │  ┌─────────────────┐      │                │
│                    │  │ ••••••••••••    │      │                │
│                    │  └─────────────────┘      │                │
│                    │                           │                │
│                    │  🔒 8+ chars · 1 upper ·  │                │
│                    │     1 lower · 1 number ·  │                │
│                    │     1 symbol              │                │
│                    │                           │                │
│                    │  ✔ Must match · policy ok │                │
│                    │                           │                │
│                    │  ┌─────────────────┐      │                │
│                    │  │   Reset Password│      │                │
│                    │  └─────────────────┘      │                │
│                    └───────────────────────────┘                │
└─────────────────────────────────────────────────────────────────┘
```

> **Attempts/lockout**: the security-question step allows 3 attempts before
> the reset is aborted and the account is temporarily locked. OTP expires
> after 5 minutes and can be resent. On success the user is returned to Login.

### 1.5 MFA Setup — `/settings/security`

```
┌──────────┬───────────────────────────────────────────────────────┐
│ ☰        │  Security / Two-Factor Auth                          │
│          │───────────────────────────────────────────────────────│
│ 📷 Scan  │  ──── Two-Factor Authentication (MFA) ────            │
│ 📅 Hist  │  Require OTP at login      [●─────────────────○]      │
│ 📋 Sched │                                                       │
│ 👤 Prof  │  ┌──────────────────────────────────────────────┐     │
│          │  │ 1. Install an authenticator app              │     │
│          │  │ 2. Scan this QR / enter the secret:          │     │
│          │  │    ┌──────────┐   JBSWY3DPEB2XS2LP           │     │
│          │  │    │ ░▓▒▓░▒  │                               │     │
│          │  │    │ ▒▒░▓▓▒░ │                               │     │
│          │  │    └──────────┘                              │     │
│          │  │ 3. Enter 6-digit code to verify: [______]    │     │
│          │  └──────────────────────────────────────────────┘     │
│          │  ──── Backup Codes ────                               │
│          │  [Generate Backup Codes]   (use if app unavailable)   │
│          │                                                       │
│          │  ──── Security Question ────                          │
│          │  Question: [Select ▼]                                 │
│          │  Answer:   [________]                                 │
│          │                                                       │
│          │            [💾 Save Changes]                          │
│          └───────────────────────────────────────────────────────┘
└──────────────────────────────────────────────────────────────────┘
```

### 1.6 MFA Verification — `/login/mfa`

```
┌─────────────────────────────────────────────────────────────────┐
│                    ┌─────────────────────────┐                  │
│                    │   🔐 Two-Factor Auth    │                  │
│                    │   Enter 6-digit code    │                  │
│                    │                         │                  │
│                    │  ┌───┐ ┌───┐ ┌───┐      │                  │
│                    │  │ 7 │ │ 1 │ │ 4 │ ...  │                  │
│                    │  └───┘ └───┘ └───┘      │                  │
│                    │                         │                  │
│                    │  Code from your app /   │                  │
│                    │  backup code            │                  │
│                    │                         │                  │
│                    │  Expires in 03:00       │                  │
│                    │  [Resend code]          │                  │
│                    │                         │                  │
│                    │  ┌─────────────────┐    │                  │
│                    │  │     Verify      │    │                  │
│                    │  └─────────────────┘    │                  │
│                    │                         │                  │
│                    │  Use a backup code ·    │                  │
│                    │  Log out                │                  │
│                    └─────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Student

### 2.1 Student Dashboard — `/student/dashboard`

```
┌──────────┬──────────────────────────────────────────────────────┐
│ ☰        │  Hi, John! 👋                          🔔           │
│          │──────────────────────────────────────────────────────│
│ 📷 Scan  │  ┌──────┐  ┌──────┐  ┌────────┐                      │
│ 📅 Hist  │  │ 85%  │  │  3   │  │   42   │                      │
│ 📋 Sched │  │Rate  │  │Today │  │ Total  │                      │
│ 👤 Prof  │  └──────┘  └──────┘  └────────┘                      │
│          │                                                      │
│          │  ┌─────────────────────────────────────────────┐     │
│          │  │         📷  Scan QR Attendance              │     │
│          │  └─────────────────────────────────────────────┘     │
│          │                                                      │
│          │  ──── Today's Schedule ────                          │
│          │  🟢 CS101 — Software Eng  · 9:00 ✅ Scanned          │
│          │  🟡 MATH202 — Calculus 2  · 11:00 ⏳ Pending         │
│          │  🔴 PHYS101 — Physics 1   · 1:00  ❌ Missed          │
│          │                                                      │
│          │  ──── Recent Activity ────                           │
│          │  ✅ CS101 — 9:02 AM (Just now)                       │
│          │  ⏳ MATH202 — Pending sync                           │
│          │  📅 PHYS101 — Scheduled 1:00 PM                      │
│          └──────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 QR Scanner — `/student/scan`

> **Implementation status (2026-10-24):** the shipped scan is a single page
> with stages `entry → id → qr → liveness` plus result overlays. The
> `/student/scan/step/*` routes in this section are the original design and
> were not implemented. The ID step is a prefilled confirmation, not a
> student-ID QR scan ([ADR-083](../project/decision-log.md)); the only QR step
> reads the session code. The professor UI currently displays the session code,
> not a rendered QR.

#### 2.2a Session Entry — `/student/scan` (entry stage)

```
┌─────────────────────────────────────────────────────────────────┐
│ ← Back                                        ⚠ offline         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│                   ──── Join Session ────                        │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Session Code (manual entry)                              │  │
│  │                                                           │  │
│  │  ┌──────────────────────────────┐  ┌─────────────────┐    │  │
│  │  │ Enter code from projector    │  │   Verify Code   │    │  │
│  │  │ e.g. A7X-9K2M                │  └─────────────────┘    │  │
│  │  └──────────────────────────────┘                         │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ──── Verifying ──── (spinner after input)                      │
│  ✅ Session found → proceeds to ID confirmation                 │
│  ❌ Invalid / expired / wrong program → error (no detail leak)  │
└─────────────────────────────────────────────────────────────────┘
```

> **Session QR payload** (D18): `{\"v\":1,\"code\":\"A7X-9K2M\",\"offering\":123,
> \"radius\":30,\"pw\":5,\"lw\":10}` — **illustrative** values only. `radius` mirrors
> the session's `classroom_radius_meters`; the system default is **50 m** (DB default),
> configurable per offering/session. The API returns this payload, but the current
> professor UI does not render it as a QR image.
> No student-ID QR is used; the number is prefilled from the signed-in profile.

#### 2.2b ID Confirmation — `/student/scan` (id stage)

```
┌─────────────────────────────────────────────────────────────────┐
│ ← Back                                        ⚠ offline         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ✅ Session verified                                            │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ CS101 — Software Eng    BSCS·Y1 🔒                        │  │
│  │ Scan window: Present 5m + Late 10m                        │  │
│  │ Expires at: 10:15 AM                                      │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ──── Step 2: Confirm Your Student ID ────                      │
│                                                                 │
│  ┌──────────────────────────────┐  ┌─────────────────┐          │
│  │ 24-2111 (prefilled)          │  │      Check      │          │
│  └──────────────────────────────┘  └─────────────────┘          │
│                                                                 │
│  Prefilled from your signed-in profile — correct it if needed.  │
│  The server resolves the student from the account, not this      │
│  field, and compares the number case-insensitively.              │
│  Checks: enrollment for this course + duplicate-scan             │
│                                                                 │
│  ✅ Match → session-QR camera stage                              │
│  ❌ Mismatch / not enrolled / already scanned → error shown      │
└─────────────────────────────────────────────────────────────────┘
```

> After ID confirmation the shipped page opens a **session-QR camera** stage.
> The professor screen shows the code only, so this is a known UI gap; the API
> accepts a typed session code, and the QR step is session discovery, never
> student identity.

#### 2.2c Location Check — `/student/scan/step/3` (design route, not shipped)

```
┌─────────────────────────────────────────────────────────────────┐
│ ← Back                                        ⚠ offline         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│         ✅ Session verified · ✅ Student identified             │
│                                                                 │
│               ──── Location Check ────                          │
│         (server re-validates on submit)                         │
│                                                                 │
│              ┌─────────────────────────────┐                    │
│              │       📍 GPS                │                    │
│              │                             │                    │
│              │  Accuracy: ±5m              │                    │
│              │  Distance to boundary: 12m  │                    │
│              │  Required radius: 30m       │                    │
│              │                             │                    │
│              │  ✅ WITHIN GEOFENCE         │                    │
│              └─────────────────────────────┘                    │
│                                                                 │
│              🟢 GPS: High (5m)     📍 CS Lab 101                │
│                                                                 │
│                    [Retry Location]                             │
│                                                                 │
│               Proceeding…                                        │
└─────────────────────────────────────────────────────────────────┘
```

> GPS uses Haversine formula vs offering/session radius. If session has
> override coordinates (D17), those are used; otherwise offering defaults.
> `Required radius: 30m` in the mock is an example professor setting — the system
> default (`classroom_radius_meters`) is **50 m** (configurable when opening a session).
> In the shipped UI, the client captures GPS after the liveness challenge and the
> server repeats the geofence check on submit.

#### 2.2d Face Liveness — `/student/scan/step/4` (design route, not shipped)

```
┌─────────────────────────────────────────────────────────────────┐
│ ← Back                                        ⚠ offline         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ✅ Session verified · ✅ Student identified · ✅ Location OK   │
│                                                                 │
│  ──── Step 4: Face Liveness ────                                │
│                                                                 │
│                          🎥 (live)                              │
│                          Face detected ✔                        │
│                                                                 │
│  ┌──────────────────────────────────────────────┐               │
│  │  Liveness Challenge (fixed sequence)         │               │
│  │                                              │               │
│  │  ● ○ ○  Blink                                │               │
│  │  ○ ● ○  Turn Left                            │               │
│  │  ○ ○ ●  Turn Right                           │               │
│  │                                              │               │
│  │  Challenge 1 of 3 · auto-advances on success │               │
│  └──────────────────────────────────────────────┘               │
│                                                                 │
│  ──── Submitting evidence… ────                                 │
│  Server re-checks the liveness signals.                         │
│  No face-embedding comparison is performed.                     │
│                                                                 │
│  ✅ Evidence accepted → result overlay                          │
│  ❌ Liveness check fails → rejection                            │
│                                                                 │
│  📱 Offline badge: \"Evidence saved — will verify after sync\"  │
└─────────────────────────────────────────────────────────────────┘
```

> **Liveness sequence is fixed** (blink → turn left → turn right, D31).
> MediaPipe Face Mesh runs WASM client-side, and the server re-checks the
> submitted EAR/PnP signals. **Face matching is not implemented**: the client
> sends a live face image for server-side embedding comparison, and the stored enrollment
> embedding is a stub. There is no offline embedding comparison (D30 is design
> only). See [face-enrollment.md](../architecture/face-enrollment.md) §4.2.

#### 2.2e Result — `/student/scan/step/5` (design route, not shipped)

```
┌────────────────────────────────────────────────────────────────┐
│                                                                │
│  ┌─── SUCCESS ────────────────────────────┐                    │
│  │                                        │                    │
│  │              ✅ (large)                │                    │
│  │                                        │                    │
│  │         Attendance Recorded            │                    │
│  │          PRESENT                       │                    │
│  │          9:02 AM                       │                    │
│  │                                        │                    │
│  │    CS101 — Software Eng                │                    │
│  │    BSCS·Y1 🔒                          │                    │
│  │    Live · GPS + Liveness verified      │                    │
│  │                                        │                    │
│  └────────────────────────────────────────┘                    │
│                                                                │
│  ┌─── FAILURE ────────────────────────────┐                    │
│  │                                        │                    │
│  │              ❌ (large)                │                    │
│  │                                        │                    │
│  │         Attendance Rejected            │                    │
│  │                                        │                    │
│  │    Reason: outside_geofence            │                    │
│  │    (or: duplicate_scan,               │                    │
│  │     liveness_failed, face_mismatch,   │                    │
│  │     not_enrolled, session_expired)    │                    │
│  │                                        │                    │
│  │    ┌──────────┐ ┌───────────────┐      │                    │
│  │    │Try Again │ │Request Excuse │      │                    │
│  │    └──────────┘ └───────────────┘      │                    │
│  └────────────────────────────────────────┘                    │
│                                                                │
│  ┌─── OFFLINE QUEUED ─────────────────────┐                    │
│  │                                        │                    │
│  │              ⏳ (large)                │                    │
│  │                                        │                    │
│  │         Saved Offline                  │                    │
│  │         2 records pending sync         │                    │
│  │                                        │                    │
│  └────────────────────────────────────────┘                    │
└────────────────────────────────────────────────────────────────┘
```

> **Status is determined by window timing** (D13): scans within
> `present_window_minutes` → present; within `late_window_minutes`
> after that → late; no-scan students become absent when session expires.
> Offline scans store device `scanned_at`; on sync the server validates
> against the session window. Expired offline scans → rejected with
> reason `session_expired` (D16).

### 2.3 Permission Prompt (Modal)

> **Incorporated into 2.2a.** Camera/GPS permissions are requested
> before entering the scan flow.

### 2.4 Face Liveness Challenge (overlay)

> **Incorporated into 2.2d.** The fixed liveness sequence (blink →
> turn left → turn right) appears as Step 4 of the scan flow.

### 2.5 Scan Success Overlay

> **Incorporated into 2.2e.** Success, failure, and offline-queued
> results are all rendered as Step 5 of the scan flow.

### 2.6 Scan Failure Overlay

> **Incorporated into 2.2e.** Failure reasons follow D15: duplicate,
> outside_geofence, liveness_failed, face_mismatch, not_enrolled,
> session_expired.

### 2.7 Attendance History — `/student/history`

```
┌──────────┬───────────────────────────────────────────────────────┐
│ ☰        │  Attendance History                                  │
│          │───────────────────────────────────────────────────────│
│ 📷 Scan  │  ┌──────────────────────────────────────────────┐     │
│ 📅 Hist  │  │  85%  Compliance  ·  92%  Participation      │     │
│ 📋 Sched │  │  Present: 14  Late: 2  Excused: 1            │     │
│ 👤 Prof  │  │  Absent: 3  Pending: 0  Rejected: 0          │     │
│          │  └──────────────────────────────────────────────┘     │
│          │                                                       │
│          │  Program: [All ▼] Year: [All ▼] Term: [All ▼]         │
│          │  Course: [All ▼] Status: [Present,Late,Absent,        │
│          │  Excused,Rejected ▼]                                  │
│          │  Date: From [Jul 01 ▼]  To [Jul 31 ▼]  [🔍 Apply]     │
│          │                                                       │
│          │  ┌──────┬──────────┬───────┬──────────┬────────┐      │
│          │  │Date ⇅│Course ▲  │Section│Status ⇅  │Time ⇅  │      │
│          │  ├──────┼──────────┼───────┼──────────┼────────┤      │
│          │  │Jul28 │  CS101   │  A    │✅ Present│ 9:02   │      │
│          │  │Jul28 │ MATH202  │  A    │⏰ Late   │11:12   │      │
│          │  │Jul25 │  CS101   │  A    │📝Excused │  —     │      │
│          │  │Jul24 │ PHYS101  │  A    │❌ Absent │  —     │      │
│          │  │      │          │       │[Req Excuse]│      │      │
│          │  │Jul23 │ MATH202  │  A    │⛔Rejected│  —     │      │
│          │  │      │          │       │[Req Excuse]│      │      │
│          │  └──────┴──────────┴───────┴─────────┴─────────┘      │
│          │  < 1 2 3 >   [🖨 Print]  [📥 Export CSV]              │
│          │                                                       │
│          │  [Request Excuse] shown for Absent/Late/Rejected rows │
│          └───────────────────────────────────────────────────────┘
└──────────────────────────────────────────────────────────────────┘
```

> **Summary strip** shows Compliance Rate (present / total, D36) and
> Participation Rate ((present + late + excused) / total, D36) as
> prominent percentages. **Request Excuse** button appears on rows
> where status is Absent, Late, or Rejected — opens the student
> excuse request form (D21 path c) with evidence upload.

> **Sortable**: every column header (Date, Course, Section, Status, Time) is clickable
> to toggle ascending ⇅ / descending order; the active column shows an ▲/▼
> indicator. **Date-range + category filters** narrow the dataset; results are
> printable or exportable as CSV.

### 2.8 Schedule — `/student/schedule`

```
┌──────────┬──────────────────────────────────────────────────────┐
│ ☰        │  My Schedule                   [Month ▾] [Week ▾]   │
│          │──────────────────────────────────────────────────────│
│ 📷 Scan  │  ◄  Jul 2026  ►                                      │
│ 📅 Hist  │  ┌──────┬──────┬──────┬──────┬──────┬──────┬──────┐  │
│ 📋 Sched │  │ Mon  │ Tue  │ Wed  │ Thu  │ Fri  │ Sat  │ Sun  │  │
│ 👤 Prof  │  ├──────┼──────┼──────┼──────┼──────┼──────┼──────┤  │
│          │  │9:00  │      │9:00  │      │9:00  │      │      │  │
│          │  │CS101 │      │CS101 │      │CS101 │      │      │  │
│          │  │Lab101│      │Lab101│      │Lab101│      │      │  │
│          │  │ 🟢   │      │ 🟢   │      │ 🔴   │      │      │  │
│          │  ├──────┼──────┼──────┼──────┼──────┼──────┼──────┤  │
│          │  │      │11:00 │      │11:00 │      │      │      │  │
│          │  │      │MATH  │      │MATH  │      │      │      │  │
│          │  │      │ R203 │      │ R203 │      │      │      │  │
│          │  │      │ 🟢   │      │ ⏰   │      │      │      │  │
│          │  ├──────┼──────┼──────┼──────┼──────┼──────┼──────┤  │
│          │  │13:00 │      │13:00 │      │13:00 │      │      │  │
│          │  │PHYS  │      │PHYS  │      │PHYS  │      │      │  │
│          │  │L301  │      │L301  │      │L301  │      │      │  │
│          │  │ 🟢   │      │ ❌   │      │ 📝   │      │      │  │
│          │  └──────┴──────┴──────┴──────┴──────┴──────┴──────┘  │
│          │                                                      │
│          │  Tap day → sheet with detail cards:                  │
│          │  ┌────────────────────────────────────────┐          │
│          │  │ CS101 — Software Eng                   │          │
│          │  │ Prof. Smith · BSCS·Y1 🔒               │          │
│          │  │ Status: ✅ Attended (9:02 AM)          │          │
│          │  ├────────────────────────────────────────┤          │
│          │  │ MATH202 — Calculus 2                   │          │
│          │  │ Prof. Garcia · BSCS·Y1 🔒              │          │
│          │  │ Status: ⏰ Late (11:12 AM)             │          │
│          │  └────────────────────────────────────────┘          │
│          │                                                      │
│          │  📍 All classes in Main Building                     │
│          │  Static/read-only — syncs from admin setup           │
│          └──────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

> **Month grid default** with week toggle. Day cells hold color-coded
> course pills (time·code·room). Tap-day sheet shows detail cards
> with professor, program/year badge, and status if past
> (attended/excused/absent). Static/read-only — syncs from admin setup.

### 2.9 Notifications — `/student/notifications`

```
┌──────────┬──────────────────────────────────────────────────────┐
│ ☰        │  Notifications                                      │
│          │──────────────────────────────────────────────────────│
│ 📷 Scan  │  ┌────────────────────────────────────────────┐      │
│ 📅 Hist  │  │ ✅ Attendance Recorded                     │      │
│ 📋 Sched │  │   CS101 — Jul 29 · 2 min ago               │      │
│ 👤 Prof  │  └────────────────────────────────────────────┘      │
│          │  ┌────────────────────────────────────────────┐      │
│          │  │ ⏳ Pending Sync (3)                        │      │
│          │  │   Records will sync when online · 5min     │      │
│          │  └────────────────────────────────────────────┘      │
│          │  ┌────────────────────────────────────────────┐      │
│          │  │ 📅 New Class Added                         │      │
│          │  │   ECE101 added to schedule · 1 day ago     │      │
│          │  └────────────────────────────────────────────┘      │
│          │  ┌────────────────────────────────────────────┐      │
│          │  │ ❌ Session Expired                         │      │
│          │  │   MATH202 session ended · 2 days ago       │      │
│          │  └────────────────────────────────────────────┘      │
│          │            [Mark all as read]                        │
│          └──────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

### 2.10 Student Profile — `/student/profile`

```
┌──────────┬──────────────────────────────────────────────────────┐
│ ☰        │  My Profile                                         │
│          │──────────────────────────────────────────────────────│
│ 📷 Scan  │                   👤 (avatar)                        │
│ 📅 Hist  │                                                      │
│ 📋 Sched │  Student ID:   2021-01234                            │
│ 👤 Prof  │  Name:         John A. Doe                           │
│          │  Middle Name:  A.                                    │
│          │  Section:      A                                     │
│          │  Program:      BSCS (BS Computer Science)            │
│          │  Year Level:   1st Year                              │
│          │  Email:        john.doe@university.edu               │
│          │                                                      │
│          │  ──── Face Enrollment ────                           │
│          │  Status: ✅ Enrolled (3 photos, v2)                  │
│          │  Enrolled: Jul 15, 2026                              │
│          │                                                      │
│          │  ──── My QR ────                                     │
│          │  ┌──────────┐                                        │
│          │  │ ░▓▒▓░▒  │  24-2111                                │
│          │  │ ▒▒░▓▓▒░ │  (student number QR)                    │
│          │  └──────────┘                                        │
│          │                                                      │
│          │  ┌──────────────────────────────────────────┐        │
│          │  │  Changes handled by Admin                │        │
│          │  └──────────────────────────────────────────┘        │
│          │                                                      │
│          │  Account: Jun 2026 · Scans: 42                       │
│          └──────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

> **Read-only profile** (D32): all identity fields are admin-managed.
> No edit button — note says \"Changes handled by Admin.\"
> **Face enrollment status** (D28): shows enrolled/not enrolled with
> enrollment date. **QR tile** shows the student number QR (D19); it is a
> display-only profile tile and is never scanned during attendance.

### 2.11 Student Settings — `/student/settings`

```
┌──────────┬──────────────────────────────────────────────────────┐
│ ☰        │  Settings                                           │
│          │──────────────────────────────────────────────────────│
│ 📷 Scan  │  ──── Appearance ────                                │
│ 📅 Hist  │  Theme:   [Light] [Dark]                             │
│ 📋 Sched │                                                      │
│ 👤 Prof  │  ──── Notifications ────                             │
│          │  Push notifications         [●─────────────────○]    │
│          │  Email notifications        [○─────────────────●]    │
│          │                                                      │
│          │  ──── Privacy ────                                   │
│          │  Share GPS for attendance   [●─────────────────○]    │
│          │  Enable camera scanning     [●─────────────────○]    │
│          │                                                      │
│          │  ──── Security ────                                  │
│          │  [Change Password]                                   │
│          │  Password policy: 8+ chars, 1 upper, 1 lower,        │
│          │  1 number, 1 symbol                                  │
│          │                                                      │
│          │  ──── Two-Factor Auth ────                           │
│          │  [Set Up MFA]                                        │
│          │  Status: Not configured                              │
│          │                                                      │
│          │  ──── Security Question ────                         │
│          │  [Set Security Question]                             │
│          │                                                      │
│          │  ──── Face Enrollment ────                           │
│          │  Status: ✅ Enrolled (contact admin to re-enroll)    │
│          │                                                      │
│          │  App version: 1.0.0                                  │
│          └──────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

> **No Delete Account** — removed per plan. Face enrollment status line
> added (D28). Security section includes Change Password, MFA setup,
> Security Question.

---

## 3. Professor

### 3.1 Professor Dashboard — `/professor/dashboard`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Professor Dashboard                    🔔        │
│────────────│────────────────────────────────────────────────────│
│ 📊 Dash    │  ┌──────┐  ┌──────┐  ┌────────┐                    │
│ 📷 Live    │  │ 3/5  │  │ 120  │  │  92%   │                    │
│ 📅 History │  │Sess. │  │Stud. │  │ Avg    │                    │
│ 📋 Reports │  └──────┘  └──────┘  └────────┘                    │
│ 👥 Courses │                                                    │
│ ⚙️ Settings│  ──── Today's Sessions ────                        │
│            │  🟢 CS101 — Software Eng  BSCS·Y1 🔒               │
│            │     18/30 scanned  [View Live]                     │
│            │  🟡 MATH202 — Calculus 2  BSIT·Y1 🔒               │
│            │     Not yet started  [Open Session]                │
│            │                                                    │
│            │  ──── Quick Actions ────                           │
│            │  [+ New Session]  [📄 Export Report]               │
│            └────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Open Session — `/professor/sessions/create`

> **3.2 is split into two variants** per D11: locked (from My Courses)
> and selector (from Dashboard "New Session").

#### 3.2a From My Courses (Locked) — `/professor/sessions/create?course={id}`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Open New Session                                 │
│────────────│────────────────────────────────────────────────────│
│ 📊 Dash    │  Course:                                           │
│ 📷 Live    │  ┌─────────────────────────────────────────┐       │
│ 📅 History │  │ CS101 — Software Engineering 🔒         │       │
│ 📋 Reports │  │ BSCS·Y1 · Section A                     │       │
│ 👥 Courses │  │ MWF 9:00–10:30 · Lab 101                │       │
│ ⚙️ Settings│  └─────────────────────────────────────────┘       │
│            │                                                    │
│            │  Geofence Radius: [10m] [20m] [30m] [50m] [100m]   │
│            │                                                    │
│            │  Duration (minutes): [90]                          │
│            │  Helper: expires min(now + 90m, 10:30 scheduled)   │
│            │                                                    │
│            │  Present window: [5] min (default from course)     │
│            │  Late window: [10] min (default from course)       │
│            │  ┌─────────────────────────────────────────┐       │
│            │  │ Present __ + Late __ ≤ Duration __      │       │
│            │  │       5    +    10    ≤      90    ✅   │       │
│            │  └─────────────────────────────────────────┘       │
│            │                                                    │
│            │  Classroom override: [________] (blank = course)   │
│            │                                                    │
│            │  HMAC Preview:  A7X-9K2M                           │
│            │                                                    │
│            │  ┌─────────────────────────────────────────┐       │
│            │  │     🔐 Generate Session Code            │       │
│            │  └─────────────────────────────────────────┘       │
│            └────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

> **Locked variant** (D11): course is fixed from My Courses card — no
> selector. Window math block (§9) shows live validation P+L≤duration.
> Duration prefilled = scheduled length. Optional classroom override
> overrides offering defaults when set (D17).

#### 3.2b From Dashboard (Selector) — `/professor/sessions/create`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Open New Session                                 │
│────────────│────────────────────────────────────────────────────│
│ 📊 Dash    │  Select Course:                                    │
│ 📷 Live    │  ┌──────────────────────────────────────────┐      │
│ 📅 History │  │ CS101 — Software Eng  BSCS·Y1 ▼          │      │
│ 📋 Reports │  │(professor's active assignments this term)│      │
│ 👥 Courses │  └──────────────────────────────────────────┘      │
│ ⚙️ Settings│                                                    │
│            │  (same form as 3.2a from here down)                │
│            └────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

> **Selector variant** (D11): course dropdown limited to professor's
> active assignments this term. Form identical to 3.2a below the selector.
> **Window defaults** come from the offering (D14) and are overridable per
> session. **Duration expiry** (D12): `expires_at = min(created_at +
duration_minutes, scheduled_end_time)`.

### 3.3 Active Session / Projector Mode — `/professor/sessions/active/[id]`

```
┌─────────────────────────────────────────────────────────────────┐
│ ← Back          {session.status === 'closed' ? 'Closed' : 'Active'}: CS101 — Software Eng        [Close]     │
│                  BSCS·Y1 · Section A                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│              ┌───────────────────────────────────────────┐      │
│              │    Session Code — Show on projector       │      │
│              │          A 7 X - 9 K 2 M                  │      │
│              │        (large, projector-ready)           │      │
│              └───────────────────────────────────────────┘      │
│                                                                 │
│  ┌──────────────────────┐  ┌──────────────────────┐             │
│  │ ⏱ Scan window 14:32  │  │ 🏁 Class ends 10:30  │             │
│  └──────────────────────┘  └──────────────────────┘             │
│                                                                 │
│    ┌────────┐          ┌────────┐          ┌────────┐           │
│    │   30   │          │   18   │          │   12   │           │
│    │Enrolled│          │Scanned │          │Remaining           │
│    └────────┘          └────────┘          └────────┘           │
│                                                                 │
│  Status: ✅Present  ⏰Late  📝Excused  ⏳Pending  ❌Absent      │
│                                                                 │
│  ──── Live Feed (auto-refresh 3s) ────                          │
│  ┌──────┬──────────────┬──────────┬─────────┬────────┐          │
│  │ Time⇅│   Name ⇅     │ Status ⇅ │  GPS ⇅  │ Action │          │
│  ├──────┼──────────────┼──────────┼─────────┼────────┤          │
│  │09:01 │ Alice Santos │ ✅Present│ 🟢 In   │        │          │
│  │09:02 │ Bob Cruz     │ ✅Present│ 🟢 In   │        │          │
│  │09:03 │ Carol Tan    │ ⏳ Pend  │ 🔴 Out  │        │          │
│  │09:04 │ Emma Lim     │ ✅Present│ 🟢 In   │        │          │
│  │09:05 │ Frank Diaz   │ ⏰ Late  │ 🟢 In   │[📝 Exc]│          │
│  └──────┴──────────────┴──────────┴─────────┴────────┘          │
│                                                                 │
│  ┌────────────────────────────────────────────────────────┐     │
│  │ [📝 Excuse All Absent]   reason: [________________]    │     │
│  └────────────────────────────────────────────────────────┘     │
│                                                                 │
│  After duration expiry:                                         │
│  ┌────────────────────────────────────────────────────────┐     │
│  │ ⚠ Scanning closed — waiting for offline syncs          │     │
│  │   3 records pending sync                               │     │
│  └────────────────────────────────────────────────────────┘     │
│                                                                 │
│           [📥 Export Current]  [🖨 Print]  [📋 View All]        │
└─────────────────────────────────────────────────────────────────┘
```

> **Dual timers** (§9): stacked pills showing scan window countdown and
> class scheduled end time. **Present/Late windows** per D13: scans
> within `present_window_minutes` → present; within `late_window_minutes`
> after that → late; no-scan students become absent when session expires.
> Constraint: present_window_minutes + late_window_minutes ≤ duration_minutes.
> **[📝 Excuse]** per-row opens quick-excuse modal for absent/late
> students (D21 path a). **[Excuse All Absent]** (D23) applies bulk
> excuse with required reason. **After duration expiry** (D12): banner
> shows "Scanning closed" while waiting for offline syncs.
>
> **Closed-session behavior** (session.status === 'closed'): the header
> label reads "Closed:" instead of "Active:", the scan-window countdown
> freezes at 00:00:00 and the class-end timer shows the actual end time
> from `expires_at` (falls back to scheduled end time) instead of a
> running countdown, the [Close] button is disabled, and the skeleton
> gate no longer blocks rendering on `classRemainingSeconds`.
>
> The page now also exposes four collapsible `<details>` panels —
> **General session information**, **Schedule and time**, **Location**,
> **Attendance overview** — surfacing course/program/year/academic-year/
> semester/type/status/duration/windows, schedule & override provenance,
> classroom/geofence details, a `rejected` count, and compliance/
> participation rates. Counts include `rejected`.


### 3.4 Professor Attendance List — `/professor/attendance`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Attendance Records                               │
│────────────│────────────────────────────────────────────────────│
│ 📊 Dash    │  Course:[CS101 ▼] Section:[All ▼]                  │
│ 📷 Live    │  Session:[All ▼] Status:[All ▼]                    │
│ 📅 History │  Date: From [Jul 01 ▼] To [Jul 31 ▼] [🔍 Apply]    │
│ 📋 Reports │  ┌──────┬──────────────┬───────┬──────────┬──────┐ │
│ 👥 Courses │  │ Date⇅│ Student ⇅    │Section│Status ⇅  │Time ⇅│ │
│ ⚙️ Settings│  ├──────┼──────────────┼───────┼──────────┼──────┤ │
│            │  │Jul29 │ Alice Santos │  A    │✅Present │ 09:01│ │
│            │  │Jul29 │ Bob Cruz     │  A    │✅Present │ 09:02│ │
│            │  │Jul29 │ Carol Tan    │  B    │❌Absent  │  —   │ │
│            │  │      │              │       │[📝Excuse]│      │ │
│            │  │Jul28 │ Dave Reyes   │  A    │⏰ Late   │ 08:55│ │
│            │  │Jul28 │ Emma Lim     │  A    │📝Excused │  —   │ │
│            │  │      │              │       │[✏️ Edit] │      │ │
│            │  │Jul28 │ Frank Diaz   │  B    │⛔Rejected│  —   │ │
│            │  └──────┴──────────────┴───────┴──────────┴──────┘ │
│            │  < 1 2 3 >  [🖨 Print]  [📥 Export]  [📷 View Live]│
│            │  Legend: ✅ Present ⏰ Late 📝 Excused ❌ Absent   │
│            │          ⏳ Pending ⛔ Rejected                    │
│            └────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

> **Section filter** (D2) populated from roster. **Status filter** includes
> Late/Excused/Rejected per D15. **[📝 Excuse]** per-row opens quick-excuse
> modal for absent/late rows (D21 path a). **[✏️ Edit]** appears on excused
> rows to modify the existing excuse. Column headers are sortable (click
> to toggle ▲/▼). Filters combine category (Course / Section / Session /
> Status) with a **date-range** (From–To).

### 3.5 Professor Session History — `/professor/sessions/history`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Session History                                  │
│────────────│────────────────────────────────────────────────────│
│ 📊 Dash    │  Course: [All Courses ▼]  Section: [All ▼]         │
│ 📷 Live    │  Date: [Jul 01→Jul 31 ▼]                           │
│ 📅 History │  ┌──────┬──────────┬───────┬──────────────┬──────┐ │
│ 📋 Reports │  │ Date ⇅│  Code ⇅  │Section│ P / L / A ⇅ │ Rate▲│ │
│ 👥 Courses │  ├──────┼──────────┼───────┼──────────────┼──────┤ │
│ ⚙️ Settings│  │Jul29 │ A7X-9K2M │   A   │ 18 / 5 / 7   │ 60%  │ │
│            │  │Jul28 │ B4Y-3L7N │   A   │ 28 / 1 / 1   │ 93%  │ │
│            │  │Jul25 │ C8Z-5P1Q │   B   │ 25 / 3 / 2   │ 83%  │ │
│            │  │Jul24 │ D2W-8R4T │   A   │ 30 / 0 / 0   │ 100% │ │
│            │  └──────┴──────────┴───────┴──────────────┴──────┘ │
│            │  Average: 84% over 12 sessions                     │
│            │  < 1 2 3 >   [🖨 Print]  [📥 Export CSV]           │
│            │  Click row → full attendance detail                │
│            │                                                    │
│            │  Rate tooltip:                                     │
│            │  Compliance: present / total (default)             │
│            │  Participation: (present+late+excused) / total     │
│            └────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

> **Section filter** (D2) added. Rate column shows compliance rate by
> default; tooltip reveals participation rate (D36). Column headers
> sortable (toggle ▲/▼). Supports date-range + course + section
> filtering, printing, and CSV export.

### 3.6 Professor Courses — `/professor/courses`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  My Courses                                       │
│────────────│────────────────────────────────────────────────────│
│ 📊 Dash    │  ──── BSCS 🔽 ────                                 │
│ 📷 Live    │  ┌─── CS101 — Software Engineering (3u) ──────┐    │
│ 📅 History │  │  BSCS·Y1 🔒  · Primary                     │    │
│ 📋 Reports │  │  MWF 9:00-10:30 · Lab 101 · 30 students    │    │
│ 👥 Courses │  │  [🔐 Open Session] [📊 Reports]            │    │
│ ⚙️ Settings│  └────────────────────────────────────────────┘    │
│            │                                                    │
│            │  ┌─── MATH202 — Calculus 2 (4u) ──────────────┐    │
│            │  │  BSCS·Y1 🔒  · Primary                     │    │
│            │  │  TTH 11:00-12:30 · Rm 203 · 35 students    │    │
│            │  │  [🔐 Open Session] [📊 Reports]            │    │
│            │  └────────────────────────────────────────────┘    │
│            │                                                    │
│            │  ──── BSIT 🔽 ────                                 │
│            │  ┌─── CS101 — Software Engineering (3u) ──────┐    │
│            │  │  BSIT·Y1 🔒  · Assistant                   │    │
│            │  │  MWF 9:00-10:30 · Lab 101 · 25 students    │    │
│            │  │  [🔐 Open Session] [📊 Reports]            │    │
│            │  └────────────────────────────────────────────┘    │
│            │                                                    │
│            │  Total: 3 courses across 2 programs                │
│            │  Active session: 1                                 │
│            └────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

> **Program-grouped** cards (D6): courses appear under collapsible
> Program headers with **cohort badges** (§9). Each card shows program·year
> badge, **units** (e.g. `3u`), schedule, room, student count, and
> **primary/assistant** indicator. **[🔐 Open Session]** opens the
> locked variant (3.2a). **[📊 Reports]** deep-links pre-filtered to that
> course.

### 3.7 Professor Reports — `/professor/reports`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Attendance Reports                               │
│────────────│────────────────────────────────────────────────────│
│ 📊 Dash    │  Program: [All ▼]  Year: [All ▼]                   │
│ 📷 Live    │  Course: [All Courses ▼]  Section: [All ▼]         │
│ 📅 History │  Granularity: [Daily ▾] [Weekly ▾] [Monthly ▾]     │
│ 📋 Reports │                                                    │
│ 👥 Courses │  ┌────────────┬──────────────┬──────────┐          │
│ ⚙️ Settings│  │All Courses │ Per-Course   │ Trends   │          │
│            │  │ (default)  │ Comparison   │          │          │
│            │  ├────────────┼──────────────┼──────────┤          │
│            │  │            │              │          │          │
│            │  └────────────┴──────────────┴──────────┘          │
│            │                                                    │
│            │  ──── All Courses Tab ──── (aggregate)             │
│            │  ┌──────────────────────────────────────────┐      │
│            │  │  95% ██ 88% ██ 72% ██ 90% ██ 62% ██      │      │
│            │  │  Mon  Tue  Wed  Thu  Fri                 │      │
│            │  └──────────────────────────────────────────┘      │
│            │  Average: 81% · Total sessions: 24                 │
│            │  Across all assigned courses                       │
│            │                                                    │
│            │  ──── Per-Course Comparison Tab ────               │
│            │  BSCS·Y1 CS101  ████████████░░░  88%               │
│            │  BSIT·Y1 CS101  █████████████░░  91%               │
│            │  BSCS·Y1 MATH202 ██████████░░░░  72%               │
│            │  (same course shown once per cohort — D6)          │
│            │                                                    │
│            │  ──── Trends Tab ────                              │
│            │  ┌──────────────────────────────────────────┐      │
│            │  │  Metric: [Compliance ▾] [Participation▾] │      │
│            │  │  95%┤   ╭──╮                             │      │
│            │  │  85%┤╭──╯  ╰──╮  ╭──╮                    │      │
│            │  │  75%┤╯        ╰──╯  ╰──                  │      │
│            │  │     └──┬──┬──┬──┬──┬──┬──                │      │
│            │  │      Mon Tue Wed Thu Fri Sat             │      │
│            │  └──────────────────────────────────────────┘      │
│            │                                                    │
│            │  [📥 Download CSV]   [📄 Download PDF]             │
│            └────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

> **Three tabs** (D37): All Courses (aggregate bars per day/week/month
> across all assigned courses with avg line), Per-Course Comparison
> (grouped bars — one course shown once per cohort it spans), Trends
> (multi-series line with metric toggle Compliance/Participation).
> Program/Year/Course/Section + granularity filters shared across tabs.
> Export CSV/PDF of current filter set.

### 3.8 Professor Export — `/professor/attendance/export`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Export Attendance                                │
│────────────│────────────────────────────────────────────────────│
│ 📊 Dash    │  Course: [CS101 — Software Engineering ▼]          │
│ 📷 Live    │  Date Range:                                       │
│ 📅 History │  From: [Jul 01, 2026 ▼]  To: [Jul 29, 2026 ▼]      │
│ 📋 Reports │  Format: ○ CSV  ● PDF  ○ Excel  ○ Print            │
│ 👥 Courses │  Include:                                          │
│ ⚙️ Settings│  ☑ Student ID  ☑ Name  ☑ Timestamp                 │
│            │  ☑ GPS Coordinates  ☐ Liveness Status              │
│            │  Status filter: ☑Present ☑Late ☑Excused            │
│            │                ☑Absent  ☑Pending ☑Rejected         │
│            │                                                    │
│            │  ┌─────────────────────────────────────────┐       │
│            │  │         📥 Download Report              │       │
│            │  └─────────────────────────────────────────┘       │
│            └────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

> Status field list includes excused and late (D15) in addition to
> present, absent, pending, and rejected.

### 3.9 Professor Profile / Settings

#### Profile Tab — `/professor/profile` (read-only per D32)

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  My Profile                                       │
│────────────│────────────────────────────────────────────────────│
│ 📊 Dash    │                   👤 (avatar)                      │
│ 📷 Live    │                                                    │
│ 📅 History │  Name:         John A. Smith                       │
│ 📋 Reports │  Department:   Computer Science                    │
│ 👥 Courses │  Employee No.: EMP-2024-0042                       │
│ ⚙️ Settings│  Email:        jsmith@university.edu               │
│            │                                                    │
│            │  Assigned Courses:                                 │
│            │  · CS101 — Software Eng (BSCS·Y1, Primary)         │
│            │  · MATH202 — Calculus 2 (BSCS·Y1, Primary)         │
│            │  · CS101 — Software Eng (BSIT·Y1, Assistant)       │
│            │                                                    │
│            │  Claim Status: ✅ Claimed                          │
│            │                                                    │
│            │  ┌──────────────────────────────────────────┐      │
│            │  │  Changes handled by Admin                │      │
│            │  └──────────────────────────────────────────┘      │
│            │                                                    │
│            │  Account: Jan 2024 · Sessions: 87                  │
│            └────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

> **Read-only profile** (D32): all identity fields are admin-managed.
> No edit button — note says "Changes handled by Admin."

#### Settings Tab — `/professor/settings`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Settings                                         │
│────────────│────────────────────────────────────────────────────│
│ 📊 Dash    │  ──── Security ────                                │
│ 📷 Live    │  [Change Password]                                 │
│ 📅 History │  Password policy: 8+ chars, 1 upper, 1 lower,      │
│ 📋 Reports │  1 number, 1 symbol                                │
│ 👥 Courses │                                                    │
│ ⚙️ Settings│  ──── Two-Factor Auth ────                         │
│            │  [Set Up MFA]                                      │
│            │  Status: Not configured                            │
│            │                                                    │
│            │  ──── Security Question ────                       │
│            │  [Set Security Question]                           │
│            │                                                    │
│            │  App version: 1.0.0                                │
│            └────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

> **Settings** (D32): security (Change Password with policy hint, MFA
> setup, Security Question) plus device-local preferences — Appearance
> (Light/Dark theme), Notifications, and Privacy toggles. Identity stays
> admin-managed.

---

## 4. Admin

### 4.1 Admin Dashboard — `/admin/dashboard`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Admin Dashboard                     🔔           │
│────────────│────────────────────────────────────────────────────│
│ 📊 Dash    │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐               │
│ 👤 Students│  │1,240 │ │  45  │ │   8  │ │ 89%  │               │
│ 👨‍🏫 Profs   │  │Students│Prof. │ │Progr.│ │ Rate │               │
│ 📚 Programs│  └──────┘ └──────┘ └──────┘ └──────┘               │
│ 📈Analytics│                                                    │
│ 🔍 Audit   │  ──── Today's Activity ────                        │
│ ⚙️ System  │  Active: 5 · Scans: 142 · Pending: 3               │
│            │                                                    │
│            │  ──── Quick Actions ────                           │
│            │  [📥 Import]  [💾 Backup]                          │
│            │                                                    │
│            │  ──── Recent Scans (last 10) ────                  │
│            │  09:01 Alice → CS101 ✅                            │
│            │  09:02 Bob   → MATH202 ❌ (GPS)                    │
│            │  09:03 Carol → PHYS101 ✅                          │
│            │  09:04 Dave  → CS101 ⏳ (pending)                  │
│            └────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Admin Student Management — `/admin/students`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Student Management               [+Add] [Import] │
│────────────│────────────────────────────────────────────────────│
│ 📊 Dash    │  🔍 [Search...]    Course: [All ▼]  Year: [All ▼]  │
│ 👤 Students│  Section: [All ▼]  Date: [From—To ▼] [🔍 Apply]    │
│ 👨‍🏫 Profs   │  ┌──────────┬──────────────┬──────┬───┬───┬──────┐ │
│ 📚 Programs│  │ ID ⇅     │ Name ⇅       │Course│Sec│ Yr│Status│ │
│ 📈Analytics│  ├──────────┼──────────────┼──────┼───┼───┼──────┤ │
│ 🔍 Audit   │  │2021-001  │ Alice Santos │  CS  │ A │ 3 │  ✅  │ │
│ ⚙️ System  │  │2022-002  │ Bob Cruz     │  IT  │ B │ 2 │  ✅  │ │
│            │  │2023-003  │ Carol Tan    │  CS  │ A │ 1 │  ✅  │ │
│            │  │2024-004  │ Dave Reyes   │ ECE  │ C │ 4 │  🚫  │ │
│            │  │2025-005  │ Emma Lim     │  CS  │ B │ 1 │  ✅  │ │
│            │  └──────────┴──────────────┴──────┴───┴───┴──────┘ │
│            │  < 1 2 >   [🔓 Deactivate] [🔑 Reset Pwd]          │
│            │            [🗃 Archive]                            │
│            └────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

> **Name** = First + Middle + Last (add a Middle Name / Section when
> editing or importing). **Email** is seeded from the roster and is the
> student's **registration lookup key** (they claim this record by
> registering with that email + OTP). **Deactivate** sets `is_active=false`
> (soft delete); records are never hard-deleted here. **Reset Pwd** lets an
> admin reset a user's password (a temp password is set + the user is
> prompted to change it on next login). Only from the Archive screen can a
> record be permanently deleted. Column headers are sortable.

### 4.3 Admin CSV Import — `/admin/students/import`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Import Students from CSV                         │
│────────────│────────────────────────────────────────────────────│
│            │  Step 1: Download Template                         │
│            │  [📥 Download CSV Template]                        │
│            │  student_id, first_name, middle_name, last_name,   │
│            │  email, program_code, section, year_level             │
│            │                                                    │
│            │  Step 2: Upload File                               │
│            │  ┌──────────────────────────────────────────┐      │
│            │  │          Drag & drop CSV here            │      │
│            │  │          or click to browse              │      │
│            │  └──────────────────────────────────────────┘      │
│            │                                                    │
│            │  Step 3: Preview                                   │
│            │  ┌──────┬───────┬─────┬──────┬──────────┬───┬───┐  │
│            │  │ ID   │ FName │MName│ LName│ Email    │Sec│ Yr│  │
│            │  ├──────┼───────┼─────┼──────┼──────────┼───┼───┤  │
│            │  │2025- │ New   │     │ Stu  │ s@univ...│ A │ 1 │  │
│            │  └──────┴───────┴─────┴──────┴──────────┴───┴───┘  │
│            │  25 new · 0 duplicates · 3 errors                  │
│            │  ┌──────────────────────────────────────────┐      │
│            │  │        Confirm Import (25)               │      │
│            │  └──────────────────────────────────────────┘      │
│            └────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

### 4.4 Admin Professor Management — `/admin/professors`

Same CRUD pattern as Student Management (4.2), but this screen **seeds the
professor records that professors claim at registration**. Columns:
Name (First/Middle/Last), Department, **Email** (the
registration lookup key and professor identifier), Courses Assigned, Status, **Claim** (Unclaimed ✅
/ Claimed). Actions: [+Add] [Import CSV] (template: `first_name,
middle_name, last_name, email, department`), [Deactivate]
[Reset Pwd] [Archive]. Create/Edit form includes multi-select course
assignment.

### 4.5 Admin Program Management — `/admin/programs`

#### 4.5a Programs List — `/admin/programs`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Program Management                [+Add Program] │
│────────────│────────────────────────────────────────────────────│
│ 📊 Dash    │  🔍 [Search...]    Status: [All ▼]  [🔍 Apply]     │
│ 👤 Students│                                                    │
│ 👨‍🏫 Profs   │  ┌──────┬────────────┬───────┬──────┬────────┬───┐ │
│ 📚 Programs│  │Code ⇅│ Name ⇅     │ Years │Terms │Courses │St │ │
│ 📈Analytics│  ├──────┼────────────┼───────┼──────┼────────┼───┤ │
│ 🔍 Audit   │  │ BSCS │ BS Comp Sci│   4   │ 2-3  │  24    │ ✅│ │
│ ⚙️ System  │  │ BSIT │ BS Info Tec│   4   │ 2    │  20    │ ✅│ │
│            │  │BSECE │ BS Elec CE │   4   │ 2    │  22    │ ✅│ │
│            │  │ BSED │ BS Education│  4   │ 2    │  18    │ 🚫│ │
│            │  └──────┴────────────┴───────┴──────┴────────┴───┘ │
│            │  < 1 >  [🗃 Archive]                               │
│            │  Click row → program detail (4.5b)                 │
│            └────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

#### 4.5b Program Detail — `/admin/programs/{id}`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  BSCS — BS Computer Science         [✏ Edit]      │
│────────────│────────────────────────────────────────────────────│
│ 📊 Dash    │  Total Years: 4 · Total Courses: 24                │
│ 👤 Students│                                                    │
│ 👨‍🏫 Profs   │  ──── Year Levels ────                             │
│ 📚 Programs│  [+Add Year]                                       │
│ 📈Analytics│  ┌─────────────────────────────────────────────┐   │
│ 🔍 Audit   │  │ 1st Year 🔒        [Manage Terms ✏]         │   │
│ ⚙️ System  │  │ Terms: ● 1st Semester  ● 2nd Semester       │   │
│            │  │ Courses: 6  ·  [View Courses →]             │   │
│            │  ├─────────────────────────────────────────────┤   │
│            │  │ 2nd Year 🔒        [Manage Terms ✏]         │   │
│            │  │ Terms: ● 1st Semester  ● 2nd Semester       │   │
│            │  │ Courses: 6  ·  [View Courses →]             │   │
│            │  ├─────────────────────────────────────────────┤   │
│            │  │ 3rd Year 🔒        [Manage Terms ✏]         │   │
│            │  │ Terms: ● 1st Sem  ● 2nd Sem  ● Midyear      │   │
│            │  │ Courses: 8  ·  [View Courses →]             │   │
│            │  ├─────────────────────────────────────────────┤   │
│            │  │ 4th Year 🔒        [Manage Terms ✏]         │   │
│            │  │ Terms: ● 1st Semester  ● 2nd Semester       │   │
│            │  │ Courses: 4  ·  [View Courses →]             │   │
│            │  └─────────────────────────────────────────────┘   │
│            └────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

> **Term chips** are editable via a modal (add/remove/rename terms).
> Each year level's `term_structure` JSONB (D3) defines available terms.
> Example: BSCS Y3 has 3 terms (1st, 2nd, Midyear); BSCS Y1/Y2 have 2.

#### 4.5c Year-Level Courses — `/admin/programs/{pid}/years/{yid}/courses`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  BSCS · 1st Year — Courses       [+Add Course]    │
│────────────│────────────────────────────────────────────────────│
│ 📊 Dash    │  Terms: ● 1st Semester  ● 2nd Semester             │
│ 👤 Students│                                                    │
│ 👨‍🏫 Profs   │  ┌──────┬──────────────────┬──────┬──────┬──────┐  │
│ 📚 Programs│  │Code ⇅│ Name ⇅           │Units │Sched │Stdnts│  │
│ 📈Analytics│  ├──────┼──────────────────┼──────┼──────┼──────┤  │
│ 🔍 Audit   │  │CS101 │ Software Eng     │  3   │MWF   │  30  │  │
│ ⚙️ System  │  │CS102 │ Data Structures  │  3   │TTH   │  28  │  │
│            │  │MATH1 │ Calculus 1       │  4   │MWF   │  35  │  │
│            │  │GE001 │ Ethics           │  2   │W     │  40  │  │
│            │  └──────┴──────────────────┴──────┴──────┴──────┘  │
│            │  Click row → course detail (4.5d)                  │
│            └────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

> **Add Course form fields** (D4): course_code, course_name, units,
> sessions_per_week, session_duration_hours, semester_weeks,
> schedule_days (MWF/TTH/etc), schedule_start_time, schedule_end_time,
> classroom_name, classroom_lat, classroom_lng,
> default_present_window_minutes (DEF 5), default_late_window_minutes
> (DEF 10). A course can span multiple programs/year_levels (D6).

#### 4.5d Course Detail — `/admin/courses/{cid}`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  CS101 — Software Engineering                     │
│────────────│────────────────────────────────────────────────────│
│ 📊 Dash    │  BSCS · 1st Year · MWF 9:00-10:30                  │
│ 👤 Students│  Room: Lab 101 (14.5995°N, 120.9842°E)             │
│ 👨‍🏫 Profs   │  Units: 3 · Duration: 90 min · Weeks: 16           │
│ 📚 Programs│                                                    │
│ 📈Analytics│  ┌──────┬──────────┬───────────────┬──────────────┐│
│ 🔍 Audit   │  │Tab   │ Overview │ Professors    │ Enrolled     ││
│ ⚙️ System  │  ├──────┼──────────┼───────────────┼──────────────┤│
│            │  │      │ Schedule │ History log   │ Roster       ││
│            │  │      │ Windows  │ Effective     │ Section      ││
│            │  │      │ GPS      │ from/to       │ filter       ││
│            │  └──────┴──────────┴───────────────┴──────────────┘│
│            │                                                    │
│            │  ──── Professors Tab ────                          │
│            │  ┌───────────────────────────────────────────┐     │
│            │  │ Prof. Smith  (Primary)                    │     │
│            │  │ Effective: 2026-01-01 → ongoing           │     │
│            │  │ Semester: 1st Sem 2026                    │     │
│            │  ├───────────────────────────────────────────┤     │
│            │  │ Prof. Garcia  (Assistant)                 │     │
│            │  │ Effective: 2026-06-01 → 2026-08-15        │     │
│            │  │ Semester: Summer 2026                     │     │
│            │  └───────────────────────────────────────────┘     │
│            │  [+Assign Professor]                               │
│            │                                                    │
│            │  ──── Settings Tab ────                            │
│            │  Present window: 5 min · Late window: 10 min       │
│            │  Geofence radius: 30m                              │
│            │  [✏ Edit Defaults]                                 │
│            └────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

> `Geofence radius: 30m` is a mock value — the system default (`classroom_radius_meters`)
> is **50 m**, configurable per offering/session. Same applies to the 2.2c "Required
> radius: 30m" label.

> **Professor assignment** (D7–D9): many-to-many via `course_professors`
> with `is_primary`, `effective_from`, `effective_to` (nullable = ongoing),
> `semester`, `assigned_by`, `assigned_at`. Professors CAN be changed
> mid-semester; history is never rewritten. Any professor with an active
> assignment may open sessions for the course.

### 4.6 Attendance Snapshot — Attendance tab of `/admin/analytics`

> Relocated from the old `/admin/attendance/overview` page ([ADR-083](../project/decision-log.md)).
> Reachable at `/admin/analytics?tab=attendance` and from the dashboard's
> "Attendance at a glance" strip. Its Course ▸ Professor ▸ Date filters are
> its own; the 4.7 filter rail is hidden on this tab.

```
┌────────────┬───────────────────────────────────────────────────┐
│ ☰          │  Analytics & Reports › Attendance                 │
│────────────│───────────────────────────────────────────────────│
│            │  Filters: Course [All] Prof [All] Date [Range ▼]  │
│            │                                                   │
│            │  ┌─────────────────────────────────────────┐      │
│            │  │ Course ⇅   │ Sessions⇅│ Avg ⇅  │ Trend⇅ │      │
│            │  ├────────────┼──────────┼────────┼────────┤      │
│            │  │  CS101     │   12     │  88%   │   ↑    │      │
│            │  │  MATH202   │   10     │  72%   │   ↓    │      │
│            │  │  PHYS101   │    8     │  91%   │   →    │      │
│            │  │  ECE101    │    6     │  95%   │   ↑    │      │
│            │  └────────────┴──────────┴────────┴────────┘      │
│            │        [🖨 Print]  [📥 Export Overview]           │
│            └───────────────────────────────────────────────────┘
└────────────────────────────────────────────────────────────────┘
```

### 4.7 Analytics & Reports — `/admin/analytics`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Analytics & Reports                              │
│────────────│────────────────────────────────────────────────────│
│ 📊 Dash    │  ┌──────────────────────────────────────────────┐  │
│ 👤 Students│  │  FILTER RAIL                                 │  │
│ 👨‍🏫 Profs   │  │  Program  ▸ [BSCS ▼]                         │  │
│ 📚 Programs│  │  Year      ▸ [All ▼]                         │  │
│ 📈Analytics│  │  Term      ▸ [1st Sem 2026 ▼]                │  │
│  🔍 Audit  │  │  Courses   ▸ [CS101, MATH1 ▼] (multi)        │  │
│  ⚙️ System │  │  Date Range▸ [Jul 01 → Jul 31 ▼]             │  │
│            │  │  Granularity▸ [Daily ▼]                      │  │
│            │  │  [Apply Filters]                             │  │
│            │  └──────────────────────────────────────────────┘  │
│            │                                                    │
│            │  ┌────────┬───────────┬──────────┬───────┬──────┐  │
│            │  │Overview│ Comparison│ Trends   │At-Risk│Export│  │
│            │  └────────┴───────────┴──────────┴───────┴──────┘  │
│            │                                                    │
│            │  ──── Overview Tab ────                            │
│            │  ┌──────┐ ┌──────┐ ┌────────┐ ┌────────┐           │
│            │  │ 1240 │ │  45  │ │  88%   │ │  92%   │           │
│            │  │Stud. │ │Sess. │ │AvgComp │ │AvgPart │           │
│            │  └──────┘ └──────┘ └────────┘ └────────┘           │
│            │                                                    │
│            │  ──── Course Comparison Tab ────                   │
│            │  BSCS·Y1 CS101  ████████████████░░░░  88%          │
│            │  BSCS·Y1 MATH1  ██████████████░░░░░░  72%          │
│            │  BSIT·Y1 CS101  █████████████████░░░  91%          │
│            │  (same course shown once per cohort — D6/D34)      │
│            │                                                    │
│            │  ──── Trends Tab ────                              │
│            │  ┌──────────────────────────────────────────┐      │
│            │  │  95%┤   ╭──╮                             │      │
│            │  │  85%┤╭──╯  ╰──╮  ╭──╮                    │      │
│            │  │  75%┤╯        ╰──╯  ╰──                  │      │
│            │  │  65%┤                                    │      │
│            │  │     └──┬──┬──┬──┬──┬──┬──                │      │
│            │  │      Mon Tue Wed Thu Fri Sat             │      │
│            │  │  [Daily ▾] [Weekly ▾] [Monthly ▾]        │      │
│            │  └──────────────────────────────────────────┘      │
│            │                                                    │
│            │  ──── At-Risk Tab ────                             │
│            │  ┌──────┬────────┬──────┬──────┬───────┬──────┐    │
│            │  │Name ⇅│ Course │Abs%  │Streak│Trend  │Risk  │    │
│            │  ├──────┼────────┼──────┼──────┼───────┼──────┤    │
│            │  │J.Sant│ MATH1  │ 42%  │  5   │  ↓    │🔴Hi  │    │
│            │  │A.Reye│ CS101  │ 28%  │  3   │  ↓    │🟡Med │    │
│            │  │C.Tan │ CS101  │ 15%  │  0   │  →    │🟢Lo  │    │
│            │  └──────┴────────┴──────┴──────┴───────┴──────┘    │
│            │  [🔄 Refresh Risk Scores]                          │
│            │                                                    │
│            │  ──── Export Tab ────                              │
│            │  Format: ○ CSV  ○ PDF                              │
│            │  Include: ☑ Attendance  ☑ Students  ☑ Risk         │
│            │  [📥 Download Export]                              │
│            └────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

> **Cascading filters** (D33): Program → Year → Term → Courses (multi)
> → Date range → Granularity (D/W/M). Same course can appear under
> multiple cohorts (D6/D34). **At-Risk** uses heuristic thresholds
> (D35): absence_rate > 0.30 → high; > 0.15 → medium; streak ≥ 3
> → high; sync-lag pending ≥ 5 → medium; trend slope < −0.05/week →
> medium. Runs as daily batch job; manual refresh endpoint exists
> (admin-only). **Compliance Rate** = present / total (default D36);
> **Participation Rate** = (present + late + excused) / total (toggle).
>
> **Attendance tab** (ADR-083): the per-course snapshot (wireframe 4.6)
> is a seventh tab, rendered inline with its own Course / Professor / date
> filters — the rail above is hidden while it is open. The live tab set is
> Overview · Course Comparison · Trends · At-Risk · **Staging** ·
> **Attendance** · Export. Deep link: `/admin/analytics?tab=attendance`.

### 4.8 Admin Audit Logs — `/admin/audit-logs`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Audit Logs                                       │
│────────────│────────────────────────────────────────────────────│
│            │  Date: [Jul 01 → Jul 29 ▼]  Action: [All ▼]        │
│            │  ┌──────┬────────────┬──────────────────────┐      │
│            │  │ Time⇅│ User ▲     │ Action ⇅             │      │
│            │  ├──────┼────────────┼──────────────────────┤      │
│            │  │09:01 │ A. Santos  │ Scan CS101           │      │
│            │  │08:55 │ Prof.Smith │ Opened session CS101 │      │
│            │  │08:30 │ Admin      │ Imported CSV (25)    │      │
│            │  │08:00 │ Admin      │ Added term to Y2 BSCS│      │
│            │  └──────┴────────────┴──────────────────────┘      │
│            │  < 1 2 3 >  [🖨 Print]  [📥 Export Logs]           │
│            └────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

### 4.9 Admin System Settings — `/admin/system/settings`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  System Settings                                  │
│────────────│────────────────────────────────────────────────────│
│            │  ──── Attendance Defaults ────                     │
│            │  Geofence Radius: [30] meters                      │
│            │  Default Present Window: [5] min                   │
│            │  Default Late Window: [10] min                     │
│            │                                                    │
│            │  ──── Academic Structure Updates ────              │
│            │  [Edit Programs ➜]                                 │
│            │  Deep-link into 4.5 — add/rename year levels,      │
│            │  adjust term structures, move courses between      │
│            │  programs. All changes audited.                    │
│            │  Last structural change: Jun 2026 (Admin K. Santos)│
│            │                                                    │
│            │  ──── Backup ────                                  │
│            │  Full Database Backup                              │
│            │  Status: ✅ Healthy · Last: Jul 28, 2026 3:00 AM   │
│            │  Encryption: AES-256-GCM · Retention: 30D daily    │
│            │  + 12 monthly                                      │
│            │  [💾 Backup Now]  [📥 Download]  [🔒 Key Mgmt]     │
│            │                                                    │
│            │  Analytics Export                                  │
│            │  Format: ○ CSV  ○ PDF                              │
│            │  [📥 Export Analytics Data]                        │
│            │                                                    │
│            │  ──── Maintenance ────                             │
│            │  Pending sync: 3   [Force Sync] [Clean Up]         │
│            │                                                    │
│            │              [💾 Save Changes]                     │
│            └────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

> **Year + Section Promotion** (old) is removed (D38). Replaced by
> **Academic Structure Updates** — manual, intentional, audited changes
> through the Program Management screen (4.5).
>
> **Full Backup** (D39): pg_dump custom format of EVERY table — nothing
> excluded by default — compressed, encrypted AES-256-GCM with key from
> env. Retention: last 30 daily + 12 monthly. All backups logged in
> `backup_log`. Storage: local (dev) / S3-compatible (prod) via
> `BACKUP_STORAGE_TYPE`.
>
> **Analytics Export**: separate aggregated CSV/PDF download of reporting
> data — does not touch backup infrastructure.

### 4.10 Admin Archive — `/admin/students/archive`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Archived Students                                │
│────────────│────────────────────────────────────────────────────│
│            │  Graduated or unenrolled students moved here.      │
│            │  ┌──────────┬──────────────┬──────┬────────────┐   │
│            │  │ ID ▲     │ Name ⇅       │Course│ Archived ⇅ │   │
│            │  ├──────────┼──────────────┼──────┼────────────┤   │
│            │  │2020-006 │ Grace Lopez   │  CS  │ Jun 2026   │   │
│            │  │2020-007 │ Henry Tan     │ ECE  │ Jun 2026   │   │
│            │  │2021-008 │ Isabel M.     │  IT  │ Jun 2026   │   │
│            │  └──────────┴──────────────┴──────┴────────────┘   │
│            │  [Restore Selected] [🗑 Permanently Delete]        │
│            └────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

### 4.11 Admin Profile

Admin profile uses the student settings visual shell: identity card (name,
email, role, last login), Appearance (theme), a Security card (Change Password,
MFA via `MfaSettings`, Security Question), and an app version footer.
Non-super-admin first login with a temp password captures the security question
in the forced flow; super-admin uses the password-only flow.

### 4.12 Admin Attendance Review — `/admin/attendance`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Attendance Review                                │
│────────────│────────────────────────────────────────────────────│
│            │  Flagged scans awaiting manual review              │
│            │  ┌──────┬────────────┬──────────┬──────────────┐   │
│            │  │ Time │ Student    │ Reason   │ Evidence     │   │
│            │  ├──────┼────────────┼──────────┼──────────────┤   │
│            │  │09:02 │ J. Santos  │ GPS 35m  │ [View bundle]│   │
│            │  │08:55 │ A. Reyes   │ Face 62% │ [View bundle]│   │
│            │  └──────┴────────────┴──────────┴──────────────┘   │
│            │  [Approve] [Reject] [🖨 Print] [Export log]        │
│            └────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

### 4.13 Admin Users — `/admin/users`

Admin accounts are **never self-registered**. The first admin is seeded at
deployment; this screen manages all subsequent ones.

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Admin Users                       [+Add Admin]   │
│────────────│─────────────────────────────────────────────────── │
│ 📊 Dash    │  🔍 [Search...]    Role: [All ▼]  Status: [All ▼]  │
│ 👤 Students│  ┌──────────────┬──────────────┬────────┬────────┐ │
│ 👨‍🏫 Profs   │  │ Name ⇅       │ Email        │ Role   │ Status │ │
│ 📚 Programs├──────────────┼──────────────┼────────┼────────┤  │ │
│ 📈Analytics│  │ K. Santos    │ karla@...    │ Super  │  ✅    │ │
│  🔍 Audit  │  │ J. Reyes     │ jose@...     │ Admin  │  🚫    │ │
│  ⚙️ System │  │  A. Lim      │ ana@...      │ Admin  │  ✅    │ │
│            │  └──────────────┴──────────────┴────────┴────────┘ │
│            │  < 1 2 >  [🔓 Deactivate] [🔑 Reset Pwd]           │
│            │           [🗃 Archive]                             │
│            │                                                    │
│            │  [+Add Admin] form:                                │
│            │  Name (First/Middle/Last) · Email · Role:          │
│            │  [Super Admin ▼]  · Send temp password? ☑          │
│            └────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

> Mirrors the Student/Professor management pattern: sortable headers,
> search + category filters, deactivate instead of delete, archive, and
> admin password reset. Only a Super Admin can manage other admins.

### 4.14 Admin Face Enrollment — `/admin/students` (modal)

> **Design mockup** for the admin face-enrollment flow (D28). The shipped UI is
> a modal on `/admin/students`, not a dedicated route. It accepts **3 photos**
> (front, left, right) as file uploads. The server now generates a real 512-d
> embedding (MobileFaceNet) from those photos; AES-GCM encryption at rest is
> still **not implemented**. See
> [face-enrollment.md](../architecture/face-enrollment.md) §4.2.
```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Face Enrollment — John Doe (2021-01234)          │
│────────────│────────────────────────────────────────────────────│
│ 📊 Dash    │  Step 1: Capture Photos                            │
│ 👤 Students│                                                    │
│ 👨‍🏫 Profs   │  ┌──────────────────────────────────────────────┐  │
│ 📚 Programs│  │  Front Face [📷 Capture]                     │  │
│ 📈 Analytics│ │  ┌──────────────────────────────────────┐    │  │
│ 🔍 Audit   │  │  │                                      │    │  │
│ ⚙️ System  │  │  │           (camera preview)           │    │  │
│ 📷 Face    │  │  │                                      │    │  │
│            │  │  │                                      │    │  │
│            │  │  └──────────────────────────────────────┘    │  │
│            │  │  Quality: Brightness ✓ · Face size ✓ · Single fa│
│            │  └──────────────────────────────────────────────┘  │
│            │                                                    │
│            │  ┌──────────────────────────────────────────────┐  │
│            │  │  Left Profile       [📷 Capture]             │  │
│            │  │  (same camera preview)                       │  │
│            │  └──────────────────────────────────────────────┘  │
│            │                                                    │
│            │  ┌──────────────────────────────────────────────┐  │
│            │  │  Right Profile      [📷 Capture]             │  │
│            │  │  (same camera preview)                       │  │
│            │  └──────────────────────────────────────────────┘  │
│            │                                                    │
│            │  Step 2: Prepare Enrollment                        │
│            │  [🔄 Prepare Enrollment Record]                    │
│            │  Status: Not prepared                              │
│            │                                                    │
│            │  Step 3: Save & Enroll                             │
│            │  [💾 Save Enrollment]                              │
│            │  Current build stores a real 512-d embedding;       │
│            │  encryption at rest is not implemented.           │
│            └────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

> **Re-enrollment**: replaces the stored embedding and bumps the version. **Revocation** on archive.
> **Thresholds**: the server applies `FACE_MATCH_THRESHOLD` (0.70) and the
> 0.65 review band to the server-computed cosine similarity.

---

## 5. Shared & Global

### 5.1 404 Error Page — `/+error`

```

┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│ 🔍 404                                                          │
│ Page Not Found                                                  │
│                                                                 │
│ The page doesn't exist or you don't have                        │
│ permission to access it.                                        │
│                                                                 │
│ ┌──────────────────────┐                                        │
│                       │ Go to Dashboard │                       │
│ └──────────────────────┘                                        │
└─────────────────────────────────────────────────────────────────┘

```

### 5.2 Offline Sync Status (floating banner)

```

Connected state (auto-dismiss):
┌─────────────────────────────────────────────────────────────────┐
│ ✅ Synced — All caught up!                                      │
└─────────────────────────────────────────────────────────────────┘

Offline state (persistent):
┌─────────────────────────────────────────────────────────────────┐
│ ⚠ You are offline · Records will sync when connected. [✕]       │
│ 3 pending                                                       │
│ (2 include face-liveness evidence — will verify after sync)     │
└─────────────────────────────────────────────────────────────────┘

Syncing state (progress):
┌─────────────────────────────────────────────────────────────────┐
│ 🔄 Syncing… 2 of 5 records processed [✕]                        │
└─────────────────────────────────────────────────────────────────┘

Partial failure:
┌─────────────────────────────────────────────────────────────────┐
│ ⚠ 1 record rejected: session_expired (window closed) [✕]        │
└─────────────────────────────────────────────────────────────────┘

```

> **Offline banner** (D16/D30): shows "N awaiting verification (face)"
> when offline scans include face-liveness evidence pending server-side
> verification. Expired-window offline scans are rejected on sync with
> reason `session_expired`.

---

## 6. Screen Map

### Navigation Flow

```
                       ┌─────────────┐
                       │  Landing    │
                       └──────┬──────┘
                              ▼
                       ┌───────────────┐
                       │   Login       │ ←─── Register
                       │  (+Turnstile) │      Forgot Password (4-step)
                       └───────┬───────┘
                              ▼
                       ┌─────────────┐
                       │  MFA Verify │  (if MFA enabled)
                       │  (OTP 1.6)  │
                       └──────┬──────┘
                              ▼
                       ┌─────────────┐
                       │ Auth Guard  │──→ 404 if no role
                       └──┬──┬──┬───┘
            ┌─────────────┘  │  └────────────┐
            ▼                ▼               ▼

┌────────────┐ ┌────────────┐ ┌────────────┐
│  Student   │ │ Professor  │ │   Admin    │
│ Dash(2.1)  │ │ Dash(3.1)  │ │ Dash(4.1)  │
├────────────┤ ├────────────┤ ├────────────┤
│ Scan(2.2)  │ │OpenSes     │ │Students    │
│  ├2.2a     │ │ (3.2a/b)   │ │ (4.2)      │
│  ├2.2b     │ │ActSes(3.3) │ │ CSV(4.3)   │
│  ├2.2c     │ │AttList(3.4)│ │Profs(4.4)  │
│  ├2.2d     │ │SesHist(3.5)│ │Programs    │
│  └2.2e     │ │Courses(3.6)│ │ ├4.5a      │
│ Hist(2.7)  │ │Reports(3.7)│ │ ├4.5b      │
│ Sched(2.8) │ │Export(3.8) │ │ ├4.5c      │
│ Notif(2.9) │ │Prof(3.9)   │ │ └4.5d      │
│ Prof(2.10) │ │            │ │AttOver     │
│ Set(2.11)  │ │            │ │ (4.6)      │
└────────────┘ └────────────┘ │Analytics   │
                              │ (4.7)      │
                              │Audit(4.8)  │
                              │Settings    │
                              │ (4.9)      │
                              │Archive     │
                              │ (4.10)     │
                              │Profile     │
                              │ (4.11)     │
                              │Liveness    │
                              │ (4.12)     │
                              │Admin Users │
                              │ (4.13)     │
                              │Face Enroll │
                              │ (4.14)     │
                              └────────────┘
```

### All 47 Screens by Route

| #   | Screen                   | Route                                       | Role      |
| --- | ------------------------ | ------------------------------------------- | --------- |
| 1   | Landing                  | `/`                                         | Public    |
| 2   | Login                    | `/login`                                    | Public    |
| 3   | Register                 | `/register`                                 | Public    |
| 4   | Forgot Password (4-step) | `/forgot-password`                          | Public    |
| 5   | MFA Setup                | `/settings/security`                        | All       |
| 6   | MFA Verification         | `/login/mfa`                                | Public    |
| 7   | Dashboard                | `/student/dashboard`                        | Student   |
| 8   | Scan — Session Entry     | `/student/scan`                             | Student   |
| 9   | Scan — ID Confirmation   | `/student/scan`                             | Student   |
| 10  | Scan — Session QR        | `/student/scan`                             | Student   |
| 11  | Scan — Liveness          | `/student/scan`                             | Student   |
| 12  | Scan — Result            | `/student/scan`                             | Student   |
| 13  | History                  | `/student/history`                          | Student   |
| 14  | Schedule                 | `/student/schedule`                         | Student   |
| 15  | Notifications            | `/student/notifications`                    | Student   |
| 16  | Profile                  | `/student/profile`                          | Student   |
| 17  | Settings                 | `/student/settings`                         | Student   |
| 18  | Dashboard                | `/professor/dashboard`                      | Professor |
| 19  | Open Session (Locked)    | `/professor/sessions/create?course={id}`    | Professor |
| 20  | Open Session (Selector)  | `/professor/sessions/create`                | Professor |
| 21  | Active Session           | `/professor/sessions/active/[id]`           | Professor |
| 22  | Attendance List          | `/professor/attendance`                     | Professor |
| 23  | Session History          | `/professor/sessions/history`               | Professor |
| 24  | Courses                  | `/professor/courses`                        | Professor |
| 25  | Reports                  | `/professor/reports`                        | Professor |
| 26  | Export                   | `/professor/attendance/export`              | Professor |
| 27  | Profile                  | `/professor/profile`                        | Professor |
| 28  | Settings                 | `/professor/settings`                       | Professor |
| 29  | Dashboard                | `/admin/dashboard`                          | Admin     |
| 30  | Student Mgmt             | `/admin/students`                           | Admin     |
| 31  | CSV Import               | `/admin/students/import`                    | Admin     |
| 32  | Professor Mgmt           | `/admin/professors`                         | Admin     |
| 33  | Programs List            | `/admin/programs`                           | Admin     |
| 34  | Program Detail           | `/admin/programs/{id}`                      | Admin     |
| 35  | Year-Level Courses       | `/admin/programs/{pid}/years/{yid}/courses` | Admin     |
| 36  | Course Detail            | `/admin/courses/{cid}`                      | Admin     |
| 37  | Attendance Snapshot      | `/admin/analytics?tab=attendance`           | Admin     |
| 38  | Analytics & Reports      | `/admin/analytics`                          | Admin     |
| 39  | Audit Logs               | `/admin/audit-logs`                         | Admin     |
| 40  | System Settings          | `/admin/system/settings`                    | Admin     |
| 41  | Archive                  | `/admin/students/archive`                   | Admin     |
| 42  | Profile                  | `/admin/profile`                            | Admin     |
| 43  | Attendance Review        | `/admin/attendance`                         | Admin     |
| 44  | Admin Users              | `/admin/users`                              | Admin     |
| 45  | Face Enrollment          | `/admin/students` (modal)                   | Admin     |
| 46  | 404 Error                | `/+error`                                   | Global    |
| 47  | Offline Sync Banner      | (floating overlay)                          | Global    |

---

## Design Notes

- **All screens** are mobile-responsive: sidebar collapses to bottom tab bar on small screens
- **Permission prompts** (camera + GPS) appear before first scanner use (incorporated into 2.2a)
- **Face liveness** is a fixed 3-step challenge (blink → turn left → turn right) in 2.2d; MediaPipe FaceLandmarker WASM client-side, EAR + PnP server-side (D31)
- **Offline banner** appears on all authenticated screens when connection is lost; shows "N awaiting verification (face)" when offline scans include face evidence (D16/D30)
- **Prof/Admin profile & settings** are read-only (D32); student profile also read-only (D32)
- **CRUD screens** (students, professors) follow the same create/edit/list pattern
- **Program Management** (4.5a–d) replaces flat Course Management; hierarchical: Programs → Year Levels → Courses
- **Projector mode** (3.3) renders full-screen with large session code visible from the back of a classroom
- **Dual timers** (3.3): stacked pills showing scan window countdown and class scheduled end time
- **Window math block** (3.2a/b): always shows `Present __ + Late __ ≤ Duration __` with live-computed expiry
- **Status legend** (all attendance tables): `✅ Present ⏰ Late 📝 Excused ❌ Absent ⏳ Pending ⛔ Rejected`
- **Cohort badge**: `BSCS·Y1` compact chip wherever a course row could spans cohorts (§9)
- **Filter rail** (analytics/reports): left column listing Program▸Year▸Term▸Courses▸Dates▸Granularity with [Apply]
- **Sortable tables**: every data table (2.7, 3.4, 3.5, 3.8, 4.2, 4.6, 4.7, 4.8, 4.10, 4.13) has clickable column headers that toggle ascending/descending with an ▲/▼ indicator, plus **category + date-range filters** and **Print / CSV / PDF** actions
- **Password policy** (all accounts, incl. reset & admin reset): minimum 8 characters with at least 1 uppercase, 1 lowercase, 1 number and 1 symbol (alphanumeric + symbol)
- **Account security**: login is protected by **Cloudflare Turnstile** (free, invisible captcha); optional **MFA (OTP)** via authenticator app; **Forgot Password** is a 4-step flow (email + Turnstile → security question w/ 3-attempt limit → OTP → new/confirm password); accounts lock temporarily after 5 failed logins; OTP codes are stored in a dedicated `otp_codes` table (Argon2id-hashed, single-use, 5-min TTL)
- **Claim-based registration**: students and professors self-register with email + password; the email must match an **admin-seeded record** (roster CSV / professor management), and an **OTP sent to that email** proves ownership before the account is linked. Nothing is typed — name/course/section come from the seeded record. The student number is the roster/attendance key; it is not entered at registration and is not read from a QR
- **Soft delete / deactivate**: records are deactivated (`is_active=false`) rather than deleted; permanent deletion only from the Archive screen
- **Admin reset**: admins can reset any user's password (temp password set; user prompted to change on next login)
- **Admin provisioning**: no public admin registration — the first admin is seeded at deployment as **Super Admin**; additional admins are managed on the Admin Users screen (4.13, Super Admin only)
- **Academic structure updates**: admin-managed through Program Management (4.5) — add/rename year levels, adjust term structures, move courses. All changes audited (D38)
- **Excuse workflow**: three initiation paths (D21) — prof quick-excuse, prof-initiated with evidence, student-initiated request; bulk Excuse All Absent per session (D23)
<<<<<<< HEAD
- **Scan flow**: strictly sequential single-page flow (D27 as amended by ADR-083) - session code → student-ID confirmation → session-QR camera → liveness → GPS → result overlay. No student-ID QR is scanned, and the professor UI does not render the session QR yet.
=======
- **Scan flow**: strictly sequential 5-step flow (D27) — session code/QR → student-ID QR → GPS geofence → face liveness (fixed blink-left-right) → result overlay; requires prior face enrollment (NULL `face_embedding` → `403 face_not_enrolled`)
>>>>>>> b620ab2 (feat(scan): require face enrollment before attendance submission)
- **Embedded conventions**: locked fields (§9), window math blocks, dual timers, full status legend, cohort badges, filter rails, lettered sub-screens (2.2a, 4.5b, etc.)
- **Admin face enrollment** (4.14): modal on the Student Management page for enrolling student faces (D28); uploads 3 photos (front/left/right) and records enrollment. Real embedding generation is implemented (MobileFaceNet ONNX); encryption at rest is not implemented in this build.
- **Session History breakdown** (3.5): Present/Late/Absent counts per session for quick overview

---

_Prepared for Software Engineering 1 — Wireframe Proposal_
