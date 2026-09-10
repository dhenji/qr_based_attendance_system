# Test Plan — QR Attendance System

> **Scope:** Every decision D1–D43 from the DOCS_REFACTOR_PLAN §2 must be covered by
> at least one test case. Cases are organized by portal, then by feature area.
> Each case lists: portal, feature, decision IDs, case name, preconditions,
> steps, expected result, and edge-case variant where applicable.

---

## Table of Contents

1. [Portal × Feature Matrix](#1-portal--feature-matrix)
2. [Admin Portal Tests](#2-admin-portal-tests)
3. [Professor Portal Tests](#3-professor-portal-tests)
4. [Student Portal Tests](#4-student-portal-tests)
5. [Shared / Auth Tests](#5-shared--auth-tests)
6. [Security / Threat-Model Tests](#6-security--threat-model-tests)
7. [Offline & Sync Tests](#7-offline--sync-tests)
8. [Decision Coverage Matrix](#8-decision-coverage-matrix)

---

## 1. Portal × Feature Matrix

| Portal    | Feature Area                  | Happy-Path Cases | Edge-Case Cases |
| --------- | ----------------------------- | ---------------- | --------------- |
| Admin     | Program Management            | 4                | 3               |
| Admin     | Year-Level & Term Structure   | 3                | 2               |
| Admin     | Course Management             | 7                | 3               |
| Admin     | Professor Assignment          | 3                | 2               |
| Admin     | Student Enrollment (bulk CSV) | 2                | 2               |
| Admin     | Face Enrollment               | 3                | 2               |
| Admin     | Analytics & Reports           | 4                | 3               |
| Admin     | System Settings & Backup      | 3                | 2               |
| Admin     | Audit Logs                    | 1                | 1               |
| Professor | Session Creation (locked)     | 3                | 4               |
| Professor | Session Creation (selector)   | 2                | 2               |
| Professor | Active Session / Live View    | 3                | 3               |
| Professor | Attendance List & Filters     | 2                | 2               |
| Professor | Excuse Actions                | 4                | 3               |
| Professor | Session History               | 1                | 1               |
| Professor | Reports                       | 3                | 2               |
| Professor | Profile / Settings            | 2                | 1               |
| Student   | Scan Flow (5-step)            | 3                | 4               |
| Student   | Attendance History            | 2                | 1               |
| Student   | Schedule                      | 1                | 1               |
| Student   | Profile / Settings            | 2                | 1               |
| Student   | Excuse Request                | 2                | 2               |
| Shared    | Auth / OTP / MFA              | 3                | 2               |
| Security  | Anti-Spoofing                 | 5                | 5               |
| Offline   | Sync & Queue                  | 3                | 3               |
| **Total** |                               | **71**           | **58**          |

---

## 2. Admin Portal Tests

### 2.1 Program Management

| #      | Decision IDs | Case                                      | Preconditions                               | Steps                                                                            | Expected Result                                                                                        |
| ------ | ------------ | ----------------------------------------- | ------------------------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| A-PM-1 | D1, D6       | Create program with year levels           | Admin logged in                             | Navigate to Programs; click [+Add Program]; fill code, name, total_years=4; save | Program created; year-level tabs 1–4 auto-generated; appears in program list                           |
| A-PM-2 | D1           | Archive a program                         | Program exists, no active enrollments       | Click archive on program row                                                     | Program `is_active` set false; hidden from default list; restore option available                      |
| A-PM-3 | D6           | View shared courses across programs       | GE course enrolled by BSCS Y1 and BSIT Y1   | Open course detail for GE course                                                 | Both cohort badges shown (BSCS·Y1, BSIT·Y1); filter by program shows only relevant cohort              |
| A-PM-4 | D1, D6       | Reject duplicate program code             | Program "BSCS" already exists               | Attempt create with code "BSCS"                                                  | 409 Conflict; error message "Program code already exists"                                              |
| A-PM-5 | D1           | Delete program with active FKs            | Program has courses with active enrollments | Attempt archive                                                                  | 409 Conflict; message lists dependent resources                                                        |
| A-PM-6 | D38          | No "Year + Section Promotion" in settings | Admin opens System Settings                 | Inspect settings page                                                            | No promotion block present; "Academic Structure Updates" block with [Edit Programs ➜] deep-link exists |

### 2.2 Year-Level & Term Structure

| #      | Decision IDs | Case                            | Preconditions                                                                                                                                                             | Steps                                             | Expected Result                                                  |
| ------ | ------------ | ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------- | ---------------------------------------------------------------- |
| A-YL-1 | D3           | View term structure for BSCS Y3 | BSCS Y3 exists with term_structure `{"terms":[{"code":"1st_sem","label":"1st Semester"},{"code":"2nd_sem","label":"2nd Semester"},{"code":"midyear","label":"Midyear"}]}` | Open BSCS → Year 3 tab                            | Three term chips displayed: 1st Semester, 2nd Semester, Midyear  |
| A-YL-2 | D3           | Edit term structure             | BSCS Y1 with 2 terms                                                                                                                                                      | Click edit modal on term chips; add "Summer" term | Term structure JSONB updated; validation rejects duplicate codes |
| A-YL-3 | D5           | Add year level to program       | BSCS has 3 years; total_years=4                                                                                                                                           | Click [+Add Year] on program detail               | Year 4 tab created; term_structure empty until admin edits       |

### 2.3 Course Management

| #      | Decision IDs | Case                                      | Preconditions                            | Steps                                                                                                                            | Expected Result                                                      |
| ------ | ------------ | ----------------------------------------- | ---------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| A-CM-1a | D4           | Create course template                    | —                                         | POST /admin/courses with course_code, course_name, units=3, session_duration_hours=1.5 | Course template created; no schedule/classroom/window/program fields accepted |
| A-CM-1b | D4           | Create course offering                    | Course template GE101 exists              | POST /admin/offerings with course_id, program_id=BSCS, year_level_id=Y1, semester=1st_sem, academic_year=2026-2027, sessions_per_week=2, schedule_days=MW, schedule_start_time=07:00, schedule_end_time=08:30, classroom_name="Room 301", classroom_lat/lng, default_present_window_minutes=5, default_late_window_minutes=10 | Offering created; UNIQUE(course_id, program_id, semester, academic_year) enforced |
| A-CM-2 | D4           | Reject invalid window constraint (offering) | Offering: present=10, late=20, duration=25 | Submit offering                                                                                                              | 400 Bad Request: present + late exceeds duration                     |
| A-CM-3 | D17          | Session-level classroom override          | Offering has classroom_name="Rm 101"      | Create session with classroom_name override="Rm 201"                                                                             | Session uses Rm 201 for geofence; offering default unchanged           |
| A-CM-4 | D17          | Geofence falls back to offering coords   | Session classroom_* fields all NULL      | Verify session geofence                                                                                                          | Uses offering classroom_lat/lng and classroom_radius_meters            |
| A-CM-5 | D14          | Offering default windows applied to session | Offering: present=5, late=10             | Professor creates session without overriding windows                                                                             | Session inherits present_window_minutes=5, late_window_minutes=10    |
| A-CM-6 | D2           | Section stored on students only           | Student record                           | Inspect enrollment record                                                                                                        | No `section` column on enrollments; section exists on students table |
| A-CM-7 | D4           | Reject duplicate offering                 | Offering for GE101+BSCS+1st_sem+2026-2027 exists | Attempt POST /admin/offerings with same (course_id, program_id, semester, academic_year) | 409 Conflict; UNIQUE constraint on (course_id, program_id, semester, academic_year) |
| A-CM-8 | D14          | Offering window defaults copy to session  | Offering: present=5, late=10             | Professor creates session from offering without overriding windows                                                               | Session created with present_window_minutes=5, late_window_minutes=10 copied from offering |
| A-CM-9 | D17          | Offering classroom/geofence used by session | Offering: classroom_name="Room 301", lat/lng set | Professor creates session without classroom override                                                                     | Session geofence uses offering's classroom_lat/lng and classroom_radius_meters |

### 2.4 Professor Assignment

| #      | Decision IDs | Case                            | Preconditions                                                      | Steps                                                                                   | Expected Result                                                                                  |
| ------ | ------------ | ------------------------------- | ------------------------------------------------------------------ | --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| A-PA-1 | D7           | Assign professor to offering              | Offering and professor exist              | POST /admin/offerings/{oid}/professors with professor_id, is_primary=true, effective_from | Assignment created; professor listed on offering detail |
| A-PA-2 | D8           | Mid-semester professor handover | Prof A assigned effective_from=2026-06-01, effective_to=NULL       | Set effective_to=2026-07-14 on Prof A; assign Prof B effective_from=2026-07-15          | Prof A shows end date; Prof B shows start; sessions before 2026-07-15 still attributed to Prof A |
| A-PA-3 | D9           | Assign assistant (secondary)    | Offering has primary professor                                              | Assign second professor with is_primary=false                                           | Both listed; either can open sessions for the offering                                             |
| A-PA-4 | D7           | Reject overlapping assignment   | Prof A already assigned for offering+semester with overlapping dates | Attempt assign Prof A with overlapping effective_from/to                                | 409 Conflict; overlapping range rejected at service layer                                        |

### 2.5 Student Enrollment (Bulk CSV)

| #      | Decision IDs | Case                           | Preconditions                                                | Steps                                      | Expected Result                                                                     |
| ------ | ------------ | ------------------------------ | ------------------------------------------------------------ | ------------------------------------------ | ----------------------------------------------------------------------------------- |
| A-BE-1 | D2, D5       | Bulk enroll students to offering | CSV with 20 students; offering belongs to BSCS Y1           | POST /admin/offerings/{oid}/enrollments/bulk | 20 enrollments created; each with semester validated against BSCS Y1 term_structure |
| A-BE-2 | D5           | Reject invalid semester        | CSV row has semester="summer" but BSCS Y1 has no summer term | Bulk enroll                                                              | Row rejected; error lists invalid semester for year level                           |
| A-BE-3 | D2           | Reject duplicate enrollment    | Student already enrolled in offering for same academic_year   | Bulk enroll same student again             | Duplicate skipped; no error (idempotent)                                            |

### 2.6 Face Enrollment

| #      | Decision IDs | Case                                    | Preconditions                       | Steps                                                                       | Expected Result                                                                                                                 |
| ------ | ------------ | --------------------------------------- | ----------------------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| A-FE-1 | D28, D43     | Enroll student face — 3 photos          | Student exists, no prior enrollment | POST /admin/face-enrollment/{student_id} with 3 images (front, left, right) | `face_embedding` BYTEA populated; `face_enrolled_at` set; `face_embedding_version` incremented; mean + per-angle vectors stored |
| A-FE-2 | D28          | Reject invalid photo (no face detected) | Same setup                          | Upload image with no face                                                   | 422 Unprocessable; "No face detected in image N"                                                                                |
| A-FE-3 | D28          | Reject photo quality too low            | Same setup                          | Upload blurry/dark image                                                    | 422 Unprocessable; quality gate failure message                                                                                 |
| A-FE-4 | D28          | Re-enrollment supersedes old vectors    | Student already enrolled (v=1)      | Upload new 3 photos                                                         | `face_embedding_version` bumps to 2; old vectors overwritten                                                                    |
| A-FE-5 | D28          | Revocation on student archive           | Student archived (is_active=false)  | Admin archives student                                                      | `face_embedding` cleared or flagged; pull-on-login returns empty                                                                |

### 2.7 Analytics & Reports

| #      | Decision IDs | Case                                | Preconditions                                                         | Steps                                                      | Expected Result                                            |
| ------ | ------------ | ----------------------------------- | --------------------------------------------------------------------- | ---------------------------------------------------------- | ---------------------------------------------------------- |
| A-AN-1 | D33          | Overview tab with cascading filters | Data exists for BSCS Y1 1st_sem                                       | Select Program=BSCS, Year=1, Term=1st_sem, Courses=[CS101] | KPI cards show totals + avg compliance + avg participation |
| A-AN-2 | D34          | Course comparison across cohorts    | GE101 taught by BSCS Y1 (85% compliance) and BSIT Y1 (78% compliance) | Course Comparison tab, select GE101                        | Bar chart shows two bars: BSCS·Y1=85%, BSIT·Y1=78%         |
| A-AN-3 | D35          | At-risk prediction — high threshold | Student has 35% absence rate                                          | At-Risk tab loads                                          | Student row shows risk_level=high; absence_rate=0.35       |
| A-AN-4 | D35          | Manual risk refresh                 | Admin clicks [Refresh Risk]                                           | POST /admin/analytics/refresh-risk                         | Batch job runs on-demand; scores updated                   |
| A-AN-5 | D36          | Compliance vs participation toggle  | Session with 8 present, 2 late, 1 excused, 9 absent (total=20)        | Toggle metric                                              | Compliance = 8/20 = 40%; Participation = (8+2+1)/20 = 55%  |
| A-AN-6 | D33          | Export with current filter set      | Filters applied                                                       | Click Export → CSV/PDF                                     | File contains only filtered rows                           |
| A-AN-7 | D33          | Date range filter                   | Data across weeks                                                     | Set date range to 2026-07-01 to 2026-07-31                 | Only July data shown                                       |

### 2.8 System Settings & Backup

| #      | Decision IDs | Case                                   | Preconditions                    | Steps                        | Expected Result                                                                                     |
| ------ | ------------ | -------------------------------------- | -------------------------------- | ---------------------------- | --------------------------------------------------------------------------------------------------- |
| A-BS-1 | D39          | Full database backup                   | No prior backups                 | Click [Backup Now]           | pg_dump custom format runs; encrypted AES-256-GCM; backup_log entry created with sha256, size_bytes |
| A-BS-2 | D39          | Backup retention prune                 | >30 daily backups exist          | Nightly prune job runs       | Oldest daily backups beyond 30 pruned; monthly retained up to 12                                    |
| A-BS-3 | D39          | Analytics export                       | Attendance data exists           | Click Analytics Export → CSV | Aggregated CSV downloaded; contains compliance/participation per course                             |
| A-BS-4 | D38          | Academic structure updates are audited | Admin moves course from Y1 to Y2 | Perform structural change    | Audit log entry records change with admin user, timestamp, before/after                             |
| A-BS-5 | D42          | No buildings/campuses table            | Inspect DB schema                | Check migration              | No `buildings` or `campuses` table exists; classroom_name + lat/lng used instead                    |

### 2.9 Audit Logs

| #      | Decision IDs | Case                               | Preconditions               | Steps           | Expected Result                                               |
| ------ | ------------ | ---------------------------------- | --------------------------- | --------------- | ------------------------------------------------------------- |
| A-AL-1 | D22          | Excuse action appears in audit log | Professor excuses a student | View Audit Logs | Entry shows: excused_by, excused_at, student, session, reason |

---

## 3. Professor Portal Tests

### 3.1 Session Creation (Locked — from My Courses)

| #      | Decision IDs | Case                                  | Preconditions                                                                             | Steps                                                     | Expected Result                                                                                       |
| ------ | ------------ | ------------------------------------- | ----------------------------------------------------------------------------------------- | --------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| P-SC-1 | D11          | Create session locked to course       | Professor assigned to CS101; opens from My Courses                                        | Click [🔐 Open Session] on CS101 card                     | Course fixed at top (locked 🔒); no course selector visible                                           |
| P-SC-2 | D12, D13     | Session with window math              | Course scheduled 7:00–8:30; professor sets duration=15, present=5, late=10                | Review form                                               | Shows: Present 5 + Late 10 ≤ Duration 15; expires_at = min(now+15, 8:30) = 7:25; helper text explains |
| P-SC-3 | D13          | Reject: windows exceed duration       | present=10, late=10, duration=15                                                          | Submit                                                    | Validation error: "10 + 10 > 15 violates P+L ≤ Duration"                                              |
| P-SC-4 | D18          | Session QR payload generated          | Session created                                                                           | Inspect generated QR                                      | QR decodes to `{"v":1,"code":"A7X-9K2M","course":123,"radius":30,"pw":5,"lw":10}`                     |
| P-SC-5 | D13          | P+L equals duration (boundary valid)  | Course defaults: present=5, late=10, duration=15                                          | Set present=5, late=10, duration=15; submit               | Session created successfully; expires_at computed correctly                                           |
| P-SC-6 | D13          | Late boundary exact-second            | Session created with present=5, late=10, duration=15; student scans at exactly t+5min0sec | Student completes scan at exactly 5:00 after session open | Status = late (first second of late window, not present)                                              |
| P-SC-7 | D18          | Unknown QR version handled gracefully | Student scans QR with `"v":99`                                                            | Client receives QR payload with unknown version           | Graceful error: "App update required" or fallback to manual code entry                                |

### 3.2 Session Creation (Selector — from Dashboard)

| #      | Decision IDs | Case                                           | Preconditions                                      | Steps                                              | Expected Result                                                  |
| ------ | ------------ | ---------------------------------------------- | -------------------------------------------------- | -------------------------------------------------- | ---------------------------------------------------------------- |
| P-SS-1 | D11          | Dashboard "New Session" shows course selector  | Professor assigned to 3 courses this term          | Click [+ New Session] from Dashboard               | Dropdown lists only professor's active assignments this semester |
| P-SS-2 | D11          | Selector filtered to current term              | Professor assigned to CS101 in 1st_sem and 2nd_sem | Open selector in 1st_sem context                   | Only CS101 (1st_sem) shown; 2nd_sem assignment excluded          |
| P-SS-3 | D9           | Assistant professor opens session via selector | Assistant (is_primary=false) assigned to GE101     | Click [+ New Session] from Dashboard; select GE101 | Session created successfully; assistant listed as session opener |

### 3.3 Active Session / Live View

| #      | Decision IDs | Case                     | Preconditions                                                      | Steps                                                     | Expected Result                                                                                        |
| ------ | ------------ | ------------------------ | ------------------------------------------------------------------ | --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| P-AS-1 | D13          | Scan window countdown    | Session active; present=5, late=10, duration=15; 7 minutes elapsed | View active session                                       | Dual timers shown: "⏱ Scan window 8:23" (countdown) / "🏁 Class ends 8:30"; status legend visible      |
| P-AS-2 | D13          | Duration expiry banner   | Session window expired                                             | View active session                                       | Banner: "Scanning closed — waiting for offline syncs"                                                  |
| P-AS-3 | D15          | Student status display   | Students scanned: 2 present, 1 late, 3 absent, 1 excused           | View feed                                                 | Row statuses: ✅ Present, ⏰ Late, ❌ Absent, 📝 Excused; count totals shown                           |
| P-AS-4 | D23          | Excuse All Absent — bulk | 5 students marked absent in session                                | Click [Excuse All Absent]; enter reason "Class cancelled" | All 5 attendance records → status=excused; excuse_requests created for each; original_status preserved |

### 3.4 Attendance List & Filters

| #      | Decision IDs | Case                              | Preconditions                              | Steps              | Expected Result                                              |
| ------ | ------------ | --------------------------------- | ------------------------------------------ | ------------------ | ------------------------------------------------------------ |
| P-AL-1 | D2, D15      | Filter by section                 | Session has students from sections A and B | Filter Section=A   | Only section A students shown                                |
| P-AL-2 | D15          | Status filter includes all values | Multiple statuses present                  | Filter by Rejected | Only rejected records shown; rejection reason column visible |

### 3.5 Excuse Actions

| #      | Decision IDs | Case                                       | Preconditions                               | Steps                                                         | Expected Result                                                                                             |
| ------ | ------------ | ------------------------------------------ | ------------------------------------------- | ------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| P-EX-1 | D20, D21a    | Quick-excuse an absent student             | Student absent in active session            | Click [📝 Excuse] on absent row; enter reason                 | `excuse_requests` row: initiated_via="quick"; attendance status → excused; original_status=absent preserved |
| P-EX-2 | D20, D21b    | Prof-initiated with evidence               | Professor holds excuse letter               | Open excuse form; attach photo of letter; approve immediately | `excuse_requests`: initiated_via="prof_with_evidence"; status=approved; attachment stored in S3             |
| P-EX-3 | D22          | Excuse overrides late status               | Student scanned late (original_status=late) | Professor excuses student                                     | Final status=excused; original_status=late preserved in record                                              |
| P-EX-4 | D21c         | Student-initiated request — approve        | Student submitted excuse request            | Professor reviews pending request; approves                   | status → approved; reviewed_by set; reviewed_at set                                                         |
| P-EX-5 | D21c         | Student-initiated request — reject         | Student submitted excuse request            | Professor reviews; rejects with review_notes                  | status → rejected; student sees rejection in history                                                        |
| P-EX-6 | D20          | Excuse audit trail complete                | Any excuse path                             | Query excuse_requests                                         | Fields present: initiated_by, initiated_via, reason, excused_by, excused_at, attachment_urls, status        |
| P-EX-7 | D24          | Attachment stored in S3-compatible storage | Prof uploads excuse letter                  | Check attachment URL                                          | URL points to S3/Supabase Storage/R2; local filesystem in dev                                               |

### 3.6 Session History

| #      | Decision IDs | Case                            | Preconditions                    | Steps                | Expected Result                                                                                            |
| ------ | ------------ | ------------------------------- | -------------------------------- | -------------------- | ---------------------------------------------------------------------------------------------------------- |
| P-SH-1 | D13          | Session history shows breakdown | 5 sessions with varying statuses | View Session History | Each row: Date, Code, Section, Present/Late/Absent mini-breakdown, Rate(compliance, tooltip participation) |
| P-SH-2 | D2           | Section filter in history       | Sessions across sections A and B | Filter Section=A     | Only sessions with section A students shown                                                                |

### 3.7 Reports

| #      | Decision IDs | Case                                     | Preconditions                                        | Steps                                          | Expected Result                                                        |
| ------ | ------------ | ---------------------------------------- | ---------------------------------------------------- | ---------------------------------------------- | ---------------------------------------------------------------------- |
| P-RP-1 | D37          | All Courses aggregate tab                | Professor assigned to 3 courses with 6 weeks of data | Click All Courses tab                          | Aggregate bars per day/week/month across all 3 courses; avg line shown |
| P-RP-2 | D34          | Per-Course comparison with cohort filter | GE101 taught to BSCS Y1 and BSIT Y1                  | Per-Course Comparison tab; filter Program=BSCS | Only BSCS·Y1 bars shown for GE101                                      |
| P-RP-3 | D36          | Metric toggle in reports                 | Data exists                                          | Toggle to Participation Rate                   | Bars update: (present+late+excused)/total instead of present/total     |

### 3.8 Profile / Settings

| #      | Decision IDs | Case                    | Preconditions       | Steps                                     | Expected Result                                                         |
| ------ | ------------ | ----------------------- | ------------------- | ----------------------------------------- | ----------------------------------------------------------------------- |
| P-PR-1 | D32          | Profile is read-only    | Professor logged in | Open Profile tab                          | All identity fields disabled; note "Changes handled by Admin" displayed |
| P-PR-2 | D32          | Password change allowed | Same                | Click Change Password; enter new password | Password updated; policy hint displayed                                 |

---

## 4. Student Portal Tests

### 4.1 Scan Flow (5-Step Sequential)

| #       | Decision IDs | Case                                   | Preconditions                                          | Steps                                    | Expected Result                                                                                     |
| ------- | ------------ | -------------------------------------- | ------------------------------------------------------ | ---------------------------------------- | --------------------------------------------------------------------------------------------------- |
| S-SC-1  | D27, D18     | Step 1 — Type session code             | Session active with code "A7X-9K2M"                    | Enter code manually; click Verify        | Session config fetched: course, duration, windows, geofence radius; proceed to step 2               |
| S-SC-2  | D27, D18     | Step 1 — Scan session QR               | Session QR displayed                                   | Scan QR code                             | QR decoded: `{"v":1,"code":"A7X-9K2M","course":123,...}`; session config fetched; proceed to step 2 |
| S-SC-3  | D27, D19     | Step 2 — Scan student ID QR            | Session verified                                       | Scan student-ID QR containing "24-2111"  | Student number resolved; student record fetched (enrollment + face embedding + duplicate check)     |
| S-SC-4  | D27          | Step 2 — Duplicate scan rejected       | Student already scanned for this session               | Scan same ID again                       | Error: "Already scanned for this session"; no duplicate record created                              |
| S-SC-5  | D27          | Step 2 — Not enrolled rejected         | Student not enrolled in session's offering              | Scan non-enrolled student ID             | Error: "Not enrolled in this course"                                                                |
| S-SC-6  | D27          | Step 3 — GPS geofence pass             | Student within 30m of classroom                        | Auto-runs GPS check                      | Distance < 30m; green pill "Within geofence"; proceed to step 4                                     |
| S-SC-7  | D27          | Step 3 — GPS geofence fail             | Student 50m outside radius                             | Auto-runs GPS check                      | Red pill "Outside geofence"; retry option; cannot proceed                                           |
| S-SC-8  | D27, D31     | Step 4 — Liveness pass                 | Face embedded; student within radius                   | Blink → Turn Left → Turn Right challenge | Each step confirmed; cosine similarity ≥ 0.7; "Verifying identity…" spinner; proceed to step 5      |
| S-SC-9  | D27, D31     | Step 4 — Liveness fail (face mismatch) | Face embedded but wrong person                         | Complete liveness challenge              | Cosine similarity < 0.65; "Face does not match enrolled photo"; cannot proceed                      |
| S-SC-10 | D27, D13     | Step 5 — Result: Present               | Scan within present_window_minutes                     | Complete all steps                       | Overlay: "PRESENT ✅" + timestamp; attendance record written with status=present                    |
| S-SC-11 | D27, D13     | Step 5 — Result: Late                  | Scan within late_window_minutes (after present window) | Complete all steps                       | Overlay: "LATE ⏰" + timestamp; status=late                                                         |
| S-SC-12 | D18          | Step 1 — Invalid code                  | Expired session code entered                           | Enter code; click Verify                 | Error: "Invalid or expired session code"                                                            |
| S-SC-13 | D28, D29     | Step 4 — No face enrolled              | Student has no face_embedding                          | Reach step 4                             | Error: "Face not enrolled — contact admin"; cannot proceed                                          |
| S-SC-14 | D29          | Embedding pull on login                | Student logs in; server version > local version        | Login                                    | Client fetches new embedding; caches encrypted in IndexedDB; version updated                        |

### 4.2 Attendance History

| #      | Decision IDs | Case                        | Preconditions                                                   | Steps                                | Expected Result                                           |
| ------ | ------------ | --------------------------- | --------------------------------------------------------------- | ------------------------------------ | --------------------------------------------------------- |
| S-AH-1 | D36          | Compliance % displayed      | Student has 10 sessions: 7 present, 1 late, 1 excused, 1 absent | View History                         | Compliance = 7/10 = 70%; Participation = (7+1+1)/10 = 90% |
| S-AH-2 | D15          | Status multi-select filter  | History has all status types                                    | Filter by Excused + Rejected         | Only excused and rejected rows shown                      |
| S-AH-3 | D21c         | Request Excuse from history | Student has absent record                                       | Click [Request Excuse] on absent row | Opens excuse request form with evidence upload            |

### 4.3 Schedule

| #       | Decision IDs | Case             | Preconditions                                        | Steps           | Expected Result                                                                   |
| ------- | ------------ | ---------------- | ---------------------------------------------------- | --------------- | --------------------------------------------------------------------------------- |
| S-SCH-1 | D4           | Month grid view  | Student enrolled in 2 courses with schedule_days=MWF | Open Schedule   | Month grid shows color-coded course pills on M/W/F cells                          |
| S-SCH-2 | D4           | Day detail sheet | Past class day                                       | Tap on day cell | Detail cards show professor, program·year badge, status (attended/excused/absent) |

### 4.4 Profile / Settings

| #      | Decision IDs | Case                              | Preconditions     | Steps           | Expected Result                                                                                       |
| ------ | ------------ | --------------------------------- | ----------------- | --------------- | ----------------------------------------------------------------------------------------------------- |
| S-PR-1 | D32          | Profile read-only                 | Student logged in | Open Profile    | All identity fields disabled; Face enrollment status shown; QR-of-student-number preview tile visible |
| S-PR-2 | D32          | Only password/security changeable | Same              | Change Password | Password updated; other fields remain read-only                                                       |

### 4.5 Student Excuse Request

| #      | Decision IDs | Case                        | Preconditions              | Steps                                                | Expected Result                                                                            |
| ------ | ------------ | --------------------------- | -------------------------- | ---------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| S-EX-1 | D21c, D24    | Submit excuse with evidence | Student has absent record  | Fill reason; attach excuse letter (PDF <5MB); submit | `excuse_requests` row created: initiated_by=student, status=pending; attachment URL stored |
| S-EX-2 | D21c         | Reject oversized attachment | Student attaches 10MB file | Submit                                               | Error: "Attachment exceeds 5 MiB limit"                                                    |
| S-EX-3 | D21c         | View excuse request status  | Request submitted          | Open excuse history                                  | Status shown: pending/approved/rejected; review_notes if rejected                          |

---

## 5. Shared / Auth Tests

| #       | Decision IDs | Case                                                      | Preconditions                     | Steps                            | Expected Result                                                              |
| ------- | ------------ | --------------------------------------------------------- | --------------------------------- | -------------------------------- | ---------------------------------------------------------------------------- |
| SH-AU-1 | D25          | No "mark all present" endpoint exists                     | Inspect API surface               | Search for endpoint              | No endpoint allows marking all students present in any role                  |
| SH-AU-2 | D25          | No security-disabled session option                       | Inspect session creation form     | Check form fields                | No toggle/option to disable security features on a session                   |
| SH-AU-3 | D26          | Remote class uses relaxed geofence but liveness mandatory | Session created with large radius | Student scans remotely           | Geofence passes (large radius); liveness challenge still required            |
| SH-AU-4 | —            | MFA setup                                                 | Professor/student logged in       | Enable MFA in settings           | MFA secret generated; QR code for authenticator app displayed; TOTP verified |
| SH-AU-5 | —            | Forgot password flow                                      | User exists                       | Request password reset via email | OTP sent; password reset completes after OTP verification                    |

---

## 6. Security / Threat-Model Tests

| #      | Threat                   | Decision IDs  | Case                                          | Preconditions                                       | Steps                            | Expected Result                                                                                                                                                               |
| ------ | ------------------------ | ------------- | --------------------------------------------- | --------------------------------------------------- | -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| SEC-1  | Buddy punching           | D19, D27, D28 | Different person scans student QR             | Student A's QR scanned by Person B (different face) | Complete scan flow               | Step 4 face mismatch detected; attendance rejected                                                                                                                            |
| SEC-2  | Photo/video replay of QR | D27, D28      | Student shows printed photo of QR to camera   | Print QR and hold to camera                         | Scan student-ID QR               | Live QR detection rejects static image (no movement/depth); liveness challenge fails for photo                                                                                |
| SEC-3  | QR relay                 | D18, D19      | QR code forwarded to remote student           | Remote student scans forwarded QR                   | Scan flow                        | Session QR is one-time per session; student-ID QR only contains student number; course context from session; GPS geofence catches remote                                      |
| SEC-4  | Sibling confusion        | D31           | Twin scans QR of sibling                      | Twin completes liveness challenge                   | Face comparison                  | Cosine similarity may be close (known limitation per D31); test verifies system behaves correctly — if threshold met, accepted; if not, rejected; documented as accepted risk |
| SEC-5  | GPS spoof                | D27           | GPS coordinates spoofed to classroom location | Spoof GPS to exact classroom lat/lng                | Scan flow                        | Geofence passes; liveness + face match still required — spoof alone insufficient                                                                                              |
| SEC-6  | Token theft              | D18           | Stale/used session code reused                | Replay old session code                             | Verify code                      | Expired/already-used codes rejected; HMAC validation fails                                                                                                                    |
| SEC-7  | Offline scan replay      | D16           | Offline scan synced after session expires     | Scan offline during session; sync after expires_at  | Sync server validates scanned_at | scanned_at outside window → rejected with reason=session_expired                                                                                                              |
| SEC-8  | Embedding tampering      | D28, D29      | Client modifies cached embedding              | Tamper with IndexedDB data                          | Scan flow                        | Server validates embedding version; client-side tamper has no effect on server-side verification                                                                              |
| SEC-9  | Backup encryption        | D39           | Backup file accessed without key              | Obtain backup file; attempt pg_restore without key  | Restore attempt                  | Decryption fails; data inaccessible without AES-256-GCM key                                                                                                                   |
| SEC-10 | Rate limiting            | —             | Brute-force login attempts                    | 10+ failed login attempts in rapid succession       | Continue attempting login        | Account locked; rate limit enforced                                                                                                                                           |

---

## 7. Offline & Sync Tests

| #     | Decision IDs | Case                                  | Preconditions                                                      | Steps                                 | Expected Result                                                                                                  |
| ----- | ------------ | ------------------------------------- | ------------------------------------------------------------------ | ------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| OFF-1 | D16, D15     | Offline scan queued                   | Device offline; student completes scan flow                        | Submit scan                           | Record stored in IndexedDB with `scanned_at`; status=pending; queue count displayed                              |
| OFF-2 | D16          | Sync validates scanned_at             | Device comes online; offline scan was during active session        | Background sync triggers              | Server validates scanned_at against session window; record accepted (if within window); status → present or late |
| OFF-3 | D16          | Offline scan expired on sync          | Device offline during session; syncs 2 hours after session expires | Sync triggers                         | Server rejects: scanned_at outside window; status=rejected; reason=session_expired                               |
| OFF-4 | D30          | Offline face verification             | Student offline; has cached embedding                              | Complete scan flow offline            | Face verified locally against cached embedding; only scores/evidence synced to server                            |
| OFF-5 | D29          | Embedding pull-on-login handshake     | Student logs in; server has version 3; client has version 2        | Login                                 | Client detects version mismatch; fetches version 3 embedding; caches encrypted                                   |
| OFF-6 | D29          | Embedding version match (no download) | Client has current version                                         | Login                                 | No embedding download; uses cached version                                                                       |
| OFF-7 | D15          | Pending count display                 | 3 offline scans queued                                             | View scan result or offline banner    | Banner shows "3 awaiting verification (face)"                                                                    |
| OFF-8 | D27          | Offline scan happy path end-to-end    | Student offline, embedded, enrolled                                | Complete 5 steps offline → later sync | All steps completed; record accepted on sync with correct present/late status                                    |

---

## 8. Decision Coverage Matrix

Every decision D1–D43 is covered by at least one test case above.

| Decision | Covered By (Test IDs)                                                                                                                                                                               |
| -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D1       | A-PM-1, A-PM-2, A-PM-4, A-PM-5, A-YL-3                                                                                                                                                              |
| D2       | A-CM-6, A-BE-1, A-BE-3, P-AL-1, S-SCH-1                                                                                                                                                             |
| D3       | A-YL-1, A-YL-2, A-YL-3                                                                                                                                                                              |
| D4       | A-CM-1a, A-CM-1b, A-CM-7, A-CM-8, A-CM-9, S-SCH-1, S-SCH-2                                                                                                                                    |
| D5       | A-BE-1, A-BE-2, A-YL-3                                                                                                                                                                              |
| D6       | A-PM-1, A-PM-3, A-PM-4                                                                                                                                                                              |
| D7       | A-PA-1, A-PA-2, A-PA-4                                                                                                                                                                              |
| D8       | A-PA-2                                                                                                                                                                                              |
| D9       | A-PA-3, P-SS-3                                                                                                                                                                                      |
| D10      | P-AS-1, P-SS-1 (session infrastructure handles prof-absence without special feature)                                                                                                                |
| D11      | P-SC-1, P-SS-1, P-SS-2                                                                                                                                                                              |
| D12      | P-SC-2                                                                                                                                                                                              |
| D13      | P-SC-2, P-SC-3, P-SC-5, P-SC-6, P-AS-1, P-AS-2, S-SC-10, S-SC-11                                                                                                                                    |
| D14      | A-CM-5                                                                                                                                                                                              |
| D15      | P-AS-3, P-AL-2, S-AH-2, OFF-7, OFF-3 (rejection reason codes: online flow stops before record creation for geoface/liveness failures; rejection reasons written only on sync-path failures per D16) |
| D16      | OFF-1, OFF-2, OFF-3, SEC-7                                                                                                                                                                          |
| D17      | A-CM-3, A-CM-4                                                                                                                                                                                      |
| D18      | P-SC-4, P-SC-7, S-SC-1, S-SC-2, S-SC-12, SEC-6                                                                                                                                                      |
| D19      | S-SC-3, SEC-1, SEC-2, SEC-3                                                                                                                                                                         |
| D20      | P-EX-1, P-EX-6                                                                                                                                                                                      |
| D21      | P-EX-1, P-EX-2, P-EX-4, P-EX-5, S-EX-1                                                                                                                                                              |
| D22      | P-EX-3, P-EX-1, P-EX-4                                                                                                                                                                              |
| D23      | P-AS-4                                                                                                                                                                                              |
| D24      | P-EX-7, S-EX-1                                                                                                                                                                                      |
| D25      | SH-AU-1, SH-AU-2                                                                                                                                                                                    |
| D26      | SH-AU-3                                                                                                                                                                                             |
| D27      | S-SC-1 through S-SC-11, OFF-8                                                                                                                                                                       |
| D28      | A-FE-1, A-FE-2, A-FE-3, A-FE-4, A-FE-5, S-SC-13, SEC-1                                                                                                                                              |
| D29      | S-SC-14, OFF-5, OFF-6                                                                                                                                                                               |
| D30      | OFF-4                                                                                                                                                                                               |
| D31      | S-SC-8, S-SC-9, SEC-4                                                                                                                                                                               |
| D32      | P-PR-1, P-PR-2, S-PR-1, S-PR-2                                                                                                                                                                      |
| D33      | A-AN-1, A-AN-6, A-AN-7                                                                                                                                                                              |
| D34      | A-AN-2, P-RP-2                                                                                                                                                                                      |
| D35      | A-AN-3, A-AN-4                                                                                                                                                                                      |
| D36      | A-AN-5, P-RP-3, S-AH-1                                                                                                                                                                              |
| D37      | P-RP-1                                                                                                                                                                                              |
| D38      | A-PM-6, A-BS-4                                                                                                                                                                                      |
| D39      | A-BS-1, A-BS-2, A-BS-3, SEC-9                                                                                                                                                                       |
| D40      | A-PM-6 (settings block + deep-link; full nav bar verification: Dashboard/Students/Professors/Programs/Analytics/Audit Logs/Settings)                                                                |
| D41      | (Technology decision — verified via dependency audit, not functional test)                                                                                                                          |
| D42      | A-BS-5                                                                                                                                                                                              |
| D43      | A-FE-1, A-FE-4                                                                                                                                                                                      |

---

## Appendix: Environment Variables for Test Configuration

Tests should use the following env vars (from §8) to validate configurable thresholds:

```bash
FACE_MATCH_THRESHOLD=0.7
FACE_REVIEW_BAND_LOW=0.65
RISK_ABSENCE_RATE_HIGH=0.30
RISK_ABSENCE_RATE_MEDIUM=0.15
RISK_STREAK_GAPS_HIGH=3
RISK_SYNC_LAG_HIGH=5
RISK_TREND_NEGATIVE=-0.05
DEFAULT_PRESENT_WINDOW_MINUTES=5
DEFAULT_LATE_WINDOW_MINUTES=10
BACKUP_ENCRYPTION_KEY=<test-key>
```

Tests must validate that changing these env vars shifts the corresponding thresholds
(e.g., setting `RISK_ABSENCE_RATE_HIGH=0.20` should flag students at 21% absence
as high-risk instead of waiting for 31%).
