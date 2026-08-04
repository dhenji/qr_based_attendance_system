# QR-Code Based Offline-Capable Attendance System with Anti-Spoofing

**Presenters:** Presenter 1 · Presenter 2 · Presenter 3

**Course & Section:** `[Course & Section]`

**Subject:** `[Subject]`

**Instructor:** `[Instructor's Name]`

**Date:** `[Date]`

---

## Introduction

**What is this project?**

An attendance system that uses the QR codes already printed on student ID cards. Instead of manual roll call, students scan their ID card QR using their phone — attendance is recorded instantly.

**Why is it important?**

- Manual attendance wastes **5–10 minutes** of every class
- Professors lose valuable lecture time
- Paper records are easily lost or damaged

**Purpose of the system:**

- Automate attendance recording
- Prevent fraudulent submissions
- Work reliably even without internet

---

## Problem Statement

**The Real-World Problem**

- **Slow process** — Calling names one by one takes too long
- **Fraud** — Students sign for absent classmates or share QR photos
- **Unreliable internet** — Campus connectivity is not always stable
- **Lost records** — Paper sheets get misplaced

**Who is affected?**

| Person | Impact |
|--------|--------|
| **Professors** | Lost lecture time, inaccurate records |
| **Students** | Unfair attendance marking, wasted time |
| **Administrators** | No reliable attendance data for reporting |

---

## Project Description

**What the system does**

A Progressive Web Application (PWA) that:

1. Scans the QR code from existing campus ID cards
2. Extracts the student ID number embedded in the QR
3. Validates attendance through **multi-layer anti-spoofing**
4. Works **offline** by storing records locally and auto-syncing later
5. Provides **dashboards and reports** for professors

**Main Features**

| Feature | Purpose |
|---------|---------|
| QR Scanning | Decode student ID from ID card QR |
| Session Codes | Professor shares a time-limited code |
| GPS Verification | Ensures student is in the classroom |
| Liveness Detection | Distinguishes physical card from a photo |
| Offline Mode | Stores attendance when no internet |
| Dashboard | Real-time attendance view & reports |

**How it solves the problem**

- Eliminates manual roll call → **saves 5–10 min per class**
- Multi-layer validation → **prevents cheating**
- Offline capability → **works anywhere, anytime**

---

## Target Users

| User | Role |
|------|------|
| **Professors** | Open sessions, view real-time attendance, generate reports |
| **Students** | Scan own ID card QR, mark attendance in seconds, no app needed |
| **Administrators** | Import rosters from CSV, manage courses, export reports |

---

## System Flow

### Main Attendance Flow

```mermaid
sequenceDiagram
    actor Professor
    actor Student
    participant Server

    Professor->>Server: Login
    Professor->>Server: Select course
    Professor->>Server: Click "Open Session"
    Server->>Server: Generate HMAC-signed code
    Server-->>Professor: Session code
    Professor-->>Student: Code on projector

    Student->>Student: Enter session code
    Student->>Student: Scan QR on ID card
    Student->>Student: Capture GPS
    Student->>Server: Submit {student_id, session_code, gps}

    Server->>Server: 1. HMAC verification
    Server->>Server: 2. GPS geofencing (Haversine)
    Server->>Server: 3. Live QR liveness check
    Server->>Server: 4. One-scan-per-session check
    Server->>Server: 5. Enrollment check

    alt All checks pass
        Server-->>Student: ✅ Attendance recorded
        Server-->>Professor: Student marked present
    else Any check fails
        Server-->>Student: ❌ Attendance rejected
    end
```

### Offline Mode

```mermaid
flowchart TD
    A[Internet Down] --> B[Student scans QR]
    B --> C[Server unreachable]
    C --> D[Record saved to local IndexedDB]
    D --> E[Status: Pending Sync]
    E --> F[Internet Restored]
    F --> G[Service Worker detects connectivity]
    G --> H[Auto-sync pending records]
    H --> I{Server validates}
    I -->|Valid| J[Attendance confirmed]
    I -->|Invalid| K[Flagged for review]
```

### Anti-Spoofing Layers

```mermaid
flowchart LR
    A[Student submits<br>attendance] --> B{Session Code<br>HMAC-SHA256}
    B -->|Valid| C{GPS Geofencing<br>Haversine}
    B -->|Invalid| X[Rejected ❌]
    C -->|Within range| D{Live QR Detection<br>Reflection analysis}
    C -->|Outside range| X
    D -->|Physical card| E{One Scan<br>Per Session}
    D -->|Screenshot| X
    E -->|First scan| F{Enrollment<br>Check}
    E -->|Duplicate| X
    F -->|Enrolled| G[✅ Attendance Recorded]
    F -->|Not enrolled| X
```

### Input → Process → Output

| Input | Process | Output |
|-------|---------|--------|
| QR code scan | Decode student ID from QR | Student identified |
| GPS coordinates | Haversine distance formula | Location verified ✅/❌ |
| Session code | HMAC-SHA256 verification | Session valid ✅/❌ |
| All inputs combined | Multi-layer validation | Attendance recorded/rejected |

---

## Conclusion

**Summary**

This project proposes a QR-based attendance system that:
- Automates the entire attendance process
- Prevents fraud through session codes, GPS, and liveness detection
- Works with or without internet
- Uses existing student ID cards — no new hardware needed

**Expected Benefits**

| Benefit | Impact |
|---------|--------|
| Speed | Under 1 second per student |
| Accuracy | Zero fraudulent entries |
| Convenience | No app to install, works in any browser |
| Reliability | Works even when internet is down |

**Why it should be developed**

Manual attendance is a daily problem in every classroom. This system solves it using resources already available (student ID QR codes) with modern anti-spoofing techniques — saving time, preventing fraud, and providing reliable data for the entire institution.

---

### Thank You

**Questions?**

---

*Presented for [Subject] · [Course & Section]*
