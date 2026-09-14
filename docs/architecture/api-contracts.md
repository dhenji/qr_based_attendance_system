# API Contracts — QR Attendance System

> Canonical reference for every endpoint. Each entry: method, path, role guard,
> request schema, response schema, error codes.

---

## Conventions

| Aspect      | Standard                                                                                    |
| ----------- | ------------------------------------------------------------------------------------------- |
| Auth        | `Authorization: Bearer <JWT>` header on all `/admin/*`, `/professor/*`, `/student/*` routes |
| Role guards | FastAPI `Depends(require_role(Role.admin))` etc. 403 on mismatch                            |
| Pagination  | `?page=1&size=20` → `{ items: [...], total: int, page: int, size: int }`                    |
| Error shape | `{ detail: { code: string, message: string, field?: string } }`                             |
| Idempotency | Scan submit accepts `X-Idempotency-Key` header; duplicate returns prior result              |
| Timestamps  | ISO-8601 UTC (`2026-08-25T14:30:00Z`)                                                       |
| Soft-delete | `DELETE` endpoints archive (set `is_active=false`) unless stated destructive               |

### DTO → Column Mapping

DTO field names below are canonical and exotic DB column names are mapped where they differ:

| DTO field       | DB column                                  |
| --------------- | ------------------------------------------ |
| `status`        | `attendance_records.validation_status`     |
| `scanned_at`    | `attendance_records.timestamp`             |
| `student_number`| `students.student_id`                      |
| session `code`  | `sessions.session_code`                    |
| `offering`      | column `offering_id`                       |
| geofence `radius`| `classroom_radius_meters`                 |
| session `status`| computed DTO (no backing column)          |

---

## Session QR Payload (D18)

Scanned by students. Server generates HMAC-signed JSON.

```json
{
  "v": 1,
  "code": "A7X-9K2M",
  "offering": 123,
  "radius": 30,
  "pw": 5,
  "lw": 10
}
```

| Field      | Type   | Meaning                                |
| ---------- | ------ | -------------------------------------- |
| `v`        | int    | Payload version (migration-safe)       |
| `code`     | string | 6–8 char session code (HMAC-truncated) |
| `offering` | int    | `course_offerings.id`                  |
| `radius`   | int    | Geofence radius in metres              |
| `pw`       | int    | Present window minutes                 |
| `lw`       | int    | Late window minutes                    |

**Note:** The HMAC payload uses compact keys. On verify, they map to DB columns:
`code` → `sessions.session_code`, `offering` → `sessions.offering_id`,
`radius` → `sessions.classroom_radius_meters`, `pw` → `present_window_minutes`,
`lw` → `late_window_minutes`.

---

## Excuse State Machine

```
          ┌─────────────────────────────────────────────────┐
          │                                                 │
          ▼                                                 │
      ┌─────────┐    professor approves    ┌──────────┐    │
      │ PENDING │─────────────────────────►│ APPROVED │    │
      └─────────┘                          └──────────┘    │
          │                                   ▲  ▲         │
          │ professor rejects                 │  │         │
          ▼                                   │  │         │
      ┌──────────┐                            │  │         │
      │ REJECTED │                            │  │         │
      └──────────┘                            │  │         │
          │                                   │  │         │
          └───────────────────────────────────┘  │         │
               (student re-submits → new request) │         │
                                                 │         │
      Prof-initiated (quick / with evidence):     │         │
        → immediate APPROVED (skips PENDING)      │         │
          ┌───────────────────────────────────────┘         │
          │                                                  │
          └──────────────────────────────────────────────────┘
```

| Transition         | Actor                     | Condition                                                     |
| ------------------ | ------------------------- | ------------------------------------------------------------- |
| → PENDING          | Student                   | Student submits excuse request with reason + evidence         |
| PENDING → APPROVED | Professor                 | Reviews evidence, approves                                    |
| PENDING → REJECTED | Professor                 | Reviews evidence, rejects (review_notes required)             |
| → APPROVED         | Professor (quick)         | Prof marks absent/late student excused with reason; immediate |
| → APPROVED         | Professor (with evidence) | Prof holds physical proof, files + approves immediately       |
| REJECTED → PENDING | Student                   | Student may re-submit (new request record)                    |

---

## ADMIN Endpoints

### Programs

#### `GET /admin/programs`

List all programs (with year-level counts).

|                  |                                                                                                                   |
| ---------------- | ----------------------------------------------------------------------------------------------------------------- |
| **Role**         | admin                                                                                                             |
| **Query**        | `?is_active=true&page=1&size=20`                                                                                  |
| **Response 200** | `{ items: [{ id, code, name, description, total_years, is_active, created_at, updated_at }], total, page, size }` |

#### `POST /admin/programs`

Create a new program.

|                  |                                                                                         |
| ---------------- | --------------------------------------------------------------------------------------- |
| **Role**         | admin                                                                                   |
| **Request**      | `{ code: string, name: string, description?: string, total_years: int }`                |
| **Response 201** | `{ id, code, name, description, total_years, is_active: true, created_at, updated_at }` |
| **Errors**       | 409 `program_code_exists` · 422 validation                                              |

#### `GET /admin/programs/{id}`

|                  |                                                |
| ---------------- | ---------------------------------------------- |
| **Response 200** | Program object with nested `year_levels` array |

#### `PATCH /admin/programs/{id}`

|                  |                                       |
| ---------------- | ------------------------------------- |
| **Request**      | `{ name?, description?, is_active? }` |
| **Response 200** | Updated program                       |

#### `DELETE /admin/programs/{id}`

Archive program (sets `is_active=false`). Cascades year-levels/courses inactive.

|                  |            |
| ---------------- | ---------- |
| **Response 204** | No content |

---

### Year Levels

#### `GET /admin/programs/{pid}/years`

|                  |                                                                                        |
| ---------------- | -------------------------------------------------------------------------------------- |
| **Response 200** | `{ items: [{ id, program_id, year_number, label, term_structure, sort_order }], ... }` |

#### `POST /admin/programs/{pid}/years`

|                  |                                                                                     |
| ---------------- | ----------------------------------------------------------------------------------- |
| **Request**      | `{ year_number: int, label: string, term_structure: { terms: [{ code, label }] } }` |
| **Response 201** | Created year level                                                                  |

#### `PATCH /admin/programs/{pid}/years/{yid}`

|                  |                                            |
| ---------------- | ------------------------------------------ |
| **Request**      | `{ label?, term_structure?, sort_order? }` |
| **Response 200** | Updated year level                         |

#### `DELETE /admin/programs/{pid}/years/{yid}`

Archive year level. Restrict if courses exist.

|                  |                        |
| ---------------- | ---------------------- |
| **Response 204** | No content             |
| **Errors**       | 409 `year_has_courses` |

---

### Courses

#### `GET /admin/programs/{pid}/years/{yid}/courses`

|                  |                                                                                                              |
| ---------------- | ------------------------------------------------------------------------------------------------------------ |
| **Response 200** | `{ items: [{ id, course_code, course_name, units, session_duration_hours, is_active, created_at, updated_at }], ... }` |

#### `POST /admin/programs/{pid}/years/{yid}/courses`

|                  |                                                                                                              |
| ---------------- | ------------------------------------------------------------------------------------------------------------ |
| **Request**      | `{ course_code: string, course_name: string, units: int, session_duration_hours: numeric(3,1) }`            |
| **Response 201** | Created course template                                                                                      |
| **Errors**       | 409 `course_code_exists` · 422 validation                                                                    |

#### `GET /admin/courses/{cid}`

|                  |                                              |
| ---------------- | -------------------------------------------- |
| **Response 200** | Full course template                         |

#### `PATCH /admin/courses/{cid}`

|                  |                             |
| ---------------- | --------------------------- |
| **Request**      | Any mutable template field from POST |
| **Response 200** | Updated course template              |

#### `DELETE /admin/courses/{cid}`

Archive course template.

|                  |            |
| ---------------- | ---------- |
| **Response 204** | No content |

---

### Course Offerings

A course offering is a specific instance of a course template for a program, year level, and semester. It holds scheduling, classroom, and window configuration.

#### `GET /admin/offerings`

|                  |                                                                                                                                                                                                                          |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Query**        | `?program_id?&year_level_id?&semester?&course_id?&is_active?&page=1&size=20`                                                                                                                                             |
| **Response 200** | `{ items: [{ id, course_id, program_id, year_level_id, semester, academic_year, sessions_per_week, semester_weeks, schedule_days, schedule_start_time, schedule_end_time, classroom_name, classroom_lat, classroom_lng, default_present_window_minutes, default_late_window_minutes, is_active, created_at, updated_at }], ... }` |

#### `POST /admin/offerings`

|                  |                                                                                                                                                                                                                                                                    |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Request**      | `{ course_id: int, program_id: int, year_level_id: int, semester: string, academic_year: string, sessions_per_week: int, semester_weeks: int, schedule_days: string, schedule_start_time: time, schedule_end_time: time, classroom_name?: string, classroom_lat?: numeric, classroom_lng?: numeric, default_present_window_minutes?: int, default_late_window_minutes?: int }` |
| **Response 201** | Created course offering                                                                                                                                                                                                                                             |
| **Errors**       | 409 `offering_exists` · 404 `course_not_found` · 404 `program_not_found` · 422 `windows_exceed_duration`                                                                                                                                                            |

#### `GET /admin/offerings/{oid}`

|                  |                  |
| ---------------- | ---------------- |
| **Response 200** | Course offering  |

#### `PATCH /admin/offerings/{oid}`

|                  |                                                |
| ---------------- | ---------------------------------------------- |
| **Request**      | Any mutable field from POST (except course_id, program_id, year_level_id, semester, academic_year) |
| **Response 200** | Updated course offering                        |

#### `DELETE /admin/offerings/{oid}`

Archive course offering.

|                  |            |
| ---------------- | ---------- |
| **Response 204** | No content |

#### `GET /admin/offerings/{oid}/professors`

|                  |                                                                                                                               |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| **Response 200** | `{ items: [{ offering_id, professor_id, is_primary, effective_from, effective_to, semester, assigned_by, assigned_at }], ... }` |

#### `POST /admin/offerings/{oid}/professors`

Assign professor to course offering.

|                  |                                                                                                        |
| ---------------- | ------------------------------------------------------------------------------------------------------ |
| **Request**      | `{ professor_id: int, is_primary: bool, effective_from: date, effective_to?: date, semester: string }` |
| **Response 201** | Created assignment                                                                                     |
| **Errors**       | 409 `overlapping_assignment` · 404 `professor_not_found`                                               |

#### `DELETE /admin/offerings/{oid}/professors/{pid}`

End assignment (set `effective_to` = today).

|                  |                                  |
| ---------------- | -------------------------------- |
| **Response 200** | `{ effective_to: "YYYY-MM-DD" }` |
| **Errors**       | 404 `assignment_not_found`       |

#### `POST /admin/offerings/{oid}/enrollments/bulk`

Bulk-enroll students via CSV upload.

|                  |                                                               |
| ---------------- | ------------------------------------------------------------- |
| **Request**      | `multipart/form-data: file=students.csv`                      |
| **Response 201** | `{ enrolled: int, skipped: int, errors: [{ line, reason }] }` |
| **Errors**       | 422 `validation_error`                                        |

---

### Face Enrollment

#### `POST /admin/face-enrollment/{student_id}`

Upload 3 photos (front, left, right) for face embedding generation.

|                  |                                                                                             |
| ---------------- | ------------------------------------------------------------------------------------------- |
| **Request**      | `multipart/form-data: front=Image, left=Image, right=Image`                                 |
| **Response 201** | `{ student_id, face_enrolled_at, face_embedding_version: int }`                             |
| **Errors**       | 400 `invalid_image` · 400 `no_face_detected` · 400 `multiple_faces` · 422 `quality_too_low` |

#### `GET /admin/face-enrollment/{student_id}`

Check enrollment status.

|                  |                                                                  |
| ---------------- | ---------------------------------------------------------------- |
| **Response 200** | `{ enrolled: bool, face_enrolled_at?, face_embedding_version? }` |

---

### Analytics

#### `GET /admin/analytics/overview`

|                  |                                                                                                  |
| ---------------- | ------------------------------------------------------------------------------------------------ |
| **Role**         | admin                                                                                            |
| **Query**        | `?program_id?&year_level_id?&semester?&date_from?&date_to?`                                      |
| **Response 200** | `{ total_students, total_courses, avg_compliance_rate, avg_participation_rate, total_sessions }` |

#### `GET /admin/analytics/course-comparison`

|                  |                                                                                                                                |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| **Query**        | `?program_id?&year_level_id?&semester?&course_ids?&date_from?&date_to?`                                                        |
| **Response 200** | `{ items: [{ course_id, course_code, program_id, year_level_id, compliance_rate, participation_rate, total_sessions }], ... }` |

#### `GET /admin/analytics/trends`

|                  |                                                                                   |
| ---------------- | --------------------------------------------------------------------------------- |
| **Query**        | `?program_id?&year_level_id?&semester?&course_ids?&granularity=daily              | weekly | monthly&date_from?&date_to?` |
| **Response 200** | `{ items: [{ date, compliance_rate, participation_rate, total_sessions }], ... }` |

#### `GET /admin/analytics/at-risk`

|                  |                                                                                                                                                               |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Query**        | `?program_id?&year_level_id?&semester?&risk_level=low                                                                                                         | medium | high` |
| **Response 200** | `{ items: [{ student_id, student_name, program, year_level, offering_id, course_code, course_name, absence_rate, max_streak, trend_slope, risk_level, computed_at }], ... }` |

#### `POST /admin/analytics/export`

Export analytics as CSV/PDF.

|                  |                            |
| ---------------- | -------------------------- |
| **Request**      | `{ format: "csv"           | "pdf", program_id?, year_level_id?, semester?, course_ids?, date_from?, date_to? }` |
| **Response 200** | File download (CSV or PDF) |

#### `POST /admin/analytics/refresh-risk`

Trigger manual risk-score recalculation (admin-only).

|                  |                                |
| ---------------- | ------------------------------ |
| **Response 202** | `{ job_id, status: "pending" }` |
| **Notes**        | `job_id` is an opaque DTO (queue job reference), not a table column. `status` is the queue job status (QueueStatus). |

---

### System Settings & Backups

#### `GET /admin/system/settings`

|                  |                                                                                                                                   |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| **Response 200** | `{ geofence_default_radius, present_window_default, late_window_default, backup_retention_daily, backup_retention_monthly, ... }` |

#### `PATCH /admin/system/settings`

|                  |                         |
| ---------------- | ----------------------- |
| **Request**      | Partial settings object |
| **Response 200** | Updated settings        |

#### `GET /admin/system/academic-structure`

List structural changes (audit log for program/year/course mutations).

|                  |                                                                                                              |
| ---------------- | ------------------------------------------------------------------------------------------------------------ |
| **Response 200** | `{ items: [{ id, action, entity_type, entity_id, old_value, new_value, performed_by, performed_at }], ... }` |

#### `GET /admin/backups`

|                  |                                                                                                          |
| ---------------- | -------------------------------------------------------------------------------------------------------- |
| **Response 200** | `{ items: [{ id, filename, kind, size_bytes, storage_backend, started_at, finished_at, status }], ... }` |

#### `POST /admin/backups`

Trigger a full backup.

|                  |                                   |
| ---------------- | --------------------------------- |
| **Response 202** | `{ backup_id, status: "started" }` |

#### `GET /admin/backups/{id}/download`

Download backup file.

|                  |                      |
| ---------------- | -------------------- |
| **Response 200** | Binary file download |

---

### Excuses (Admin View)

#### `GET /admin/excuses`

List pending excuse requests.

|                  |                                                 |
| ---------------- | ----------------------------------------------- |
| **Query**        | `?status=pending                                | approved | rejected&page=1&size=20` |
| **Response 200** | `{ items: [ExcuseRequest], total, page, size }` |

---

## PROFESSOR Endpoints

### Courses

#### `GET /professor/courses`

List professor's active course assignments with program/year badges.

|                  |                                                                                                                                                |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| **Role**         | professor                                                                                                                                      |
| **Response 200** | `{ items: [{ offering_id, course_id, course_code, course_name, program_id, program_code, year_level_id, year_level_label, semester, academic_year, section, is_primary, effective_from, effective_to }], ... }` |
| **Notes**        | `section` is derived (from `students.section` via enrollment), not its own column. |

---

### Sessions

#### `GET /professor/sessions`

|                  |                                                                                                                                        |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| **Query**        | `?from?&to?&offering_id?&page=1&size=20`                                                                                               |
| **Response 200** | `{ items: [{ id, offering_id, session_code, created_at, expires_at, duration_minutes, present_count, late_count, absent_count, status }], ... }` |
| **Notes**        | `present_count`/`late_count`/`absent_count` and `status` are computed DTOs (no columns). `status` is `active`/`closed` derived from `expires_at`/close time. `expires_at` is a regular column populated by service layer at creation (D49). |

#### `POST /professor/sessions`

Open a new attendance session.

|                  |                                                                                                                                                                                                         |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Request**      | `{ offering_id: int, duration_minutes?: int, present_window_minutes?: int, late_window_minutes?: int, classroom_radius_meters?: int, classroom_name?: string, classroom_lat?: numeric, classroom_lng?: numeric }` |
| **Response 201** | `{ id, session_code, offering_id, qr_payload: QRPayload, expires_at, scheduled_end_time, created_at }`                                                                                                            |
| **Errors**       | 409 `session_already_active` · 422 `windows_exceed_duration`                                                                                                                          |
| **Notes**        | Session created against a course offering. Schedule/classroom/window defaults copied from offering. `expires_at = min(created_at + duration_minutes, scheduled_end_time)` computed in service layer (D12, D49).                                |

#### `GET /professor/sessions/active/{id}`

Live session detail with dual timers.

|                  |                                                                                                                                                                                                            |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Response 200** | `{ id, offering, session_code, scan_window_remaining, scheduled_end_time, status, students: [{ student_number, name, section, status, scanned_at?, excuse_reason? }], counts: { present, late, pending, absent, excused } }` |
| **Notes**        | `status` and `scan_window_remaining` are computed DTOs (no columns). `students[].student_number` maps `students.student_id`; `students[].status` maps `attendance_records.validation_status`; `students[].scanned_at` maps `attendance_records.timestamp`. |

#### `POST /professor/sessions/{id}/close`

Manually close session scanning.

|                  |                                                 |
| ---------------- | ----------------------------------------------- |
| **Response 200** | `{ id, status: "closed", final_counts: {...} }`                               |
| **Notes**        | `status: "closed"` is a server-side computed DTO — sessions have no `status` column. |

---

### Excuses

#### `POST /professor/sessions/{id}/attendance/{sid}/excuse`

Quick-excuse a student for this session.

|                  |                                                                                     |
| ---------------- | ----------------------------------------------------------------------------------- |
| **Request**      | `{ reason: string }`                                                                |
| **Response 201** | `{ excuse_request_id, status: "approved", original_status, new_status: "excused" }` |
| **Notes**        | `new_status`/`original_status` are DTO fields mapping `attendance_records.validation_status`. |

#### `PATCH /professor/sessions/{id}/attendance/{sid}/excuse`

Update/edit existing excuse.

|                  |                       |
| ---------------- | --------------------- |
| **Request**      | `{ reason?: string }` |
| **Response 200** | Updated excuse        |

#### `DELETE /professor/sessions/{id}/attendance/{sid}/excuse`

Revoke excuse (revert to original status).

|                  |                                    |
| ---------------- | ---------------------------------- |
| **Response 200** | `{ reverted_to: original_status }` |

#### `POST /professor/sessions/{id}/excuse-all-absent`

Bulk excuse all absent students.

|                  |                                                  |
| ---------------- | ------------------------------------------------ |
| **Request**      | `{ reason: string }`                             |
| **Response 200** | `{ excused_count: int, reason }`                 |
| **Idempotent**   | Re-running with same session returns same result |

#### `GET /professor/excuse-requests`

List pending excuse requests for professor's courses.

|                  |                                                 |
| ---------------- | ----------------------------------------------- |
| **Query**        | `?status=pending                                | approved | rejected&page=1&size=20` |
| **Response 200** | `{ items: [ExcuseRequest], total, page, size }` |

#### `POST /professor/excuse-requests/{rid}/review`

Approve or reject an excuse request.

|                  |                               |
| ---------------- | ----------------------------- |
| **Request**      | `{ status: "approved"       | "rejected", review_notes?: string }` |
| **Response 200** | `{ id, status, reviewed_at }` |

---

### Attendance

#### `GET /professor/attendance`

Query attendance records with filters.

|                  |                                                                                                                                                 |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| **Query**        | `?offering_id?&section?&status?&from?&to?&page=1&size=20`                                                                                       |
| **Response 200** | `{ items: [{ id, student_number, student_name, section, session_id, status, original_status?, scanned_at, scanned_via, face_match_score? }], ... }` |
| **Notes**        | `student_number` maps `students.student_id`; `status` maps `attendance_records.validation_status`; `scanned_at` maps `attendance_records.timestamp`; `original_status` is the preserved pre-excuse value. |

#### `GET /professor/sessions/history`

Session history with filters.

|                  |                                                 |
| ---------------- | ----------------------------------------------- |
| **Query**        | `?offering_id?&section?&from?&to?&page=1&size=20` |
| **Response 200** | `{ items: [SessionSummary], ... }`              |

---

### Reports

#### `GET /professor/reports/all-courses`

Aggregate attendance across all assigned courses.

|                  |                                                                                                                                 |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| **Query**        | `?granularity=daily                                                                                                             | weekly | monthly&date_from?&date_to?` |
| **Response 200** | `{ items: [{ date, total_sessions, total_students, compliance_rate, participation_rate }], avg_compliance, avg_participation }` |

#### `GET /professor/reports/comparison`

Per-course comparison with program/year slicing.

|                  |                                                                                                                                |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| **Query**        | `?program_id?&year_level_id?&semester?&granularity?&date_from?&date_to?`                                                       |
| **Response 200** | `{ items: [{ course_id, course_code, program_id, year_level_id, compliance_rate, participation_rate, total_sessions }], ... }` |

#### `GET /professor/reports/trends`

Multi-series trend data.

|                  |                                                            |
| ---------------- | ---------------------------------------------------------- |
| **Query**        | `?course_ids?&metric=compliance                            | participation&granularity=daily | weekly | monthly&date_from?&date_to?` |
| **Response 200** | `{ items: [{ date, course_id, course_code, rate }], ... }` |

---

### Profile

#### `GET /professor/profile`

Read-only profile.

|                  |                                                                                                                         |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------- |
| **Response 200** | `{ id, first_name, middle_name, last_name, email, department, assigned_courses: [...], claim_status }` |
| **Notes**        | No `employee_number` column exists on `professors` — omitted. `claim_status` is a computed DTO derived from `professors.user_id` non-null. |

#### `PATCH /professor/profile/password`

Change password.

|                  |                                                                  |
| ---------------- | ---------------------------------------------------------------- |
| **Request**      | `{ current_password: string, new_password: string }`             |
| **Response 200** | `{ message: "Password updated" }`                                |
| **Errors**       | 400 `current_password_invalid` · 422 `password_policy_violation` |

---

## STUDENT Endpoints

### Session Verification

#### `POST /student/sessions/verify-code`

Verify a typed session code or scan session QR.

|                  |                                                                                                                                                                    |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Role**         | student                                                                                                                                                            |
| **Request**      | `{ code: string }`                                                                                                                                                 |
| **Response 200** | `{ session_id, offering_id, course_code, course_name, program_code, year_level_label, expires_at, scheduled_end_time, geofence: { radius, lat, lng }, present_window_minutes, late_window_minutes }` |
| **Notes**        | Nested `geofence` keys map to columns: `radius` → `classroom_radius_meters`, `lat` → `classroom_lat`, `lng` → `classroom_lng`. |
| **Errors**       | 404 `session_not_found` · 410 `session_expired`                                                                                                                    |

---

### Attendance Scan

#### `POST /student/attendance/scan`

Submit attendance scan (online or queued for offline sync).

|                  |                                                                                                                                                                                                                                                                                              |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Request**      | `{ session_id: int, student_number: string, gps: { lat: number, lng: number, accuracy: number }, liveness_evidence: { blink_detected: bool, head_turn_left: bool, head_turn_right: bool, ear_samples: number[], pnp_evidence: object }, face_match_score: number, scanned_at: ISO-8601 }` |
| **Response 200** | `{ id, status: "present"                                                                                                                                                                                                                                                          | "late" | "rejected", scanned_at, expires_at }` |
| **Errors**       | 409 `duplicate_scan` · 403 `outside_geofence` · 403 `liveness_failed` · 403 `face_mismatch` · 403 `not_enrolled` · 410 `session_expired`                                                                                                                                                     |
| **Notes**        | `student_number` maps `students.student_id`. `gps` is kept as a nested input object but stored flat as `gps_lat`/`gps_lng`; `accuracy` is folded into `liveness_evidence`. `scanned_at` maps `attendance_records.timestamp`; response `status` maps `validation_status`. |
| **Offline**      | If offline, client stores locally. On sync, server validates `scanned_at` against session window; expired → `rejected` with reason `session_expired` (D16).                                                                                                                                  |

---

### Attendance History

#### `GET /student/attendance/history`

|                  |                                                                                                                                                                                                                                                           |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Query**        | `?program_id?&year_level_id?&semester?&status?&page=1&size=20`                                                                                                                                                                                            |
| **Response 200** | `{ items: [{ id, session_id, course_code, course_name, status, original_status?, excuse_reason?, scanned_at, scanned_via }], total, page, size, summary: { compliance_rate, participation_rate, counts: { present, late, absent, excused, rejected } } }` |

---

### Schedule

#### `GET /student/schedule`

|                  |                                                                                                                                                                                 |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Response 200** | `{ offerings: [{ offering_id, course_id, course_code, course_name, program_code, year_level_label, semester, schedule_days, schedule_start_time, schedule_end_time, classroom_name, professor_name }] }` |

---

### Excuses

#### `POST /student/excuse-requests`

Submit an excuse request with evidence.

|                  |                                                                        |
| ---------------- | ---------------------------------------------------------------------- |
| **Request**      | `multipart/form-data: session_id=int, reason=string, attachment=File?` |
| **Response 201** | `{ id, status: "pending", requested_at }`                              |

#### `GET /student/excuse-requests`

|                  |                                                                                                                |
| ---------------- | -------------------------------------------------------------------------------------------------------------- |
| **Query**        | `?page=1&size=20`                                                                                              |
| **Response 200** | `{ items: [{ id, session_id, course_code, status, reason, requested_at, reviewed_at?, review_notes? }], ... }` |

#### `GET /student/excuse-requests/{rid}`

|                  |                            |
| ---------------- | -------------------------- |
| **Response 200** | Full excuse request detail |

---

### Face Embedding

#### `GET /student/me/face-embedding`

Pull face embedding (version-gated, D29).

|                  |                                                                                                                    |
| ---------------- | ------------------------------------------------------------------------------------------------------------------ |
| **Query**        | `?current_version=0`                                                                                               |
| **Response 200** | `{ version: int, embedding: string (base64-encoded encrypted blob) }` — only if `current_version < server_version` |
| **Response 204** | No content (version matches, no update needed)                                                                     |

---

### Profile & Settings

#### `GET /student/profile`

Read-only identity fields.

|                  |                                                                                                                                          |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| **Response 200** | `{ student_number, first_name, middle_name, last_name, email, program_code, year_level_label, section, is_active, face_enrolled: bool }` |

#### `PATCH /student/profile/password`

Same contract as professor password change.

---

## SHARED Auth Endpoints

Existing claim-based registration, MFA, and forgot-password flows are unchanged from current implementation. Documented here for completeness:

| Method | Path                    | Purpose                        |
| ------ | ----------------------- | ------------------------------ |
| POST   | `/auth/register`        | Claim-based registration (OTP) |
| POST   | `/auth/login`           | Email/password login           |
| POST   | `/auth/otp/verify`      | Verify OTP code                |
| POST   | `/auth/forgot-password` | Request password reset         |
| POST   | `/auth/reset-password`  | Reset with token               |
| POST   | `/auth/mfa/setup`       | Generate TOTP secret           |
| POST   | `/auth/mfa/verify`      | Verify TOTP code               |
| GET    | `/auth/me`              | Current user info              |

---

## Appendix: Decision ID Cross-Reference

| Contract Element                                    | Decision(s)        |
| --------------------------------------------------- | ------------------ |
| Session QR payload schema                           | D18                |
| `expires_at` = `min(created_at+duration, scheduled_end)`   | D12, D49           |
| Present/Late window validation `P+L ≤ D`            | D13                |
| Offline `scanned_at` validation → `session_expired` | D16                |
| Excuse state machine paths                          | D20, D21, D22, D23 |
| Bulk excuse-all                                     | D23                |
| Face enrollment 3-photo endpoint                    | D28, D43           |
| Embedding version-gated pull                        | D29                |
| Student profile read-only                           | D32                |
| Analytics cascading filters                         | D33, D34           |
| At-risk refresh endpoint                            | D35                |
| Compliance vs Participation rates                   | D36                |
| Professor reports All Courses aggregate             | D37                |
| Backup trigger endpoint                             | D39                |
| Academic structure audit log                        | D38                |
