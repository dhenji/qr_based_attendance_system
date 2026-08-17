# Wireframes — QR Attendance System

> 39 screens across 4 user roles + public pages.
> SVG wireframes for proposal presentation.

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

| Element | Style |
|---------|-------|
| Canvas | 700×520px, white bg |
| Sidebar | 140px, `#1e293b` bg, white text |
| Primary button | `#2563eb`, white text |
| Table header | `#f1f5f9` |
| Border radius | 6px cards, 4px inputs |
| Status colors | green `#16a34a`, yellow `#ca8a04`, red `#dc2626`, blue `#2563eb` |

---

## 1. Public & Auth

### 1.1 Landing Page — `/`

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                   │
│                    ┌───────────────────────┐                      │
│                    │    Attendance System   │                      │
│                    │  QR-based · Offline    │                      │
│                    │  Anti-spoofing PWA     │                      │
│                    └───────────────────────┘                      │
│                                                                   │
│                    ┌───────────────────────┐                      │
│                    │        Login          │                      │
│                    └───────────────────────┘                      │
│                         Don't have account?                       │
│                         Register                                  │
│                                                                   │
│                ──────────────────────────────────                  │
│                                                                   │
│         ┌─────────┐        ┌─────────┐       ┌─────────┐         │
│         │ 📷 QR   │        │ 🛡️ Anti │       │ 🌐 Off   │         │
│         │ Scanning│        │ -Spoof  │       │ -line    │         │
│         └─────────┘        └─────────┘       └─────────┘         │
│                                                                   │
│      A PWA — no app installation required                         │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Login — `/login`

```
┌─────────────────────────────────────────────────────────────────┐
│                    ┌─────────────────────────┐                    │
│                    │      Welcome Back        │                    │
│                    │   Sign in to account     │                    │
│                    │                          │                    │
│                    │  Email / Username        │                    │
│                    │  ┌─────────────────┐     │                    │
│                    │  │ student@...     │     │                    │
│                    │  └─────────────────┘     │                    │
│                    │                          │                    │
│                    │  Password                │                    │
│                    │  ┌─────────────────┐     │                    │
│                    │  │ ••••••••••••    │     │                    │
│                    │  └─────────────────┘     │                    │
│                    │                          │                    │
│                    │  Captcha                 │                    │
│                    │  ┌──────────┐  ┌───┐    │                    │
│                    │  │ 4F7K2Q   │  │↻  │    │                    │
│                    │  └──────────┘  └───┘    │                    │
│                    │  ┌─────────────────┐     │                    │
│                    │  │ Enter code above│     │                    │
│                    │  └─────────────────┘     │                    │
│                    │                          │                    │
│                    │  ┌─────────────────┐     │                    │
│                    │  │     Login       │     │                    │
│                    │  └─────────────────┘     │                    │
│                    │                          │                    │
│                    │     Forgot Password?      │                    │
│                    │     ───── OR ──────       │                    │
│                    │  Don't have account?      │                    │
│                    │     Register              │                    │
│                    └─────────────────────────┘                    │
└─────────────────────────────────────────────────────────────────┘
```

> If MFA is enabled, successful login proceeds to the MFA Verification
> screen (1.6) before the dashboard loads. After 5 failed attempts the
> account is temporarily locked (rate-limiting / lockout).

### 1.3 Register — `/register`

```
┌─────────────────────────────────────────────────────────────────┐
│                    ┌─────────────────────────┐                    │
│                    │     Create Account       │                    │
│                    │                          │                    │
│                    │  Email      [________]   │                    │
│                    │  Password   [________]   │                    │
│                    │  Confirm    [________]   │                    │
│                    │  Role       [Student ▼]  │  Student or        │
│                    │                          │  Professor only    │
│                    │  🔒 8+ chars · 1 upper · │                    │
│                    │     1 lower · 1 number · │                    │
│                    │     1 symbol             │                    │
│                    │                          │                    │
│                    │  ┌─────────────────┐     │                    │
│                    │  │    Register     │     │                    │
│                    │  └─────────────────┘     │                    │
│                    │                          │                    │
│                    │  Already have account?   │                    │
│                    │     Login                │                    │
│                    └─────────────────────────┘                    │
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
> registration lookup key and the login identity. The **Student ID is never
> entered at registration** — it exists only as the QR/attendance key.
> **Admin accounts are never self-registered**: the first admin is seeded at
> deployment (env/seed script) and additional admins are created by an
> existing admin on the Admin Users screen (4.14). **Password policy**:
> minimum 8 characters with at least 1 uppercase, 1 lowercase, 1 number and
> 1 symbol (alphanumeric + symbol).

### 1.4 Forgot Password — `/forgot-password`

Four-step flow. Each step advances after verification.

**Step 1 — Email + Captcha**

```
┌─────────────────────────────────────────────────────────────────┐
│                    ┌─────────────────────────┐                    │
│                    │   🔑 Forgot Password    │                    │
│                    │      Step 1 of 4        │                    │
│                    │                          │                    │
│                    │  Email:                  │                    │
│                    │  ┌─────────────────┐     │                    │
│                    │  │ your@email.com  │     │                    │
│                    │  └─────────────────┘     │                    │
│                    │                          │                    │
│                    │  Captcha                 │                    │
│                    │  ┌──────────┐  ┌───┐    │                    │
│                    │  │ 2D8MQA   │  │↻  │    │                    │
│                    │  └──────────┘  └───┘    │                    │
│                    │  ┌─────────────────┐     │                    │
│                    │  │ Enter code above│     │                    │
│                    │  └─────────────────┘     │                    │
│                    │                          │                    │
│                    │  ┌─────────────────┐     │                    │
│                    │  │     Continue    │     │                    │
│                    │  └─────────────────┘     │                    │
│                    │                          │                    │
│                    │     ← Back to Login       │                    │
│                    └─────────────────────────┘                    │
└─────────────────────────────────────────────────────────────────┘
```

**Step 2 — Security Question (multiple attempts)**

```
┌─────────────────────────────────────────────────────────────────┐
│                    ┌─────────────────────────┐                    │
│                    │   🔑 Verify Identity    │                    │
│                    │      Step 2 of 4        │                    │
│                    │                          │                    │
│                    │  Answer the security     │                    │
│                    │  question set at sign-up:│                    │
│                    │                          │                    │
│                    │  "What was your first    │                    │
│                    │   pet's name?"           │                    │
│                    │  ┌─────────────────┐     │                    │
│                    │  │                │     │                    │
│                    │  └─────────────────┘     │                    │
│                    │                          │                    │
│                    │  ⚠ 2 attempts left       │                    │
│                    │  (3 max — then lock)     │                    │
│                    │                          │                    │
│                    │  ┌─────────────────┐     │                    │
│                    │  │     Verify      │     │                    │
│                    │  └─────────────────┘     │                    │
│                    └─────────────────────────┘                    │
└─────────────────────────────────────────────────────────────────┘
```

**Step 3 — OTP**

```
┌─────────────────────────────────────────────────────────────────┐
│                    ┌─────────────────────────┐                    │
│                    │   📧 One-Time Code      │                    │
│                    │      Step 3 of 4        │                    │
│                    │                          │                    │
│                    │  A 6-digit code was      │                    │
│                    │  sent to your email.     │                    │
│                    │                          │                    │
│                    │  ┌───┐ ┌───┐ ┌───┐       │                    │
│                    │  │ 4 │ │ 2 │ │ 8 │ ...   │                    │
│                    │  └───┘ └───┘ └───┘       │                    │
│                    │                          │                    │
│                    │  Expires in 05:00        │                    │
│                    │  [Resend code]           │                    │
│                    │                          │                    │
│                    │  ┌─────────────────┐     │                    │
│                    │  │     Verify      │     │                    │
│                    │  └─────────────────┘     │                    │
│                    └─────────────────────────┘                    │
└─────────────────────────────────────────────────────────────────┘
```

**Step 4 — New Password + Confirm**

```
┌─────────────────────────────────────────────────────────────────┐
│                    ┌─────────────────────────┐                    │
│                    │   🔐 New Password       │                    │
│                    │      Step 4 of 4        │                    │
│                    │                          │                    │
│                    │  New Password            │                    │
│                    │  ┌─────────────────┐     │                    │
│                    │  │ ••••••••••••    │     │                    │
│                    │  └─────────────────┘     │                    │
│                    │                          │                    │
│                    │  Confirm Password         │                    │
│                    │  ┌─────────────────┐     │                    │
│                    │  │ ••••••••••••    │     │                    │
│                    │  └─────────────────┘     │                    │
│                    │                          │                    │
│                    │  🔒 8+ chars · 1 upper · │                    │
│                    │     1 lower · 1 number · │                    │
│                    │     1 symbol             │                    │
│                    │                          │                    │
│                    │  ✔ Must match · policy ok │                    │
│                    │                          │                    │
│                    │  ┌─────────────────┐     │                    │
│                    │  │   Reset Password│     │                    │
│                    │  └─────────────────┘     │                    │
│                    └─────────────────────────┘                    │
└─────────────────────────────────────────────────────────────────┘
```

> **Attempts/lockout**: the security-question step allows 3 attempts before
> the reset is aborted and the account is temporarily locked. OTP expires
> after 5 minutes and can be resent. On success the user is returned to Login.

### 1.5 MFA Setup — `/settings/security`

```
┌──────────┬──────────────────────────────────────────────────────┐
│ ☰        │  Security / Two-Factor Auth                          │
│          │──────────────────────────────────────────────────────│
│ 📷 Scan  │  ──── Two-Factor Authentication (MFA) ────            │
│ 📅 Hist  │  Require OTP at login      [●─────────────────○]    │
│ 📋 Sched │                                                        │
│ 👤 Prof  │  ┌──────────────────────────────────────────────┐    │
│          │  │ 1. Install an authenticator app              │    │
│          │  │ 2. Scan this QR / enter the secret:          │    │
│          │  │    ┌──────────┐   JBSWY3DPEB2XS2LP            │    │
│          │  │    │ ░▓▒▓░▒  │                                │    │
│          │  │    │ ▒▒░▓▓▒░ │                                │    │
│          │  │    └──────────┘                               │    │
│          │  │ 3. Enter 6-digit code to verify: [______]     │    │
│          │  └──────────────────────────────────────────────┘    │
│          │  ──── Backup Codes ────                               │
│          │  [Generate Backup Codes]   (use if app unavailable)  │
│          │                                                        │
│          │  ──── Security Question ────                           │
│          │  Question: [Select ▼]                                  │
│          │  Answer:   [________]                                  │
│          │                                                        │
│          │            [💾 Save Changes]                           │
│          └───────────────────────────────────────────────────────┘
└──────────┴───────────────────────────────────────────────────────┘
```

### 1.6 MFA Verification — `/login/mfa`

```
┌─────────────────────────────────────────────────────────────────┐
│                    ┌─────────────────────────┐                    │
│                    │   🔐 Two-Factor Auth     │                    │
│                    │   Enter 6-digit code     │                    │
│                    │                          │                    │
│                    │  ┌───┐ ┌───┐ ┌───┐       │                    │
│                    │  │ 7 │ │ 1 │ │ 4 │ ...   │                    │
│                    │  └───┘ └───┘ └───┘       │                    │
│                    │                          │                    │
│                    │  Code from your app /     │                    │
│                    │  backup code             │                    │
│                    │                          │                    │
│                    │  Expires in 03:00        │                    │
│                    │  [Resend code]           │                    │
│                    │                          │                    │
│                    │  ┌─────────────────┐     │                    │
│                    │  │     Verify      │     │                    │
│                    │  └─────────────────┘     │                    │
│                    │                          │                    │
│                    │  Use a backup code ·      │                    │
│                    │  Log out                  │                    │
│                    └─────────────────────────┘                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Student

### 2.1 Student Dashboard — `/student/dashboard`

```
┌──────────┬──────────────────────────────────────────────────────┐
│ ☰        │  Hi, John! 👋                          🔔            │
│          │──────────────────────────────────────────────────────│
│ 📷 Scan  │  ┌──────┐  ┌──────┐  ┌────────┐                     │
│ 📅 Hist  │  │ 85%  │  │  3   │  │   42   │                     │
│ 📋 Sched │  │Rate  │  │Today │  │ Total  │                     │
│ 👤 Prof  │  └──────┘  └──────┘  └────────┘                     │
│          │                                                       │
│          │  ┌─────────────────────────────────────────────┐     │
│          │  │         📷  Scan QR Attendance              │     │
│          │  └─────────────────────────────────────────────┘     │
│          │                                                       │
│          │  ──── Today's Schedule ────                           │
│          │  🟢 CS101 — Software Eng  · 9:00 ✅ Scanned           │
│          │  🟡 MATH202 — Calculus 2  · 11:00 ⏳ Pending          │
│          │  🔴 PHYS101 — Physics 1   · 1:00  ❌ Missed           │
│          │                                                       │
│          │  ──── Recent Activity ────                             │
│          │  ✅ CS101 — 9:02 AM (Just now)                        │
│          │  ⏳ MATH202 — Pending sync                            │
│          │  📅 PHYS101 — Scheduled 1:00 PM                       │
│          └───────────────────────────────────────────────────────┘
└──────────┴───────────────────────────────────────────────────────┘
```

### 2.2 QR Scanner — `/student/scan`

```
┌─────────────────────────────────────────────────────────────────┐
│ ← Back                                        ⚠ offline         │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Session Code                                                     │
│  ┌──────────────────────────────┐  ┌─────────────────────┐       │
│  │ Enter code from projector    │  │   Verify Code       │       │
│  └──────────────────────────────┘  └─────────────────────┘       │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │                                                           │   │
│  │                    ┌── Camera Preview ──┐                 │   │
│  │                    │                    │                 │   │
│  │                    │  ┌──────────────┐  │                 │   │
│  │                    │  │   Align QR   │  │                 │   │
│  │                    │  │   code here  │  │                 │   │
│  │                    │  └──────────────┘  │                 │   │
│  │                    └────────────────────┘                 │   │
│  │                                                           │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                   │
│                  ┌──────────────────────────┐                    │
│                  │     Scan My ID Card      │                    │
│                  └──────────────────────────┘                    │
│                                                                   │
│  After QR: face challenge (blink / turn head)                     │
│  🟢 GPS: High (5m)     📍 CS Lab 101      ⚡ Live Validation     │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 Permission Prompt (Modal)

```
┌─────────────────────────────────────────────────────────────────┐
│                         ┌──────────────────────┐                 │
│                         │    📷 🎯             │                 │
│                         │   Allow Access       │                 │
│                         │                      │                 │
│                         │  Camera needed for   │                 │
│                         │  QR scanning. GPS    │                 │
│                         │  to verify location. │                 │
│                         │                      │                 │
│                         │  ┌────────────────┐  │                 │
│                         │  │ Allow Camera   │  │                 │
│                         │  └────────────────┘  │                 │
│                         │  ┌────────────────┐  │                 │
│                         │  │ Allow GPS      │  │                 │
│                         │  └────────────────┘  │                 │
│                         │                      │                 │
│                         │  No thanks, enter    │                 │
│                         │  manually            │                 │
│                         └──────────────────────┘                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.4 Face Liveness Challenge (overlay)

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                   │
│                          🎥 (live)                               │
│                          Face detected ✔                         │
│                                                                   │
│                  ┌──────────────────────────┐                    │
│                  │   👤  Now do this:       │                    │
│                  │   ┌──────────────────┐   │                    │
│                  │   │   Blink Now      │   │                    │
│                  │   └──────────────────┘   │                    │
│                  │   (or: Turn head left)   │                    │
│                  └──────────────────────────┘                    │
│                                                                   │
│  Challenge 1 of 2 · auto-advances on success                     │
│  Offline: evidence saved · verified after sync                   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.5 Scan Success Overlay

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                   │
│                                                                   │
│                          ✅ (large)                               │
│                                                                   │
│                    Attendance Recorded!                           │
│                       John Doe                                   │
│                    CS101 — 9:02 AM                                │
│                                                                   │
│                    Live · GPS + Face verified                     │
│                                                                   │
│                    Auto-dismissing in 3s...                       │
└─────────────────────────────────────────────────────────────────┘
```

### 2.6 Scan Failure Overlay

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                   │
│                                                                   │
│                          ❌ (large)                               │
│                                                                   │
│                    Attendance Rejected                            │
│                                                                   │
│                ┌──────────────────────────┐                      │
│                │ Already scanned session  │                      │
│                └──────────────────────────┘                      │
│                                                                   │
│              Possible reasons: duplicate,                         │
│              outside geofence, QR/face liveness failed            │
│                                                                   │
│                    ┌──────────────────┐                           │
│                    │    Try Again     │                           │
│                    └──────────────────┘                           │
└─────────────────────────────────────────────────────────────────┘
```

### 2.7 Attendance History — `/student/history`

```
┌──────────┬──────────────────────────────────────────────────────┐
│ ☰        │  Attendance History                                  │
│          │──────────────────────────────────────────────────────│
│ 📷 Scan  │  Semester: [1st Sem 2026 ▼]  Course: [All ▼]         │
│ 📅 Hist  │  Status: [All ▼]  🔍 [Search...]                     │
│ 📋 Sched │  Date: From [Jul 01 ▼]  To [Jul 31 ▼]  [🔍 Apply]    │
│ 👤 Prof  │  ┌──────┬──────────┬─────────┬────────┐              │
│          │  │Date ⇅│Course ▲  │Status ⇅│Time ⇅  │              │
│          │  ├──────┼──────────┼─────────┼────────┤              │
│          │  │Jul28 │  CS101   │ ✅ Present│ 9:02  │              │
│          │  │Jul28 │ MATH202  │ ⏳ Pending│  —    │              │
│          │  │Jul25 │  CS101   │ ❌ Absent │  —    │              │
│          │  │Jul24 │ PHYS101  │ ✅ Present│ 1:05  │              │
│          │  │Jul24 │ MATH202  │ ✅ Present│11:02  │              │
│          │  └──────┴──────────┴─────────┴────────┘              │
│          │  < 1 2 3 >   [🖨 Print]  [📥 Export CSV]              │
│          │                                                       │
│          │  ┌──────────────────────────────────────────────┐    │
│          │  │     Summary: Present 14/18 (78%) ▓▓▓▓▓░░     │    │
│          │  └──────────────────────────────────────────────┘    │
│          └───────────────────────────────────────────────────────┘
└──────────┴───────────────────────────────────────────────────────┘
```

> **Sortable**: every column header (Date, Course, Status, Time) is clickable
> to toggle ascending ⇅ / descending order; the active column shows an ▲/▼
> indicator. **Date-range + category filters** narrow the dataset; results are
> printable or exportable as CSV.

### 2.8 Schedule — `/student/schedule`

```
┌──────────┬──────────────────────────────────────────────────────┐
│ ☰        │  My Schedule                      Week: [Jul 27 ▼]  │
│          │──────────────────────────────────────────────────────│
│ 📷 Scan  │  ┌──────┬──────┬──────┬──────┬──────┬──────┬──────┐│
│ 📅 Hist  │  │ Mon  │ Tue  │ Wed  │ Thu  │ Fri  │ Sat  │ Sun  ││
│ 📋 Sched │  ├──────┼──────┼──────┼──────┼──────┼──────┼──────┤│
│ 👤 Prof  │  │9:00  │      │9:00  │      │9:00  │      │      ││
│          │  │CS101 │      │CS101 │      │CS101 │      │      ││
│          │  │Lab101│      │Lab101│      │Lab101│      │      ││
│          │  ├──────┼──────┼──────┼──────┼──────┼──────┼──────┤│
│          │  │      │11:00 │      │11:00 │      │      │      ││
│          │  │      │MATH  │      │MATH  │      │      │      ││
│          │  │      │ R203 │      │ R203 │      │      │      ││
│          │  ├──────┼──────┼──────┼──────┼──────┼──────┼──────┤│
│          │  │13:00 │      │13:00 │      │13:00 │      │      ││
│          │  │PHYS  │      │PHYS  │      │PHYS  │      │      ││
│          │  │L301  │      │L301  │      │L301  │      │      ││
│          │  └──────┴──────┴──────┴──────┴──────┴──────┴──────┘│
│          │  📍 All classes in Main Building                     │
│          └───────────────────────────────────────────────────────┘
└──────────┴───────────────────────────────────────────────────────┘
```

### 2.9 Notifications — `/student/notifications`

```
┌──────────┬──────────────────────────────────────────────────────┐
│ ☰        │  Notifications                                      │
│          │──────────────────────────────────────────────────────│
│ 📷 Scan  │  ┌────────────────────────────────────────────┐     │
│ 📅 Hist  │  │ ✅ Attendance Recorded                      │     │
│ 📋 Sched │  │   CS101 — Jul 29 · 2 min ago               │     │
│ 👤 Prof  │  └────────────────────────────────────────────┘     │
│          │  ┌────────────────────────────────────────────┐     │
│          │  │ ⏳ Pending Sync (3)                        │     │
│          │  │   Records will sync when online · 5min     │     │
│          │  └────────────────────────────────────────────┘     │
│          │  ┌────────────────────────────────────────────┐     │
│          │  │ 📅 New Class Added                         │     │
│          │  │   ECE101 added to schedule · 1 day ago     │     │
│          │  └────────────────────────────────────────────┘     │
│          │  ┌────────────────────────────────────────────┐     │
│          │  │ ❌ Session Expired                         │     │
│          │  │   MATH202 session ended · 2 days ago       │     │
│          │  └────────────────────────────────────────────┘     │
│          │            [Mark all as read]                       │
│          └───────────────────────────────────────────────────────┘
└──────────┴───────────────────────────────────────────────────────┘
```

### 2.10 Student Profile — `/student/profile`

```
┌──────────┬──────────────────────────────────────────────────────┐
│ ☰        │  My Profile                                         │
│          │──────────────────────────────────────────────────────│
│ 📷 Scan  │                   👤 (avatar)                         │
│ 📅 Hist  │                                                       │
│ 📋 Sched │  Student ID:   2021-01234                            │
│ 👤 Prof  │  Name:         John A. Doe                            │
│          │  Middle Name:  A.                                    │
│          │  Section:      CS-A                                  │
│          │  Course:       BS Computer Science                    │
│          │  Year Level:   3rd Year                               │
│          │  Email:        john.doe@university.edu                │
│          │                                                       │
│          │              ┌──────────────────┐                    │
│          │              │   Edit Profile   │                    │
│          │              └──────────────────┘                    │
│          │                                                       │
│          │  Account: Jun 2026 · Scans: 42                       │
│          └───────────────────────────────────────────────────────┘
└──────────┴───────────────────────────────────────────────────────┘
```

### 2.11 Student Settings — `/student/settings`

```
┌──────────┬──────────────────────────────────────────────────────┐
│ ☰        │  Settings                                           │
│          │──────────────────────────────────────────────────────│
│ 📷 Scan  │  ──── Appearance ────                                │
│ 📅 Hist  │  Theme:   [Light] [Dark]                             │
│ 📋 Sched │                                                       │
│ 👤 Prof  │  ──── Notifications ────                              │
│          │  Push notifications         [●─────────────────○]   │
│          │  Email notifications        [○─────────────────●]   │
│          │                                                       │
│          │  ──── Privacy ────                                    │
│          │  Share GPS for attendance   [●─────────────────○]   │
│          │  Enable camera scanning     [●─────────────────○]   │
│          │                                                       │
│          │  ──── Account ────                                    │
│          │  [Change Password]   [Delete Account]                 │
│          │                                                       │
│          │  App version: 1.0.0                                   │
│          └───────────────────────────────────────────────────────┘
└──────────┴───────────────────────────────────────────────────────┘
```

---

## 3. Professor

### 3.1 Professor Dashboard — `/professor/dashboard`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Professor Dashboard                    🔔        │
│────────────│────────────────────────────────────────────────────│
│ 📊 Dash    │  ┌──────┐  ┌──────┐  ┌────────┐                   │
│ 📷 Live    │  │ 3/5  │  │ 120  │  │  92%   │                   │
│ 📅 History │  │Sess. │  │Stud. │  │ Avg    │                   │
│ 📋 Reports │  └──────┘  └──────┘  └────────┘                   │
│ 👥 Courses │                                                   │
│ ⚙️ Settings│  ──── Today's Sessions ────                        │
│            │  🟢 CS101 — Software Eng · 18/30  [View Live]     │
│            │  🟡 MATH202 — Calculus 2 · Not yet  [Open Ses.]   │
│            │                                                   │
│            │  ──── Quick Actions ────                           │
│            │  [+ New Session]  [📄 Export Report]               │
│            └─────────────────────────────────────────────────────┘
└────────────┴─────────────────────────────────────────────────────┘
```

### 3.2 Open Session — `/professor/sessions/create`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Open New Session                                 │
│────────────│────────────────────────────────────────────────────│
│ 📊 Dash    │  Select Course:                                    │
│ 📷 Live    │  ┌─────────────────────────────────────────┐      │
│ 📅 History │  │ CS101 — Software Engineering ▼          │      │
│ 📋 Reports │  └─────────────────────────────────────────┘      │
│ 👥 Courses │                                                   │
│ ⚙️ Settings│  Geofence Radius: [10m] [20m] [30m] [50m] [100m]│
│            │  Classroom: CS Lab 101 (14.5995°N, 120.9842°E)    │
│            │  Duration: [1 hour ▼]                             │
│            │                                                   │
│            │  HMAC Preview:  A7X-9K2M                          │
│            │                                                   │
│            │  ┌─────────────────────────────────────────┐      │
│            │  │     🔐 Generate Session Code            │      │
│            │  └─────────────────────────────────────────┘      │
│            └─────────────────────────────────────────────────────┘
└────────────┴─────────────────────────────────────────────────────┘
```

### 3.3 Active Session / Projector Mode — `/professor/sessions/active/[id]`

```
┌─────────────────────────────────────────────────────────────────┐
│ ← Back          Active: CS101 — Software Eng        [Close]    │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│              ┌───────────────────────────────────────────┐       │
│              │    Session Code — Show on projector        │       │
│              │          A 7 X - 9 K 2 M                   │       │
│              │        (large, projector-ready)            │       │
│              └───────────────────────────────────────────┘       │
│                                                                   │
│                      ⏱ Expires in: 01:47:23                      │
│                                                                   │
│    ┌────────┐          ┌────────┐          ┌────────┐            │
│    │   30   │          │   18   │          │   12   │            │
│    │Enrolled│          │Scanned │          │Remaining│           │
│    └────────┘          └────────┘          └────────┘            │
│                                                                   │
│  ──── Live Feed (auto-refresh 3s) ────                            │
│  ┌──────┬──────────────┬──────────┬──────────┐                   │
│  │ Time ⇅│   Name ⇅     │ Status ⇅  │  GPS ⇅   │                   │
│  ├──────┼──────────────┼──────────┼──────────┤                   │
│  │09:01 │ Alice Santos │ ✅ Live  │ 🟢 In   │                   │
│  │09:02 │ Bob Cruz     │ ✅ Live  │ 🟢 In   │                   │
│  │09:03 │ Carol Tan    │ ⏳ Pend  │ 🔴 Out  │                   │
│  │09:04 │ Emma Lim     │ ✅ Live  │ 🟢 In   │                   │
│  └──────┴──────────────┴──────────┴──────────┘                   │
│                                                                   │
│           [📥 Export Current]  [🖨 Print]  [📋 View All]         │
└─────────────────────────────────────────────────────────────────┘
```

> Live-feed columns are sortable (▲/▼) and the current feed can be
> exported or printed as-is.

### 3.4 Professor Attendance List — `/professor/attendance`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Attendance Records                                │
│────────────│────────────────────────────────────────────────────│
│ 📊 Dash    │  Course:[CS101 ▼] Session:[All ▼] Status:[All ▼]  │
│ 📷 Live    │  Date: From [Jul 01 ▼] To [Jul 31 ▼] [🔍 Apply]   │
│ 📅 History │  ┌──────┬──────────────┬──────────┬────────┐      │
│ 📋 Reports │  │ Date ⇅│ Student ⇅     │ Status ⇅  │ Time ⇅  │      │
│ 👥 Courses │  ├──────┼──────────────┼──────────┼────────┤      │
│ ⚙️ Settings│  │Jul29 │ Alice Santos │ ✅ Present│ 09:01 │      │
│            │  │Jul29 │ Bob Cruz     │ ✅ Present│ 09:02 │      │
│            │  │Jul29 │ Carol Tan    │ ❌ Absent │  —    │      │
│            │  │Jul28 │ Dave Reyes   │ ⏳ Pending│ 08:55 │      │
│            │  │Jul28 │ Emma Lim     │ ✅ Present│ 08:59 │      │
│            │  └──────┴──────────────┴──────────┴────────┘      │
│            │  < 1 2 3 >  [🖨 Print]  [📥 Export]  [📷 View Live]│
│            │  Legend: ✅ Present ❌ Absent ⏳ Pending             │
│            └──────────────────────────────────────────────────────┘
└────────────┴──────────────────────────────────────────────────────┘
```

> Column headers are sortable (click to toggle ▲/▼). Filters combine
> category (Course / Session / Status) with a **date-range** (From–To).

### 3.5 Professor Session History — `/professor/sessions/history`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Session History                                   │
│────────────│────────────────────────────────────────────────────│
│ 📊 Dash    │  Course: [All Courses ▼]  Date: [Jul 01→Jul 31 ▼] │
│ 📷 Live    │  ┌──────┬──────────┬──────────┬──────┐            │
│ 📅 History │  │ Date ⇅│  Code ⇅  │ Present ⇅ │ Rate ▲ │            │
│ 📋 Reports │  ├──────┼──────────┼──────────┼──────┤            │
│ 👥 Courses │  │Jul29 │ A7X-9K2M │ 18/30    │ 60%  │            │
│ ⚙️ Settings│  │Jul28 │ B4Y-3L7N │ 28/30    │ 93%  │            │
│            │  │Jul25 │ C8Z-5P1Q │ 25/30    │ 83%  │            │
│            │  │Jul24 │ D2W-8R4T │ 30/30    │ 100% │            │
│            │  └──────┴──────────┴──────────┴──────┘            │
│            │  Average: 84% over 12 sessions                     │
│            │  < 1 2 3 >   [🖨 Print]  [📥 Export CSV]            │
│            │  Click row → full attendance detail                │
│            └──────────────────────────────────────────────────────┘
└────────────┴──────────────────────────────────────────────────────┘
```

> Column headers are sortable (toggle ▲/▼). Supports date-range + course
> filtering, printing, and CSV export.

### 3.6 Professor Courses — `/professor/courses`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  My Courses                                       │
│────────────│────────────────────────────────────────────────────│
│ 📊 Dash    │  ┌─── CS101 — Software Engineering ──────────┐   │
│ 📷 Live    │  │  MWF 9:00-10:30 · Lab 101 · 30 students   │   │
│ 📅 History │  │  [🔐 Open Session] [📊 View Reports]       │   │
│ 📋 Reports │  └────────────────────────────────────────────┘   │
│ 👥 Courses │                                                   │
│ ⚙️ Settings│  ┌─── MATH202 — Calculus 2 ──────────────────┐   │
│            │  │  TTH 11:00-12:30 · Rm 203 · 35 students  │   │
│            │  │  [🔐 Open Session] [📊 View Reports]       │   │
│            │  └────────────────────────────────────────────┘   │
│            │                                                   │
│            │  ┌─── PHYS101 — Physics 1 ───────────────────┐   │
│            │  │  MWF 1:00-2:30 · Lab 301 · 25 students    │   │
│            │  │  [🔐 Open Session] [📊 View Reports]       │   │
│            │  └────────────────────────────────────────────┘   │
│            │  Total: 3 courses · Active session: 1             │
│            └──────────────────────────────────────────────────────┘
└────────────┴──────────────────────────────────────────────────────┘
```

### 3.7 Professor Reports — `/professor/reports`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Attendance Reports                                │
│────────────│────────────────────────────────────────────────────│
│ 📊 Dash    │  [Daily] [Weekly] [Monthly]  Course: [CS101 ▼]   │
│ 📷 Live    │                                                   │
│ 📅 History │  ┌──────────────────────────────────────────┐    │
│ 📋 Reports │  │       Attendance Rate — This Week         │    │
│ 👥 Courses │  │                                           │    │
│ ⚙️ Settings│  │  88% ██ 95% ██ 72% ██ 90% ██ 62% ██     │    │
│            │  │  Mon  Tue  Wed  Thu  Fri                  │    │
│            │  └──────────────────────────────────────────┘    │
│            │  Average: 81% · Total sessions: 8                │
│            │                                                   │
│            │  [📥 Download CSV]   [📄 Download PDF]            │
│            └──────────────────────────────────────────────────────┘
└────────────┴──────────────────────────────────────────────────────┘
```

### 3.8 Professor Export — `/professor/attendance/export`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Export Attendance                                 │
│────────────│────────────────────────────────────────────────────│
│ 📊 Dash    │  Course: [CS101 — Software Engineering ▼]          │
│ 📷 Live    │  Date Range:                                       │
│ 📅 History │  From: [Jul 01, 2026 ▼]  To: [Jul 29, 2026 ▼]    │
│ 📋 Reports │  Format: ○ CSV  ● PDF  ○ Excel  ○ Print          │
│ 👥 Courses │  Include:                                          │
│ ⚙️ Settings│  ☑ Student ID  ☑ Name  ☑ Timestamp               │
│            │  ☑ GPS Coordinates  ☐ Liveness Status             │
│            │                                                   │
│            │  ┌─────────────────────────────────────────┐      │
│            │  │         📥 Download Report              │      │
│            │  └─────────────────────────────────────────┘      │
│            └──────────────────────────────────────────────────────┘
└────────────┴──────────────────────────────────────────────────────┘
```

### 3.9 Professor Profile / Settings

Same layout as Student Profile (2.10) and Settings (2.11). Fields differ: Employee ID, Department, Assigned Courses. Settings identical.

---

## 4. Admin

### 4.1 Admin Dashboard — `/admin/dashboard`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Admin Dashboard                       🔔        │
│────────────│────────────────────────────────────────────────────│
│ 📊 Dash    │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐             │
│ 👤 Students│  │1,240 │ │  45  │ │  12  │ │ 89%  │             │
│ 👨‍🏫 Profs │  │Students│ │Prof. │ │Courses│ │ Rate │             │
│ 📚 Courses │  └──────┘ └──────┘ └──────┘ └──────┘             │
│ 📈 Reports │                                                   │
│ 🔍 Audit   │  ──── Today's Activity ────                        │
│ ⚙️ System  │  Active: 5 · Scans: 142 · Pending: 3              │
│            │                                                   │
│            │  ──── Quick Actions ────                           │
│            │  [📥 Import]  [📈 Advance Yr]  [💾 Backup]        │
│            │                                                   │
│            │  ──── Recent Scans (last 10) ────                 │
│            │  09:01 Alice → CS101 ✅                           │
│            │  09:02 Bob   → MATH202 ❌ (GPS)                   │
│            │  09:03 Carol → PHYS101 ✅                         │
│            │  09:04 Dave  → CS101 ⏳ (pending)                 │
│            └──────────────────────────────────────────────────────┘
└────────────┴──────────────────────────────────────────────────────┘
```

### 4.2 Admin Student Management — `/admin/students`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Student Management                [+Add] [Import]│
│────────────│────────────────────────────────────────────────────│
│ 📊 Dash    │  🔍 [Search...]    Course: [All ▼]  Year: [All ▼]│
│ 👤 Students│  Section: [All ▼]  Date: [From—To ▼] [🔍 Apply]  │
│ 👨‍🏫 Profs │  ┌──────────┬──────────────┬──────┬───┬───┬───────┐  │
│ 📚 Courses │  │ ID ⇅     │ Name ⇅       │Course│Sec│ Yr│Status │  │
│ 📈 Reports │  ├──────────┼──────────────┼──────┼───┼───┼───────┤  │
│ 🔍 Audit   │  │2021-001 │ Alice Santos │  CS  │ A │ 3 │  ✅  │  │
│ ⚙️ System  │  │2022-002 │ Bob Cruz     │  IT  │ B │ 2 │  ✅  │  │
│            │  │2023-003 │ Carol Tan    │  CS  │ A │ 1 │  ✅  │  │
│            │  │2024-004 │ Dave Reyes   │ ECE  │ C │ 4 │  🚫  │  │
│            │  │2025-005 │ Emma Lim     │  CS  │ B │ 1 │  ✅  │  │
│            │  └──────────┴──────────────┴──────┴───┴───┴───────┘  │
│            │  < 1 2 >   [🔓 Deactivate] [🔑 Reset Pwd]         │
│            │            [🗃 Archive]                            │
│            └──────────────────────────────────────────────────────┘
└────────────┴──────────────────────────────────────────────────────┘
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
│ ☰          │  Import Students from CSV                          │
│────────────│────────────────────────────────────────────────────│
│            │  Step 1: Download Template                         │
│            │  [📥 Download CSV Template]                        │
│            │  student_id, first_name, middle_name, last_name,   │
│            │  email, course, section, year_level                 │
│            │                                                   │
│            │  Step 2: Upload File                               │
│            │  ┌──────────────────────────────────────────┐    │
│            │  │          Drag & drop CSV here             │    │
│            │  │          or click to browse               │    │
│            │  └──────────────────────────────────────────┘    │
│            │                                                   │
│            │  Step 3: Preview                                  │
│            │  ┌──────┬───────┬─────┬──────┬──────────┬───┬───┐│
│            │  │ ID   │ FName │ MName│ LName│ Email    │Sec│ Yr││
│            │  ├──────┼───────┼─────┼──────┼──────────┼───┼───┤│
│            │  │2025- │ New   │      │ Stu  │ s@univ...│ A │ 1 ││
│            │  └──────┴───────┴─────┴──────┴──────────┴───┴───┘│
│            │  25 new · 0 duplicates · 3 errors                │
│            │  ┌──────────────────────────────────────────┐   │
│            │  │        Confirm Import (25)                │   │
│            │  └──────────────────────────────────────────┘   │
│            └──────────────────────────────────────────────────────┘
└────────────┴──────────────────────────────────────────────────────┘
```

### 4.4 Admin Professor Management — `/admin/professors`

Same CRUD pattern as Student Management (4.2), but this screen **seeds the
professor records that professors claim at registration**. Columns:
Employee ID, Name (First/Middle/Last), Department, **Email** (the
registration lookup key), Courses Assigned, Status, **Claim** (Unclaimed ✅
/ Claimed). Actions: [+Add] [Import CSV] (template: `employee_id,
first_name, middle_name, last_name, email, department`), [Deactivate]
[Reset Pwd] [Archive]. Create/Edit form includes multi-select course
assignment.

### 4.5 Admin Course Management — `/admin/courses`

Same CRUD pattern. Columns: Code, Name, Professor, Schedule, Students. Form includes GPS coordinates (lat/lng) tied to the geofencing system.

### 4.6 Admin Attendance Overview — `/admin/attendance/overview`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Attendance Overview                               │
│────────────│────────────────────────────────────────────────────│
│            │  Filters: Course [All] Prof [All] Date [Range ▼]  │
│            │                                                   │
│            │  ┌──────────────────────────────────────────┐    │
│            │  │ Course ⇅   │ Sessions ⇅ │ Avg ⇅  │ Trend ⇅ │    │
│            │  ├────────────┼──────────┼────────┼────────┤    │
│            │  │  CS101     │   12     │  88%   │   ↑    │    │
│            │  │  MATH202   │   10     │  72%   │   ↓    │    │
│            │  │  PHYS101   │    8     │  91%   │   →    │    │
│            │  │  ECE101    │    6     │  95%   │   ↑    │    │
│            │  └────────────┴──────────┴────────┴────────┘    │
│            │        [🖨 Print]  [📥 Export Overview]           │
│            └──────────────────────────────────────────────────────┘
└────────────┴──────────────────────────────────────────────────────┘
```

### 4.7 Admin Attendance Analytics — `/admin/attendance/analytics`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Attendance Analytics                              │
│────────────│────────────────────────────────────────────────────│
│            │  ──── Per-Course Comparison ────                    │
│            │  CS101  ████████████████░░░░  88%                  │
│            │  MATH202 ██████████████░░░░░░  72%                 │
│            │  PHYS101 █████████████████░░  91%                  │
│            │  ECE101  ███████████████████  95%                  │
│            │                                                   │
│            │  ──── Daily Average ────                           │
│            │  Mon ██████████░░  80%   Wed ████████░░  78%      │
│            │  Tue ████████████  92%   Thu █████████░  85%      │
│            │  Fri ██████░░░░░░  62%                             │
│            │                                                   │
│            │  ⚠ Low Attendance: MATH202 (5 students < 60%)     │
│            │                                                   │
│            │  ──── Predictive: At-Risk (next 2 weeks) ────      │
│            │  J. Santos (MATH202) 79% · A. Reyes (CS101) 74%   │
│            │                                                   │
│            │  ──── Prescriptive: Recommended Actions ────      │
│            │  ✓ Alert at-risk students   ✓ Hold review session  │
│            │  ✓ Notify prof of Friday dip (62%)                 │
│            │              [📥 Export Analytics]                  │
│            └──────────────────────────────────────────────────────┘
└────────────┴──────────────────────────────────────────────────────┘
```

### 4.8 Admin Reports — `/admin/reports`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Reports                                           │
│────────────│────────────────────────────────────────────────────│
│            │  [Attendance] [Students] [Professors]             │
│            │                                                   │
│            │  ──── Attendance Tab ────                         │
│            │  Filters: Course [All] Date [Range ▼]             │
│            │  ┌──────┬──────────┬────────┐                    │
│            │  │ Date ⇅│ Course ⇅ │ Rate ▲ │                    │
│            │  ├──────┼──────────┼────────┤                    │
│            │  │Jul29 │ CS101    │  88%   │                    │
│            │  │Jul29 │ MATH202  │  72%   │                    │
│            │  └──────┴──────────┴────────┘                    │
│            │                                                   │
│            │  [📥 Export CSV] [📄 Export PDF] [🖨 Print]        │
│            └──────────────────────────────────────────────────────┘
└────────────┴──────────────────────────────────────────────────────┘
```

### 4.9 Admin Audit Logs — `/admin/audit-logs`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Audit Logs                                       │
│────────────│────────────────────────────────────────────────────│
│            │  Date: [Jul 01 → Jul 29 ▼]  Action: [All ▼]      │
│            │  ┌──────┬────────────┬──────────────────────┐    │
│            │  │ Time ⇅│ User ▲     │ Action ⇅            │    │
│            │  ├──────┼────────────┼──────────────────────┤    │
│            │  │09:01 │ A. Santos  │ Scan CS101           │    │
│            │  │08:55 │ Prof.Smith │ Opened session CS101 │    │
│            │  │08:30 │ Admin      │ Imported CSV (25)    │    │
│            │  │08:00 │ System     │ Year-advancement run │    │
│            │  └──────┴────────────┴──────────────────────┘    │
│            │  < 1 2 3 >  [🖨 Print]  [📥 Export Logs]          │
│            └──────────────────────────────────────────────────────┘
└────────────┴──────────────────────────────────────────────────────┘
```

### 4.10 Admin System Settings — `/admin/system/settings`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  System Settings                                   │
│────────────│────────────────────────────────────────────────────│
│            │  ──── Attendance Defaults ────                      │
│            │  Geofence Radius: [30] meters                      │
│            │  Session Duration: [2] hours                       │
│            │                                                   │
│            │  ──── Data Management ────                         │
│            │  Year + Section Promotion: [Promote All ➜]        │
│            │  Promotes all students to the next year level and  │
│            │  moves their section (A→B→C) for the new year.     │
│            │  Last advanced: Jun 2026                           │
│            │                                                   │
│            │  ──── Backup ────                                  │
│            │  Last backup: Jul 28, 2026 3:00 AM                 │
│            │  [💾 Backup Now] [📥 Download Backup]              │
│            │                                                   │
│            │  ──── Maintenance ────                             │
│            │  Pending sync: 3   [Force Sync] [Clean Up]        │
│            │                                                   │
│            │              [💾 Save Changes]                     │
│            └──────────────────────────────────────────────────────┘
└────────────┴──────────────────────────────────────────────────────┘
```

### 4.11 Admin Archive — `/admin/students/archive`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Archived Students                                 │
│────────────│────────────────────────────────────────────────────│
│            │  Graduated or unenrolled students moved here.      │
│            │  ┌──────────┬──────────────┬──────┬───────────┐  │
│            │  │ ID ▲     │ Name ⇅       │Course│ Archived ⇅ │  │
│            │  ├──────────┼──────────────┼──────┼───────────┤  │
│            │  │2020-006 │ Grace Lopez  │  CS  │ Jun 2026  │  │
│            │  │2020-007 │ Henry Tan    │ ECE  │ Jun 2026  │  │
│            │  │2021-008 │ Isabel M.    │  IT  │ Jun 2026  │  │
│            │  └──────────┴──────────────┴──────┴───────────┘  │
│            │  [Restore Selected] [🗑 Permanently Delete]       │
│            └──────────────────────────────────────────────────────┘
└────────────┴──────────────────────────────────────────────────────┘
```

### 4.12 Admin Profile

Same as Student Profile (2.10). Fields: Admin ID, Name (First/Middle/Last), Email, Role (Super Admin / Admin), Last Login.

### 4.13 Admin Liveness Review — `/admin/liveness/review`

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Liveness Review                                    │
│────────────│────────────────────────────────────────────────────│
│            │  Flagged scans awaiting manual review               │
│            │  ┌──────┬────────────┬──────────┬──────────────┐   │
│            │  │ Time │ Student    │ Reason   │ Evidence     │   │
│            │  ├──────┼────────────┼──────────┼──────────────┤   │
│            │  │09:02 │ J. Santos  │ GPS 35m  │ [View bundle] │  │
│            │  │08:55 │ A. Reyes   │ Face 62% │ [View bundle] │  │
│            │  └──────┴────────────┴──────────┴──────────────┘   │
│            │  [Approve] [Reject] [🖨 Print] [Export log]          │
│            └──────────────────────────────────────────────────────┘
└────────────┴──────────────────────────────────────────────────────┘
```

### 4.14 Admin Users — `/admin/users`

Admin accounts are **never self-registered**. The first admin is seeded at
deployment; this screen manages all subsequent ones.

```
┌────────────┬────────────────────────────────────────────────────┐
│ ☰          │  Admin Users                       [+Add Admin]    │
│────────────│────────────────────────────────────────────────────│
│ 📊 Dash    │  🔍 [Search...]    Role: [All ▼]  Status: [All ▼] │
│ 👤 Students│  ┌──────────────┬──────────────┬────────┬────────┬┐ │
│ 👨‍🏫 Profs │  │ Name ⇅       │ Email        │ Role   │ Status ││ │
│ 📚 Courses │  ├──────────────┼──────────────┼────────┼────────┼┤ │
│ 📈 Reports │  │ K. Santos    │ karla@...    │ Super  │  ✅    ││ │
│ 🔍 Audit   │  │ J. Reyes     │ jose@...     │ Admin  │  🚫    ││ │
│ ⚙️ System  │  │  A. Lim     │ ana@...      │ Admin  │  ✅    ││ │
│            │  └──────────────┴──────────────┴────────┴────────┴┘ │
│            │  < 1 2 >  [🔓 Deactivate] [🔑 Reset Pwd]            │
│            │           [🗃 Archive]                               │
│            │                                                       │
│            │  [+Add Admin] form:                                  │
│            │  Name (First/Middle/Last) · Email · Role:            │
│            │  [Super Admin ▼]  · Send temp password? ☑            │
│            └──────────────────────────────────────────────────────┘
└────────────┴──────────────────────────────────────────────────────┘
```

> Mirrors the Student/Professor management pattern: sortable headers,
> search + category filters, deactivate instead of delete, archive, and
> admin password reset. Only a Super Admin can manage other admins.

---

## 5. Shared & Global

### 5.1 404 Error Page — `/+error`

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                   │
│                          🔍 404                                  │
│                    Page Not Found                                │
│                                                                   │
│            The page doesn't exist or you don't have              │
│            permission to access it.                              │
│                                                                   │
│                  ┌──────────────────────┐                       │
│                  │  Go to Dashboard     │                       │
│                  └──────────────────────┘                       │
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
│ ⚠ You are offline · Records will sync when connected.  [✕]     │
│                                                    3 pending   │
│ (2 include face-liveness evidence — verified after sync)        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. Screen Map

### Navigation Flow

```
                    ┌─────────────┐
                    │  Landing    │
                    └──────┬──────┘
                           ▼
                    ┌─────────────┐
                    │   Login     │ ←─── Register
                    │   (+Captcha)│      Forgot Password (4-step)
                    └──────┬──────┘
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
   ┌──────────┐    ┌───────────┐    ┌───────────┐
   │ Student  │    │ Professor │    │  Admin    │
   │Dash(2.1) │    │Dash (3.1) │    │Dash (4.1) │
   ├──────────┤    ├───────────┤    ├───────────┤
   │Scan(2.2) │    │Open Ses   │    │Students   │
   │Live(2.4) │    │Act Ses    │    │Profs (4.4)│
   │Hist(2.7) │    │AttList    │    │Courses(4.5)│
   │Sched(2.8)│    │SesHist    │    │AttOver    │
   │Notif(2.9)│    │Courses    │    │Review(4.13)│
   │Prof(2.10)│    │Reports    │    │Analytics  │
   │Set(2.11) │    │Export     │    │Reports    │
│          │    │Prof/Set   │    │Audit      │
    │          │    │           │    │Settings   │
    │          │    │           │    │Archive    │
    │          │    │           │    │Profile    │
    │          │    │           │    │Users      │
    └──────────┘    └───────────┘    └───────────┘
```

### All 39 Screens by Route

| # | Screen | Route | Role |
|---|--------|-------|------|
| 1 | Landing | `/` | Public |
| 2 | Login | `/login` | Public |
| 3 | Register | `/register` | Public |
| 4 | Forgot Password (4-step) | `/forgot-password` | Public |
| 5 | MFA Setup | `/settings/security` | All |
| 6 | MFA Verification | `/login/mfa` | Public |
| 7 | Dashboard | `/student/dashboard` | Student |
| 8 | QR Scanner | `/student/scan` | Student |
| 9 | Permission Prompt | (modal) | Student |
| 10 | Face Liveness Challenge | (overlay) | Student |
| 11 | Scan Success | (overlay) | Student |
| 12 | Scan Failure | (overlay) | Student |
| 13 | History | `/student/history` | Student |
| 14 | Schedule | `/student/schedule` | Student |
| 15 | Notifications | `/student/notifications` | Student |
| 16 | Profile | `/student/profile` | Student |
| 17 | Settings | `/student/settings` | Student |
| 18 | Dashboard | `/professor/dashboard` | Professor |
| 19 | Open Session | `/professor/sessions/create` | Professor |
| 20 | Active Session | `/professor/sessions/active/[id]` | Professor |
| 21 | Attendance List | `/professor/attendance` | Professor |
| 22 | Session History | `/professor/sessions/history` | Professor |
| 23 | Courses | `/professor/courses` | Professor |
| 24 | Reports | `/professor/reports` | Professor |
| 25 | Export | `/professor/attendance/export` | Professor |
| 26 | Dashboard | `/admin/dashboard` | Admin |
| 27 | Student Mgmt | `/admin/students` | Admin |
| 28 | CSV Import | `/admin/students/import` | Admin |
| 29 | Professor Mgmt | `/admin/professors` | Admin |
| 30 | Course Mgmt | `/admin/courses` | Admin |
| 31 | Attendance Overview | `/admin/attendance/overview` | Admin |
| 32 | Liveness Review | `/admin/liveness/review` | Admin |
| 33 | Analytics | `/admin/attendance/analytics` | Admin |
| 34 | Reports | `/admin/reports` | Admin |
| 35 | Audit Logs | `/admin/audit-logs` | Admin |
| 36 | System Settings | `/admin/system/settings` | Admin |
| 37 | Archive | `/admin/students/archive` | Admin |
| 38 | Admin Users | `/admin/users` | Admin |
| 39 | 404 Error | `/+error` | Global |

---

## Design Notes

- **All screens** are mobile-responsive: sidebar collapses to bottom tab bar on small screens
- **Permission prompts** (camera + GPS) appear before first scanner use
- **Face liveness** inserts a challenge step (blink / turn head) between QR scan and result; offline scans queue evidence for later verification
- **Offline banner** appears on all authenticated screens when connection is lost
- **Prof/Admin profile & settings** screens mirror the student layouts (2.10, 2.11) with role-specific fields
- **CRUD screens** (students, professors, courses) follow the same create/edit/list pattern
- **Projector mode** (3.3) renders full-screen with large session code visible from the back of a classroom
- **Sortable tables**: every data table (2.7, 3.4, 3.5, 4.2, 4.6, 4.8, 4.9, 4.11, 4.14) has clickable column headers that toggle ascending/descending with an ▲/▼ indicator, plus **category + date-range filters** and **Print / CSV / PDF** actions
- **Password policy** (all accounts, incl. reset & admin reset): minimum 8 characters with at least 1 uppercase, 1 lowercase, 1 number and 1 symbol (alphanumeric + symbol)
- **Account security**: login is protected by **Captcha**; optional **MFA (OTP)** via authenticator app; **Forgot Password** is a 4-step flow (email + captcha → security question w/ 3-attempt limit → OTP → new/confirm password); accounts lock temporarily after 5 failed logins
- **Claim-based registration**: students and professors self-register with email + password; the email must match an **admin-seeded record** (roster CSV / professor management), and an **OTP sent to that email** proves ownership before the account is linked. Nothing is typed — name/course/section come from the seeded record. Student ID is only the QR/attendance key, never entered at registration
- **Soft delete / deactivate**: records are deactivated (`is_active=false`) rather than deleted; permanent deletion only from the Archive screen
- **Admin reset**: admins can reset any user's password (temp password set; user prompted to change on next login)
- **Admin provisioning**: no public admin registration — the first admin is seeded at deployment as **Super Admin**; additional admins are managed on the Admin Users screen (4.14, Super Admin only)
- **Year + Section promotion**: admin bulk-promotes all students to the next year level and section each academic year (4.10)

---

*Prepared for Software Engineering 1 — Wireframe Proposal*
