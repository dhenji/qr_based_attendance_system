# Test Data Specification — QR Attendance System

> **Purpose:** Test data for development, integration tests, and risk-model demos.
> Loadable via a single command: `python backend/test_seed_data.py`.
>
> **Prerequisites:** Programs and year levels must exist before running the seed.
> Create them via the admin API (`POST /admin/programs` + `POST /admin/programs/{pid}/years`).
>
> **Design principles:**
>
> - ~40 students across cohorts sharing one GE course template (proves D6).
> - Professors including one effective-dated handover mid-semester (proves D8).
> - 6 weeks of historical attendance for risk-model demo (proves D35).
> - All data matches the [target schema](../design/database-er.md) column-for-column.

---

## Table of Contents

1. [Programs & Year Levels](#1-programs--year-levels)
2. [Courses](#2-courses)
3. [Professors & Assignments](#3-professors--assignments)
4. [Students](#4-students)
5. [Enrollments](#5-enrollments)
6. [Sessions & Attendance (6-Week History)](#6-sessions--attendance-6-week-history)
7. [Excuse Requests](#7-excuse-requests)
8. [Face Enrollment Status](#8-face-enrollment-status)
9. [Sync Queue (Offline Scans)](#9-sync-queue-offline-scans)
10. [Risk Scores (Pre-computed)](#10-risk-scores-pre-computed)
11. [Backup Log](#11-backup-log)
12. [Seed Command](#12-seed-command)

---

## 1. Programs & Year Levels (Prerequisite)

> **These are NOT seeded by `test_seed_data.py`.** Create them via the admin API before running the seed.

### Program: BSCS

| code | name                                    | total_years | is_active |
| ---- | --------------------------------------- | ----------- | --------- |
| BSCS | Bachelor of Science in Computer Science | 4           | true      |

**Year Levels:**

| year | label    | term_structure (JSONB)                                                                                                                 |
| ---- | -------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| 1    | 1st Year | `{"terms":[{"code":"1st_sem","label":"1st Semester","weeks":16},{"code":"2nd_sem","label":"2nd Semester","weeks":16}]}`                                      |
| 2    | 2nd Year | `{"terms":[{"code":"1st_sem","label":"1st Semester","weeks":16},{"code":"2nd_sem","label":"2nd Semester","weeks":16}]}`                                      |
| 3    | 3rd Year | `{"terms":[{"code":"1st_sem","label":"1st Semester","weeks":16},{"code":"2nd_sem","label":"2nd Semester","weeks":16},{"code":"midyear","label":"Midyear","weeks":16}]}` |
| 4    | 4th Year | `{"terms":[{"code":"1st_sem","label":"1st Semester","weeks":16},{"code":"2nd_sem","label":"2nd Semester","weeks":16}]}`                                      |

### Program: BSIT

| code | name                                          | total_years | is_active |
| ---- | --------------------------------------------- | ----------- | --------- |
| BSIT | Bachelor of Science in Information Technology | 4           | true      |

**Year Levels:**

| year | label    | term_structure (JSONB)                                                                                                               |
| ---- | -------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| 1    | 1st Year | `{"terms":[{"code":"1st_sem","label":"1st Semester","weeks":16},{"code":"2nd_sem","label":"2nd Semester","weeks":16},{"code":"summer","label":"Summer","weeks":16}]}` |
| 2    | 2nd Year | `{"terms":[{"code":"1st_sem","label":"1st Semester","weeks":16},{"code":"2nd_sem","label":"2nd Semester","weeks":16},{"code":"summer","label":"Summer","weeks":16}]}` |
| 3    | 3rd Year | `{"terms":[{"code":"1st_sem","label":"1st Semester","weeks":16},{"code":"2nd_sem","label":"2nd Semester","weeks":16}]}`                                    |
| 4    | 4th Year | `{"terms":[{"code":"1st_sem","label":"1st Semester","weeks":16},{"code":"2nd_sem","label":"2nd Semester","weeks":16}]}`                                    |

### Program: BSECE

| code  | name                                           | total_years | is_active |
| ----- | ---------------------------------------------- | ----------- | --------- |
| BSECE | Bachelor of Science in Electronics Engineering | 5           | true      |

**Year Levels:**

| year | label    | term_structure (JSONB)                                                                                                                 |
| ---- | -------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| 1    | 1st Year | `{"terms":[{"code":"1st_sem","label":"1st Semester","weeks":16},{"code":"2nd_sem","label":"2nd Semester","weeks":16}]}`                                      |
| 2    | 2nd Year | `{"terms":[{"code":"1st_sem","label":"1st Semester","weeks":16},{"code":"2nd_sem","label":"2nd Semester","weeks":16}]}`                                      |
| 3    | 3rd Year | `{"terms":[{"code":"1st_sem","label":"1st Semester","weeks":16},{"code":"2nd_sem","label":"2nd Semester","weeks":16},{"code":"midyear","label":"Midyear","weeks":16}]}` |
| 4    | 4th Year | `{"terms":[{"code":"1st_sem","label":"1st Semester","weeks":16},{"code":"2nd_sem","label":"2nd Semester","weeks":16}]}`                                      |
| 5    | 5th Year | `{"terms":[{"code":"1st_sem","label":"1st Semester","weeks":16},{"code":"2nd_sem","label":"2nd Semester","weeks":16}]}`                                      |

---

## 2. Courses

### Shared GE Course (D6 — taken by BSCS Y1, BSIT Y1, BSECE Y1)

**Course template:**

| course_code | course_name            | units | session_duration_hours | is_active |
| ----------- | ---------------------- | ----- | ---------------------- | --------- |
| GE101       | Understanding the Self | 3     | 1.5                    | true      |

**Course offerings (one per program/year/semester):**

| offering | course_code | program | year | semester  | academic_year | sessions_per_week | weeks (from term) | schedule_days | start | end   | classroom_name | classroom_lat | classroom_lng | present_window | late_window |
| -------- | ----------- | ------- | ---- | --------- | ------------- | ----------------- | -------------- | ------------- | ----- | ----- | -------------- | ------------- | ------------- | -------------- | ----------- |
| GE101-BSCS-Y1-1st | GE101 | BSCS    | 1    | 1st_sem   | 2026-2027     | 2                 | 16             | MW            | 07:00 | 08:30 | Room 301       | 14.5995       | 120.9842      | 5              | 10          |
| GE101-BSIT-Y1-1st | GE101 | BSIT    | 1    | 1st_sem   | 2026-2027     | 2                 | 16             | MW            | 07:00 | 08:30 | Room 301       | 14.5995       | 120.9842      | 5              | 10          |
| GE101-BSECE-Y1-1st | GE101 | BSECE   | 1    | 1st_sem   | 2026-2027     | 2                 | 16             | MW            | 07:00 | 08:30 | Room 301       | 14.5995       | 120.9842      | 5              | 10          |

### Program-Specific Courses

**Course templates:**

| course_code | course_name            | units | session_duration_hours | is_active |
| ----------- | ---------------------- | ----- | ---------------------- | --------- |
| CS101       | Intro to Computing     | 3     | 1.5                    | true      |
| CS201       | Data Structures        | 4     | 2.0                    | true      |
| CS301       | Operating Systems      | 3     | 1.5                    | true      |
| IT101       | Web Dev Foundations    | 3     | 1.5                    | true      |
| IT201       | Network Administration | 3     | 1.5                    | true      |
| ECE101      | Circuit Theory 1       | 4     | 2.0                    | true      |

**Offerings (one per program/year/semester):**

| offering         | course_code | program | year | semester | academic_year | sessions_per_week | schedule_days | start | end   |
| ---------------- | ----------- | ------- | ---- | -------- | ------------- | ----------------- | ------------- | ----- | ----- |
| CS101-BSCS-Y1-1st  | CS101  | BSCS    | 1    | 1st_sem  | 2026-2027     | 3                 | MWF           | 09:00 | 10:30 |
| CS201-BSCS-Y2-1st  | CS201  | BSCS    | 2    | 1st_sem  | 2026-2027     | 3                 | MWF           | 10:30 | 12:30 |
| CS301-BSCS-Y3-1st  | CS301  | BSCS    | 3    | 1st_sem  | 2026-2027     | 2                 | TF            | 13:00 | 14:30 |
| IT101-BSIT-Y1-1st  | IT101  | BSIT    | 1    | 1st_sem  | 2026-2027     | 3                 | MWF           | 13:00 | 14:30 |
| IT201-BSIT-Y2-1st  | IT201  | BSIT    | 2    | 1st_sem  | 2026-2027     | 2                 | MW            | 10:00 | 11:30 |
| ECE101-BSECE-Y1-1st | ECE101 | BSECE  | 1    | 1st_sem  | 2026-2027     | 3                 | MWF           | 08:00 | 10:00 |

---

## 3. Professors & Assignments

### Professors

| user_id | email                 | first_name | last_name | department              | is_active |
| ------- | --------------------- | ---------- | --------- | ----------------------- | --------- |
| prof1   | prof.delacruz@uni.edu | Maria      | Dela Cruz | Computer Science        | true      |
| prof2   | prof.santos@uni.edu   | Juan       | Santos    | Computer Science        | true      |
| prof3   | prof.reyes@uni.edu    | Ana        | Reyes     | Information Technology  | true      |
| prof4   | prof.garcia@uni.edu   | Luis       | Garcia    | Electronics Engineering | true      |

### Course Assignments

| professor         | offering               | is_primary | effective_from | effective_to | assigned_by |
| ----------------- | ---------------------- | ---------- | -------------- | ------------ | ----------- |
| prof1 (Dela Cruz) | GE101-BSCS-Y1-1st      | true       | 2026-06-01     | NULL         | admin1      |
| prof1 (Dela Cruz) | CS101-BSCS-Y1-1st      | true       | 2026-06-01     | NULL         | admin1      |
| prof1 (Dela Cruz) | CS201-BSCS-Y2-1st      | true       | 2026-06-01     | NULL         | admin1      |
| prof2 (Santos)    | CS301-BSCS-Y3-1st      | true       | 2026-06-01     | NULL         | admin1      |
| prof3 (Reyes)     | IT101-BSIT-Y1-1st      | true       | 2026-06-01     | NULL         | admin1      |
| prof3 (Reyes)     | IT201-BSIT-Y2-1st      | true       | 2026-06-01     | NULL         | admin1      |
| prof4 (Garcia)    | ECE101-BSECE-Y1-1st    | true       | 2026-06-01     | NULL         | admin1      |

**Handover Scenario (D8):** prof2 (Santos) takes over CS301 from prof1 (Dela Cruz) mid-semester. Handover date falls between weeks 3 and 4 of the session window so existing sessions remain attributed to prof1.

| professor         | offering               | is_primary | effective_from | effective_to | assigned_by |
| ----------------- | ---------------------- | ---------- | -------------- | ------------ | ----------- |
| prof1 (Dela Cruz) | CS301-BSCS-Y3-1st      | true       | 2026-06-01     | 2026-06-20   | admin1      |
| prof2 (Santos)    | CS301-BSCS-Y3-1st      | true       | 2026-06-22     | NULL         | admin1      |

**Assistant assignment (D9):**

| professor      | offering               | is_primary | effective_from | effective_to |
| -------------- | ---------------------- | ---------- | -------------- | ------------ |
| prof2 (Santos) | GE101-BSCS-Y1-1st      | false      | 2026-06-01     | NULL         |

---

## 4. Students

Total: 42 students across 3 cohorts, sharing GE101.

### BSCS Year 1 (14 students, sections A & B)

| student_id | first_name | last_name | section | year_level |
| ---------- | ---------- | --------- | ------- | ---------- |
| 24-0001    | Jose       | Rizal     | A       | 1          |
| 24-0002    | Andres     | Bonifacio | A       | 1          |
| 24-0003    | Emilio     | Aguinaldo | A       | 1          |
| 24-0004    | Apolinario | Mabini    | A       | 1          |
| 24-0005    | Antonio    | Luna      | A       | 1          |
| 24-0006    | Marcelo    | del Pilar | A       | 1          |
| 24-0007    | Gregorio   | del Pilar | A       | 1          |
| 24-0008    | Sultan     | Kudarat   | B       | 1          |
| 24-0009    | Tandang    | Sora      | B       | 1          |
| 24-0010    | Gabriela   | Silang    | B       | 1          |
| 24-0011    | Diego      | Silang    | B       | 1          |
| 24-0012    | Francisco  | Dagohoy   | B       | 1          |
| 24-0013    | Macario    | Sakay     | B       | 1          |
| 24-0014    | Vicente    | Sotto     | B       | 1          |

### BSIT Year 1 (14 students, sections A & B)

| student_id | first_name | last_name  | section | year_level |
| ---------- | ---------- | ---------- | ------- | ---------- |
| 24-1001    | Manny      | Pacquiao   | A       | 1          |
| 24-1002    | Nonito     | Donaire    | A       | 1          |
| 24-1003    | Carlos     | Yulo       | A       | 1          |
| 24-1004    | Hidilyn    | Diaz       | A       | 1          |
| 24-1005    | Nesthy     | Petecio    | A       | 1          |
| 24-1006    | Eumir      | Marcial    | A       | 1          |
| 24-1007    | Tokyo      | Olympics   | A       | 1          |
| 24-1008    | Niels      | Bohr       | B       | 1          |
| 24-1009    | Alan       | Turing     | B       | 1          |
| 24-1010    | Grace      | Hopper     | B       | 1          |
| 24-1011    | Ada        | Lovelace   | B       | 1          |
| 24-1012    | Linus      | Torvalds   | B       | 1          |
| 24-1013    | Dennis     | Ritchie    | B       | 1          |
| 24-1014    | Bjarne     | Stroustrup | B       | 1          |

### BSECE Year 1 (14 students, section A only)

| student_id | first_name | last_name   | section | year_level |
| ---------- | ---------- | ----------- | ------- | ---------- |
| 24-2001    | Thomas     | Edison      | A       | 1          |
| 24-2002    | Nikola     | Tesla       | A       | 1          |
| 24-2003    | Alexander  | Graham Bell | A       | 1          |
| 24-2004    | Guglielmo  | Marconi     | A       | 1          |
| 24-2005    | Robert     | Noyce       | A       | 1          |
| 24-2006    | Jack       | Kilby       | A       | 1          |
| 24-2007    | Lee de     | Forest      | A       | 1          |
| 24-2008    | Philo      | Farnsworth  | A       | 1          |
| 24-2009    | John       | Bardeen     | A       | 1          |
| 24-2010    | William    | Shockley    | A       | 1          |
| 24-2011    | Walter     | Brattain    | A       | 1          |
| 24-2012    | Claude     | Shannon     | A       | 1          |
| 24-2013    | Kurt       | Godel       | A       | 1          |
| 24-2014    | Alan       | Kay         | A       | 1          |

---

## 5. Enrollments

All 42 students are enrolled in GE101 (proving D6: shared course template across programs). Each student enrolls in their program's offering. Each student also enrolled in one program-specific offering.

| enrollment_pattern | offering               | academic_year | semester |
| ------------------ | ---------------------- | ------------- | -------- |
| BSCS Y1 (14)       | GE101-BSCS-Y1-1st      | 2026-2027     | 1st_sem  |
| BSIT Y1 (14)       | GE101-BSIT-Y1-1st      | 2026-2027     | 1st_sem  |
| BSECE Y1 (14)      | GE101-BSECE-Y1-1st     | 2026-2027     | 1st_sem  |
| BSCS Y1 (14)       | CS101-BSCS-Y1-1st      | 2026-2027     | 1st_sem  |
| BSIT Y1 (14)       | IT101-BSIT-Y1-1st      | 2026-2027     | 1st_sem  |
| BSECE Y1 (14)      | ECE101-BSECE-Y1-1st    | 2026-2027     | 1st_sem  |

> **UNIQUE constraint:** `(student_id, offering_id, academic_year)` — a student may not be enrolled in the same offering twice per academic year.

---

## 6. Sessions & Attendance (6-Week History)

### GE101-BSCS-Y1-1st Session Pattern (2 sessions/week, MW, 16 weeks = 32 sessions total)

The seed creates 12 sessions across 6 weeks (Mon + Wed each week) for GE101,
with varying attendance distributions to exercise the risk model.

**Week dates (semester starts 2026-06-01):**

| Week | Monday     | Wednesday  |
| ---- | ---------- | ---------- |
| 1    | 2026-06-01 | 2026-06-03 |
| 2    | 2026-06-08 | 2026-06-10 |
| 3    | 2026-06-15 | 2026-06-17 |
| 4    | 2026-06-22 | 2026-06-24 |
| 5    | 2026-06-29 | 2026-07-01 |
| 6    | 2026-07-06 | 2026-07-08 |

### Session Metadata (applies to all 12 sessions)

| Field                   | Value                                                                                                             |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------- |
| offering_id             | GE101-BSCS-Y1-1st                                                                                                 |
| professor_id            | prof1 (Dela Cruz) for weeks 1–3; prof2 (Santos) for weeks 4–6 (assistant assignment D9; either may open sessions) |
| duration_minutes        | 90                                                                                                                |
| present_window_minutes  | 5                                                                                                                 |
| late_window_minutes     | 10                                                                                                                |
| classroom_radius_meters | 30                                                                                                                |
| scheduled_start_time    | 07:00                                                                                                             |
| scheduled_end_time      | 08:30                                                                                                             |

### Attendance Distribution Per Session

Each session generates attendance records for all 42 students with the following
distribution patterns to create realistic risk scenarios:

**Weeks 1–2 (normal attendance):**

| Status  | Count | Students                                      |
| ------- | ----- | --------------------------------------------- |
| present | 35    | Most students attend                          |
| late    | 3     | Random subset                                 |
| absent  | 4     | 4 specific students (see Risk Profiles below) |

**Weeks 3–4 (declining attendance for at-risk students):**

| Status  | Count | Notes                             |
| ------- | ----- | --------------------------------- |
| present | 33    |                                   |
| late    | 4     |                                   |
| absent  | 5     | Risk students increasing absences |

**Weeks 5–6 (risk patterns emerge):**

| Status  | Count | Notes                                      |
| ------- | ----- | ------------------------------------------ |
| present | 32    |                                            |
| late    | 3     |                                            |
| absent  | 7     | High-risk students now consistently absent |

### Student Risk Profiles (designed to exercise D35 thresholds)

| student_id | profile                                     | Expected Risk Level | Rationale                                                       |
| ---------- | ------------------------------------------- | ------------------- | --------------------------------------------------------------- |
| 24-0001    | Perfect attendance                          | low                 | 0% absence                                                      |
| 24-0002    | Perfect attendance                          | low                 | 0% absence                                                      |
| 24-0003    | 1 absence in 12 sessions                    | low                 | absence_rate = 0.08                                             |
| 24-0004    | 2 absences in 12 sessions                   | medium              | absence_rate = 0.17 (>0.15 = medium) no streak                 |
| 24-0005    | 4 absences in 12 sessions                   | high                | absence_rate = 0.33 (>0.30 = high)                              |
| 24-0006    | 5 absences in 12 sessions                   | high                | absence_rate = 0.42; streak=3                                   |
| 24-0007    | 3 consecutive absences (weeks 4–6)          | high                | streak >= 3                                                     |
| 24-0008    | 2 absences, 3 pending syncs                 | medium              | sync_lag >= 5 (combined with absences)                          |
| 24-0009    | Steady decline (1→1→2→2→3→4 absent pattern) | high                | trend_slope < -0.05/week                                        |
| 24-0010    | All 12 sessions present                     | low                 | perfect attendance                                              |
| 24-0011    | All 12 sessions present                     | low                 | perfect attendance                                              |
| 24-0012    | 3 absences, no streak                       | medium              | absence_rate = 0.25                                             |
| 24-0013    | 1 absence, 2 late                           | low                 | absence_rate = 0.08                                             |
| 24-0014    | 2 absences, 1 excused                       | medium              | effective absent = 2/12 = 0.17 (>0.15 = medium)                |

### Additional Sessions for CS101-BSCS-Y1-1st (BSCS-only, to test program-filtered analytics)

6 sessions (3 weeks, MWF pattern) for CS101 offering with prof1:

| Week | Dates              | present | late | absent |
| ---- | ------------------ | ------- | ---- | ------ |
| 1    | 2026-06-02, 04, 05 | 12      | 1    | 1      |
| 2    | 2026-06-09, 11, 12 | 11      | 2    | 1      |
| 3    | 2026-06-16, 18, 19 | 10      | 1    | 3      |

### Additional Sessions for IT101-BSIT-Y1-1st (BSIT-only)

6 sessions for IT101 offering with prof3:

| Week | Dates              | present | late | absent |
| ---- | ------------------ | ------- | ---- | ------ |
| 1    | 2026-06-02, 04, 05 | 13      | 0    | 1      |
| 2    | 2026-06-09, 11, 12 | 12      | 1    | 1      |
| 3    | 2026-06-16, 18, 19 | 11      | 2    | 1      |

### Attendance Record Field Values

Each attendance record includes:

| Field             | Value                                                                |
| ----------------- | -------------------------------------------------------------------- |
| gps_lat           | 14.5995 (within radius)                                              |
| gps_lng           | 120.9842 (within radius)                                             |
| sync_status       | synced                                                               |
| scanned_via       | qr_camera                                                            |
| face_match_score  | 0.82 (present/late students)                                         |
| liveness_evidence | `{"blink_detected":true,"head_turn_left":true,"head_turn_right":true,"ear_samples":[0.18,0.31,0.29,0.33],"pnp_evidence":{"yaw":12.5}}` |

---

## 7. Excuse Requests

Seed 3 excuse requests to exercise all D21 paths:

| initiated_by | initiated_via      | student | session    | reason                                   | status   | has_attachment         |
| ------------ | ------------------ | ------- | ---------- | ---------------------------------------- | -------- | ---------------------- |
| professor    | quick              | 24-0006 | Week 3 Mon | "Family emergency reported"              | approved | no                     |
| professor    | prof_with_evidence | 24-0007 | Week 4 Mon | "Hospitalized — attached medical cert"   | approved | yes (medical_cert.pdf) |
| student      | request            | 24-0009 | Week 5 Mon | "Sick leave — attached BRGY certificate" | pending  | yes (brgy_cert.pdf)    |

**Attendance record side effects:**

- 24-0006: original_status=absent, final_status=excused, excuse_type=quick
- 24-0007: original_status=absent, final_status=excused, excuse_type=prof_with_evidence
- 24-0009: stays absent until request approved; excuse_request_id linked

---

## 8. Face Enrollment Status

| Status         | Students                                    | Count |
| -------------- | ------------------------------------------- | ----- |
| Enrolled (v=1) | 24-0001 through 24-0014 (all BSCS Y1)       | 14    |
| Enrolled (v=1) | 24-1001 through 24-1007 (BSIT Y1 section A) | 7     |
| Not enrolled   | 24-1008 through 24-1014 (BSIT Y1 section B) | 7     |
| Not enrolled   | 24-2001 through 24-2014 (all BSECE Y1)      | 14    |

**Rationale:** Mixed enrollment status tests:

- D28: admin-enrolled faces (real 512-d embedding generated server-side)
- D29: pull-on-login version check
- D30: offline verification with cached embedding — **design only, not implemented**
- Edge case: students without face enrollment can still scan; the scan never
  reads `face_embedding` and does not require enrollment

---

## 9. Sync Queue (Offline Scans)

Seed 3 queued offline scan records for student 24-0008 (profile: "2 absences, 3 pending syncs") to exercise D16 offline sync validation and the pending-count banner (D15/OFF-7).

| student_id | session_id       | scanned_at             | gps_lat | gps_lng  | sync_status | face_match_score | liveness_evidence                                   |
| ---------- | ---------------- | ---------------------- | ------- | -------- | ----------- | ---------------- | --------------------------------------------------- |
| 24-0008    | GE101 Week 3 Mon | 2026-06-15 07:12:00+08 | 14.5995 | 120.9842 | pending     | 0.81             | `{"blink_detected":true,"head_turn_left":true,"head_turn_right":true}` |
| 24-0008    | GE101 Week 4 Mon | 2026-06-22 07:08:00+08 | 14.5995 | 120.9842 | pending     | 0.83             | `{"blink_detected":true,"head_turn_left":true,"head_turn_right":true}` |
| 24-0008    | GE101 Week 5 Mon | 2026-06-29 07:15:00+08 | 14.5995 | 120.9842 | pending     | 0.79             | `{"blink_detected":true,"head_turn_left":true,"head_turn_right":true}` |

**Notes:**

- All three scans occurred within active session windows (scanned_at within duration) — on sync they should be accepted as present or late.
- On sync, server validates `scanned_at` against each session's window per D16.
- These entries exercise OFF-1, OFF-2, OFF-7 test cases.

---

## 10. Risk Scores (Pre-computed)

Pre-seeded risk scores for the 12-session GE101 window, enabling immediate
analytics/at-risk tab display without waiting for nightly batch.

| student_id | risk_probability | risk_level | computed_at      |
| ---------- | ---------------- | ---------- | ---------------- |
| 24-0001    | 0.02             | low        | 2026-07-09 02:00 |
| 24-0002    | 0.03             | low        | 2026-07-09 02:00 |
| 24-0005    | 0.45             | high       | 2026-07-09 02:00 |
| 24-0006    | 0.72             | high       | 2026-07-09 02:00 |
| 24-0007    | 0.55             | high       | 2026-07-09 02:00 |
| 24-0008    | 0.35             | medium     | 2026-07-09 02:00 |
| 24-0009    | 0.68             | high       | 2026-07-09 02:00 |
| 24-0012    | 0.28             | medium     | 2026-07-09 02:00 |

Students not listed above default to `risk_level=low` unless the nightly batch computes
higher (see §9 Student Risk Profiles — e.g. 24-0004/24-0014 evaluate to medium when run).

---

## 11. Backup Log

Seed 1 backup log entry for display in admin settings:

| filename                          | kind | size_bytes | sha256                                                           | storage_backend | encryption_key_version | status  |
| --------------------------------- | ---- | ---------- | ---------------------------------------------------------------- | --------------- | ---------------------- | ------- |
| backup_20260708_020000.sql.gz.enc | full | 5242880 | baf1770718fda5f6d1cee88285ec19d4a9273e00080f0bdd0f6b147abf7b4b4a | local | 1 | completed |

---

## 12. Seed Command

> **Prerequisite:** a migrated database (`alembic upgrade head`). Programs
> (BSCS, BSIT, BSECE) and their year levels are **created by the seed when
> missing**, so a fresh database needs nothing else seeded first.

```bash
# From project root — default seed (42 students, matching this spec):
cd backend && python test_seed_data.py

# Scaled seed for performance benchmarks (§3 of performance-benchmarks.md):
cd backend && python test_seed_data.py --scale small    # 50 students (dev)
cd backend && python test_seed_data.py --scale medium   # 500 students (pilot)
cd backend && python test_seed_data.py --scale large    # 10,000 students
cd backend && python test_seed_data.py --scale xl       # 50,000 students (multi-year)

# Re-runnable: every write is looked up by its unique column first, so a
# second run inserts nothing. --reset deletes previously seeded rows first.
cd backend && python test_seed_data.py --scale small --reset

# Importable entry point (same module, what the load harness and tests use):
cd backend && PYTHONPATH=src .venv/bin/python -m tests.seed_data --scale small
```

The seed is a script, not a migration: `src/tests/seed_data.py` holds the
implementation and `backend/test_seed_data.py` is a thin entry point kept
because the runbooks cite that path. There is no Alembic data-migration
variant.

**Load fixtures** (`--load-fixtures N`) provisions the concurrent-scan
harness (`backend/locustfile.py`): `SEED-LOAD-###` sessions anchored at seed
time (+3h expiry, Room 301 coordinates) plus 30 `loadtestNN@load.uni.edu`
accounts cross-enrolled in `GE101-BSCS-Y1-1st`. Two behaviors matter when
re-running it:

- **Session codes are skipped if they already exist**, so a repeat run cannot
  refresh the present/late windows or un-consume `(student, session)` pairs.
  Clear the load data first: `DELETE FROM attendance_records WHERE session_id
  IN (SELECT id FROM sessions WHERE session_code LIKE 'SEED-LOAD-%'); DELETE
  FROM sessions WHERE session_code LIKE 'SEED-LOAD-%';`
- **Load-account emails must use a deliverable domain.** The login contract
  validates with `EmailStr`, which rejects reserved TLDs such as `.test`
  (HTTP 422 on every login).

```bash
cd backend && python test_seed_data.py --scale small --load-fixtures 150
```

**Verification after seed:**

```sql
-- Programs (seeded when missing — ≥3 on any database this seed has run)
SELECT count(*) FROM programs;  -- Expected: ≥3

-- Year levels (seeded when missing; 4+4+5 across the three programs)
SELECT count(*) FROM year_levels;  -- Expected: ≥13

-- Courses count (templates only, seeded)
SELECT count(*) FROM courses;  -- Expected: 7

-- Course offerings count
SELECT count(*) FROM course_offerings;  -- Expected: 9 (3 for GE101 + 6 program-specific)

-- Enrollments in GE101 (shared across programs via offerings)
SELECT count(*) FROM enrollments e
JOIN course_offerings co ON e.offering_id = co.id
JOIN courses c ON co.course_id = c.id
WHERE c.course_code = 'GE101';  -- Expected: 42 (14 per program × 3 programs)

-- Sessions created (via offering)
SELECT count(*) FROM sessions WHERE offering_id = (
  SELECT id FROM course_offerings WHERE course_code = 'GE101' AND program_id = (
    SELECT id FROM programs WHERE code = 'BSCS'
  ) AND semester = '1st_sem' AND academic_year = '2026-2027'
);  -- Expected: 12

-- Attendance records
SELECT count(*) FROM attendance_records;  -- Expected: ~504 (42 students × 12 sessions)

-- Professor handover (via offering)
SELECT professor_id, effective_from, effective_to
FROM course_professors
WHERE offering_id = (
  SELECT id FROM course_offerings WHERE course_code = 'CS301' AND program_id = (
    SELECT id FROM programs WHERE code = 'BSCS'
  ) AND semester = '1st_sem' AND academic_year = '2026-2027'
)
ORDER BY effective_from;  -- Expected: prof1 (2026-06-01 to 2026-06-20), prof2 (2026-06-22 to NULL)
```
