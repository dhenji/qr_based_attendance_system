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
- Uses a session code (shown by the professor) + GPS location to prevent cheating
- Works even without internet by saving attendance locally and uploading later
- Automatically updates student year levels each school year

## 5. Target Users

- Professors — to open sessions and view attendance reports
- Students — to scan their ID and mark attendance
- Administrators — to manage student rosters and generate reports

## 6. Features

| Feature          | Purpose                                                       |
| ---------------- | ------------------------------------------------------------- |
| QR Code Scanning | Scan student ID card QR using phone camera                    |
| Session Code     | Professor shares a code; required to submit attendance        |
| GPS Verification | Ensures student is inside the classroom                       |
| Face Liveness    | Blink/head-turn challenges to block photo, replay & distortion tricks |
| Offline Mode     | Saves attendance locally when no internet; auto-uploads later |
| Student Roster   | Import student from CSV file                                  |
| Dashboard        | View attendance in real time                                  |
| Analytics        | At-risk forecasting and recommendations for professors        |
| Reports          | Download attendance reports (CSV/PDF/Print)                    |
| Account Security | Strong passwords, Captcha, OTP, optional MFA, admin reset, lockout |

> **Names & promotion**: students use First/Middle/Last names with a Section
> field (from CSV import); admins bulk-promote year + section each academic
> year.

## 7. Technology Stack

| Component | Technology                                |
| --------- | ----------------------------------------- |
| Backend   | Python (FastAPI)                          |
| Frontend | JavaScript (SvelteKit) |
| Database  | PostgreSQL                                |
| Platform  | Progressive Web App (works on any device) |

## 8. CS Concepts Used

- **Caching & Indexing** — fast student lookup when scanning QR
- **Offline-First Architecture** — local storage + auto-sync
- **HMAC Hashing** — secure session codes
- **Geolocation Algorithms** — GPS classroom validation
- **Liveness Protocol** — challenge-response anti-spoofing with offline deferred validation
- **Data Analytics** — descriptive, diagnostic, predictive, and prescriptive reporting
- **Relational Database Design** — normalized tables

## 9. Expected Outcome

A fully functional attendance system that:

- Speeds up attendance to under 1 second per student
- Prevents cheating through session codes + GPS + QR liveness + face liveness
- Blocks photo, screen-recorder, video-replay, and distortion attacks
- Works with or without internet (liveness evidence re-validated after sync)
- Provides at-risk analytics and recommendations for professors
- Works on any phone with a camera (no app installation needed)

## 10. Team Members

| Name   | Role   |
| ------ | ------ |
| [Name] | [Role] |
| [Name] | [Role] |
| [Name] | [Role] |

---

_Submitted for Software Engineering 1_
