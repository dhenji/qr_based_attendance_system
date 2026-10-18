# API Contracts — QR Attendance System

> Canonical reference for every endpoint. Each entry: method, path, role guard,
> request schema, response schema, error codes.

---

## Conventions

| Aspect      | Standard                                                                                    |
| ----------- | ------------------------------------------------------------------------------------------- |
| Base path   | Every path below is relative to `/api`. Each `APIRouter` bakes its own `/…` prefix; `api/router.py` mounts them under `/api` with no additional prefix, so a row reading `/student/dashboard` is live at `/api/student/dashboard`. `GET /health` is the one exception: it is registered on the app itself, outside the namespace. |
| Auth        | `Authorization: Bearer <JWT>` header on all `/admin/*`, `/professor/*`, `/student/*` routes |
| Role guards | FastAPI `Depends(require_role(Role.admin))` etc. 403 on mismatch                            |
| Pagination  | `?page=1&size=20` → `{ items: [...], total: int, page: int, size: int }`                    |
| Error shape | `{ detail: { code: string, message: string, field?: string } }`                             |
| Idempotency | Scan submit accepts `X-Idempotency-Key` header; duplicate returns prior result              |
| Timestamps  | ISO-8601 UTC (`2026-08-25T14:30:00Z`)                                                       |
| Soft-delete | `DELETE` endpoints archive (set `is_active=false`) unless stated destructive               |

### Error Code Coverage

Every code below appears in the `**Errors**` row (or summary-table column) of each
endpoint that can return it, so this section no longer tracks an outstanding list —
it records the exceptions to that rule instead. `src/tests/test_contract_error_codes.py`
asserts the two sets agree, so the coverage cannot silently regress.

**Attribution was traced, not guessed.** Each code was mapped by following its
`raise` site to the enclosing service method and then to the router functions that
call it. Three consequences worth knowing:

- **Some codes are deliberately absent from an endpoint they can reach.** A 404 on
  a path parameter whose foreign key is `RESTRICT` cannot be triggered by a client —
  the row that would dangle cannot exist. Those are omitted rather than listed and
  then never seen.
- **A few codes are conditional on the request body.** `roster_link_impossible`
  fires on `POST /admin/users` only for `student`/`professor` roles;
  `offering_not_found` reaches `PATCH /admin/professors/{professor_id}` only when
  the payload carries `courses`.
- **Three codes are shared by two exception classes on purpose.**
  `storage_unconfigured` is 503 from both `shared/storage.py` (upload, and the
  backup download which re-raises) and `features/system` (backup create, academic
  structure export). `student_not_found` is raised by both the student and excuse
  slices with an identical envelope. `duplicate_scan` sets no `status_code` of its
  own and inherits 409 through `SessionDatabaseException → DatabaseException`, as
  does `year_level_program_mismatch` inheriting 422 via `DomainException`.

**Six codes are defined but unreachable**, so no endpoint row can list them:

| Code | Why it cannot occur |
| ---- | ------------------- |
| `internal_error` | The default `code` on `AppException` and the fallback in `main.py`'s single handler, but no code constructs a code-less `AppException`. An unhandled non-`AppException` (a SQLAlchemy `IntegrityError`, say) escapes to FastAPI's plain-text 500 instead. |
| `database_error` | `DatabaseException` has a 409 handler but no `raise` site anywhere. |
| `face_not_enrolled` | `FaceNotEnrolledException` is never raised. |
| `invalid_semester` | `InvalidSemesterException` is never raised; `semester` is a free-text column with no vocabulary. |
| `role_mismatch` | `RoleMismatchException` is never raised; `require_role` returns an `HTTPException` with `insufficient_permissions` (403). |
| `password_policy_violation` | `PasswordPolicyException` is never raised. New passwords *are* strength-checked, but through a Pydantic `password_strength` validator that fails as the generic 422 `validation_error` — so the custom code can never be emitted and was removed from the change-password row rather than left implying otherwise. |

They are kept rather than deleted because each is a plausible future guard, and an
unused exception class is not a defect. If one is ever raised, the guard test fails
and the row gets added.

Conversely, `no_face_detected`, `multiple_faces`, `quality_too_low` and `invalid_image`
are documented below but not yet raised: face detection is stubbed by
`_stub_embedding_blob` pending the MediaPipe pipeline. `validation_error` is the
generic 422 produced by FastAPI request validation, not a custom exception.

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
`lw` → `late_window_minutes`. The `radius:30` sample above is illustrative —
`sessions.classroom_radius_meters` defaults to **50 m**.

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

## Infrastructure

### Health

#### `GET /health`

Liveness probe. Registered on the app itself in `main.py`, so it sits **outside**
the `/api` namespace and takes no bearer token — it is what a load balancer or
`docker compose` healthcheck hits.

|                  |                                  |
| ---------------- | -------------------------------- |
| **Auth**         | None                             |
| **Response 200** | `{ status: "ok" }`               |

It reports process liveness only. It does **not** touch the database: the
startup `SELECT 1` in the lifespan is what fails the boot when Postgres is
unreachable, so a running process answering here is not evidence the database is
reachable.

---

## ADMIN Endpoints

### Programs

#### `GET /admin/programs`

List all programs (with year-level counts).

|                  |                                                                                                                   |
| ---------------- | ----------------------------------------------------------------------------------------------------------------- |
| **Role**         | admin                                                                                                             |
| **Query**        | `?search=&is_active=true&page=1&size=20`                                                                          |
| **Response 200** | `{ items: [{ id, code, name, description, total_years, is_active, course_count, year_level_count, terms_count, created_at, updated_at }], total, page, size }` |
| **Notes**        | `course_count`/`year_level_count`/`terms_count` are aggregate DTOs for the Programs table (wireframes.md 4.5a: Years / Terms / Courses columns). |
|                  | `search` is optional and matches `code` or `name` case-insensitively (wireframes 4.5a search box).                 |
|                  | All three aggregates are **derived per request**, not stored columns: `year_level_count` = rows in `year_levels`, `terms_count` = `sum(len(term_structure["terms"]))`, and `course_count` = `COUNT(DISTINCT course_offerings.course_id)` over that program's active offerings — `courses` carries no `program_id` (D44), so offerings are the only path. |

#### `POST /admin/programs`

Create a new program.

|                  |                                                                                         |
| ---------------- | --------------------------------------------------------------------------------------- |
| **Role**         | admin                                                                                   |
| **Request**      | `{ code: string, name: string, description?: string, total_years: int }`                |
| **Response 201** | `{ id, code, name, description, total_years, is_active: true, created_at, updated_at }` |
| **Errors**       | 409 `program_code_exists` · 422 validation                                              |

#### `GET /admin/programs/{program_id}`

|                  |                                                |
| ---------------- | ---------------------------------------------- |
| **Response 200** | Program object with nested `year_levels` array |

#### `PATCH /admin/programs/{program_id}`

|                  |                                       |
| ---------------- | ------------------------------------- |
| **Request**      | `{ name?, description?, is_active? }` |
| **Response 200** | Updated program                       |

#### `DELETE /admin/programs/{program_id}`

Permanent delete — allowed only on archived (`is_active=false`) programs with
no dependents. Archive via `PATCH` the same row with `is_active: false`;
reactivate with `is_active: true`.

|                  |            |
| ---------------- | ---------- |
| **Response 204** | No content |
| **Errors**       | 409 `not_archived` (record is still `is_active=true`)<br>409 `program_has_offerings` (`course_offerings` still reference this program)<br>409 `program_has_students` (students are still enrolled under this program's year levels)<br>404 `program_not_found` |
| **Notes**        | Empty year levels cascade (`delete-orphan`); the guards above run first so the `RESTRICT` FKs on `course_offerings.program_id` and `students.year_level_id` can never surface as a 500. One `delete` audit row on `program` per hard delete. |

---

### Year Levels

#### `GET /admin/programs/{program_id}/years`

|                  |                                                                                        |
| ---------------- | -------------------------------------------------------------------------------------- |
| **Response 200** | `{ items: [{ id, program_id, year_number, label, term_structure, sort_order }], ... }` |

#### `POST /admin/programs/{program_id}/years`

|                  |                                                                                     |
| ---------------- | ----------------------------------------------------------------------------------- |
| **Request**      | `{ year_number: int, label: string, term_structure: { terms: [{ code, label, weeks?: int }] } }` |
| **Response 201** | Created year level                                                                  |

| **Errors**       | 409 `year_number_exists` |

| **Notes**        | `year_number` is unique per program, but there is deliberately no `year_number <= program.total_years` check — the `1..total_years` bound is enforced only by the Programs UI and Setup Wizard year pickers (frontend-only). Empty `terms: []` is accepted; the Setup Wizard treats termless years as unusable for offerings (frontend-only), while the API accepts an offering on a termless year with a free-text `semester`. `terms[].weeks` is the term's session length (D86), optional `1..52`, stored in the JSONB `term_structure`; offerings offered in that term derive their `semester_weeks` from it (missing → 18). |
#### `GET /admin/programs/{program_id}/years/{year_id}`

|                  |                                                               |
| ---------------- | ------------------------------------------------------------- |
| **Response 200** | `{ id, program_id, year_number, label, term_structure, sort_order }` |
| **Errors**       | 404 `program_not_found` / `year_level_not_found`                  |

#### `PATCH /admin/programs/{program_id}/years/{year_id}`

|                  |                                            |
| ---------------- | ------------------------------------------ |
| **Request**      | `{ label?, term_structure?, sort_order? }` |
| **Response 200** | Updated year level                         |

| **Errors**       | 404 `year_level_not_found` · 409 `term_code_in_use` |
#### `DELETE /admin/programs/{program_id}/years/{year_id}`

Archive year level. Restrict if courses exist.

|                  |                        |
| ---------------- | ---------------------- |
| **Response 204** | No content             |
| **Errors**       | 409 `year_has_courses` · 404 `year_level_not_found` |

---

### Courses

A course is a standalone reusable **template** (D44) — it carries no program, year-level, scheduling, or classroom fields. Program/year-specific instances are `CourseOfferings` (next section). It also carries no lecture/laboratory type (D77): the distinction lives on sessions (`session_type`) and offering components, so one course can mix both. `units` are the required scheduled meeting hours per week across an offering's active components (D79); `session_duration_hours` is the default session length — the ceiling for `present + late` windows and the fallback `duration_minutes` when a professor opens a session without an override.

#### `GET /admin/courses`

|                  |                                                                                                              |
| ---------------- | ------------------------------------------------------------------------------------------------------------ |
| **Query**        | `?is_active?&page=1&size=20`                                                                                  |
| **Response 200** | `{ items: [{ id, course_code, course_name, units, session_duration_hours, is_active, created_at, updated_at }], ... }` |

#### `POST /admin/courses`

|                  |                                                                                                              |
| ---------------- | ------------------------------------------------------------------------------------------------------------ |
| **Request**      | `{ course_code: string, course_name: string, units: int, session_duration_hours: numeric(3,1) }`            |
| **Response 201** | Created course template                                                                                      |
| **Errors**       | 409 `course_code_exists` · 422 validation                                                                    |

#### `GET /admin/courses/{course_id}`

|                  |                                              |
| ---------------- | -------------------------------------------- |
| **Response 200** | Full course template                         |

#### `PATCH /admin/courses/{course_id}`

|                  |                             |
| ---------------- | --------------------------- |
| **Request**      | Any mutable template field from POST |
| **Response 200** | Updated course template              |

#### `DELETE /admin/courses/{course_id}`

Permanent delete — allowed only on archived (`is_active=false`) courses with
no dependents. Archive via `PATCH` the same row with `is_active: false`;
reactivate with `is_active: true`.

|                  |            |
| ---------------- | ---------- |
| **Response 204** | No content |
| **Errors**       | 409 `not_archived` (record is still `is_active=true`)<br>409 `course_has_offerings` (`course_offerings` still reference this course)<br>404 `course_not_found` |
| **Notes**        | The guard runs first so the `RESTRICT` FK on `course_offerings.course_id` can never surface as a 500. One `delete` audit row on `course` per hard delete. |

---

### Course Offerings

A course offering is a specific instance of a course template for a program, year level, and semester. It holds scheduling, classroom, and window configuration. Per-type schedules live on **offering components** (D77): an offering with one component behaves like before, while a mixed course carries e.g. a laboratory component on Monday plus a lecture component on Wednesday, each with its own days/times/room.

#### `GET /admin/offerings`

|                  |                                                                                                                                                                                                                          |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Query**        | `?program_id?&year_level_id?&semester?&course_id?&is_active?&page=1&size=20`                                                                                                                                             |
| **Response 200** | `{ items: [{ id, course_id, program_id, year_level_id, semester, academic_year, sessions_per_week, semester_weeks, schedule_days, schedule_start_time, schedule_end_time, classroom_name, classroom_lat, classroom_lng, default_present_window_minutes, default_late_window_minutes, enrolled_count, session_types: ["lecture" \| "lab"], components: [Component], is_active, created_at, updated_at }], ... }` |
| **Notes**        | `enrolled_count` is a computed DTO (count of active enrollments) — feeds the course/offering tables (wireframes.md 4.5c/4.5d) and the active-session "Enrolled" stat. `session_types` lists the distinct types across the offering's active components and feeds the Lecture / Lab / Mixed badges. `Component = { id, offering_id, session_type, schedule_days, schedule_start_time, schedule_end_time, classroom_name, classroom_lat, classroom_lng, is_active, created_at, updated_at }`. `semester_weeks` is **derived, read-only** (D86): resolved from the offering's year-level term entry for its `semester` via `shared/schedule.py::term_weeks`, falling back to `DEFAULT_TERM_WEEKS` (18) for an unmatched/orphaned code. It is not accepted on create/update. |

#### `POST /admin/offerings`

|                  |                                                                                                                                                                                                                                                                    |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Request**      | `{ course_id: int, program_id: int, year_level_id: int, semester: string, academic_year: string, sessions_per_week: int, schedule_days: string, schedule_start_time: time, schedule_end_time: time, classroom_name?: string, classroom_lat?: numeric, classroom_lng?: numeric, default_present_window_minutes?: int, default_late_window_minutes?: int, components?: [{ session_type, schedule_days, schedule_start_time, schedule_end_time, classroom_name?, classroom_lat?, classroom_lng? }] }` |
| **Response 201** | Created course offering (with `components` + `session_types`)                                                                                                                                                                                                                                             |
| **Errors**       | 409 `offering_exists` · 409 `component_exists` · 404 `course_not_found` · 404 `program_not_found` · 422 `windows_exceed_duration` · 422 `weekly_hours_exceed_units` · 422 `weekly_hours_below_units` · 404 `year_level_not_found` |
| **Notes**        | Omitting `components` creates a single lecture component mirroring the offering schedule/classroom, so pre-existing callers keep working unchanged. |
|                  | Uniqueness is `(course_id, program_id, semester, academic_year)` — `year_level_id` is **not** part of the key, so the same course/program/term/year on a different year level still 409s. On 409 `offering_exists` the admin UI looks the conflicting offering up and links straight to it (it may sit under a different year level than the one filtered). `semester` is free text with no vocabulary (`invalid_semester` is defined but unreachable); the year-terms dropdowns in the Offerings page and Setup Wizard are the only entry path (UI guidance only — free-text entry is not offered). The Setup Wizard builds the same meeting rows (up to 4) as the Offerings page modal; further meetings are added via `POST …/components` afterwards. A new offering still needs a professor assignment (`POST …/professors`) and enrollment before sessions can run. |
|                  | Scheduling model: one row per meeting (type + days + time + room) stored as offering components (the create forms allow up to 7 rows); the offering-level schedule columns are display default + session pre-fill only. A multi-day meeting (e.g. MWF 08:00–09:00) is stored as a single component with a day-letter string — never fanned out into one row per day — so a time change stays atomic across its days. `sessions_per_week` is derived server-side as one session per meeting day (an `MWF` row counts 3) and re-synced on every component write; the create payload value is recomputed, and the detail Settings tab shows it read-only. The term total shown is `sessions_per_week × semester_weeks`, where `semester_weeks` is the term's value (D86) — the same product the risk batch uses as its expected count. Same-day overlaps are permitted server-side (the UI warns); only one session per offering can be active at a time. Weekly scheduled hours are Σ meeting durations × day-letter counts and must equal the course's `units` (D79): a 3-unit course holds Mon 07:00–08:30 + Tue 13:00–14:30 (3.0h) but rejects Mon 07:00–08:30 + Tue 13:00–15:00 (3.5h, 422 `weekly_hours_exceed_units`) and a lone Mon 07:00–08:30 (1.5h, 422 `weekly_hours_below_units`). Creation must land exactly; adds (and reactivations) may only converge — strictly closer without crossing sides — while plain meeting edits reshape freely so multi-step changes can pass through mismatched totals (D81). |

#### `GET /admin/offerings/{offering_id}`

|                  |                                                                                  |
| ---------------- | -------------------------------------------------------------------------------- |
| **Response 200** | Course offering (with `components` + `session_types`, as in the list) |

| **Errors**       | 404 `offering_not_found` |

#### `GET /admin/offerings/{offering_id}/components`

List the offering's active scheduled components, oldest first.

|                  |                                                        |
| ---------------- | ------------------------------------------------------ |
| **Response 200** | `[Component]` (bare array, like the professors list)   |

| **Errors**       | 404 `offering_not_found` |

#### `POST /admin/offerings/{offering_id}/components`

Add a scheduled component (lecture/lab) to an offering.

|                  |                                                                                                                              |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| **Request**      | `{ session_type: "lecture" \| "lab", schedule_days: string, schedule_start_time: time, schedule_end_time: time, classroom_name?: string, classroom_lat?: numeric, classroom_lng?: numeric }` |
| **Response 201** | Created component                                                                                                            |

| **Errors**       | 404 `offering_not_found` · 409 `component_exists` · 422 `weekly_hours_exceed_units` · 422 `weekly_hours_below_units` |

| **Notes**        | When the change leaves exactly one active component, its schedule/room is mirrored onto the offering columns (the legacy display default and session fallback); with zero or several, the offering columns are left untouched. An add must meet the course's `units` (D79) or converge toward them; reactivating an archived component revalidates the same way. Plain meeting edits reshape freely (D81). |

#### `PATCH /admin/offerings/{offering_id}/components/{component_id}`

|                  |                                                                          |
| ---------------- | ------------------------------------------------------------------------ |
| **Request**      | Any mutable component field (`schedule_days`, `schedule_start/end_time`, `classroom_*`, `is_active`) |
| **Response 200** | Updated component                                                        |

| **Errors**       | 404 `offering_not_found` · 404 `component_not_found` · 422 `invalid_schedule_window` · 422 `weekly_hours_exceed_units` · 422 `weekly_hours_below_units` |

#### `DELETE /admin/offerings/{offering_id}/components/{component_id}`

Archive a scheduled component (soft-delete: `is_active=false`).

|                  |            |
| ---------------- | ---------- |
| **Response 204** | No content |

| **Errors**       | 404 `offering_not_found` · 404 `component_not_found` |
#### `PATCH /admin/offerings/{offering_id}`

|                  |                                                |
| ---------------- | ---------------------------------------------- |
| **Request**      | Any mutable field from POST (except course_id, program_id, year_level_id, semester, academic_year) |
| **Response 200** | Updated course offering                        |
| **Errors**       | 404 `offering_not_found` · 422 `invalid_schedule_window` · 422 `schedule_mismatch` |
| **Notes**        | `invalid_schedule_window` is 422 when the *merged* result would end at or before it starts. A PATCH that moves only `schedule_start_time` past the stored end is caught here, because the request body's own validator only sees the fields it was sent. Activation (`is_active` False → True) additionally requires the merged meeting total to equal the course units requirement exactly, including the zero-meeting case — 422 `schedule_mismatch` otherwise; deactivation and unrelated PATCHes are unaffected. |

#### `DELETE /admin/offerings/{offering_id}`

Permanent delete — allowed only on archived (`is_active=false`) offerings with
no dependents. Archive via `PATCH` the same row with `is_active: false`;
reactivate with `is_active: true`.

|                  |            |
| ---------------- | ---------- |
| **Response 204** | No content |

| **Errors**       | 409 `not_archived` (record is still `is_active=true`)<br>409 `offering_has_enrollments` (students are still enrolled)<br>409 `offering_has_sessions` (sessions were already opened — history is kept)<br>409 `offering_has_assignments` (professor assignments still reference it, including ended ones)<br>404 `offering_not_found` |
| **Notes**        | Guards run in FK order (enrollments → sessions → assignments) so a `RESTRICT` violation can never surface as a 500. Components are owned by the offering and are removed with it once the guards pass. One `delete` audit row on `course_offering` per hard delete. |
#### `GET /admin/offerings/{offering_id}/professors`

|                  |                                                                                                                               |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| **Response 200** | `[{ offering_id, professor_id, is_primary, effective_from, effective_to, semester, assigned_by, assigned_at }]` — a bare array, **not** `{ items: […] }`. The only non-paginated list in the app, so the row is outside the `?page/?size` convention. |

| **Errors**       | 404 `offering_not_found` |
#### `POST /admin/offerings/{offering_id}/professors`

Assign professor to course offering.

|                  |                                                                                                        |
| ---------------- | ------------------------------------------------------------------------------------------------------ |
| **Request**      | `{ professor_id: int, is_primary: bool, effective_from: date, effective_to?: date, semester: string }` |
| **Response 201** | Created assignment                                                                                     |
| **Errors**       | 409 `overlapping_assignment` · 404 `professor_not_found` · 404 `offering_not_found` |

#### `DELETE /admin/offerings/{offering_id}/professors/{professor_id}`

End assignment (set `effective_to` = today).

|                  |                                  |
| ---------------- | -------------------------------- |
| **Response 200** | `{ effective_to: "YYYY-MM-DD" }` |
| **Errors**       | 404 `assignment_not_found` · 404 `offering_not_found` |

#### `POST /admin/offerings/{offering_id}/enrollments/bulk`

Bulk-enroll EXISTING students via CSV upload (wireframes.md 4.3 template; creating
new roster students is `POST /admin/students/import`).

|                  |                                                               |
| ---------------- | ------------------------------------------------------------- |
| **Request**      | `multipart/form-data: file=students.csv`                      |
| **CSV columns**  | `student_id, first_name, middle_name, last_name, email, program_code, year_level, section` |
| **Response 201** | `{ enrolled: int, skipped: int, errors: [{ line, reason }] }` |
| **Errors**       | 422 `validation_error` · 404 `offering_not_found` |

#### `DELETE /admin/offerings/{offering_id}/students/{student_number}`

Unenroll one student (wireframes.md 4.5d Enrolled tab Remove action). Deletes
the enrollment link row only — past attendance rows keep their
student+session identity, and future scans are blocked by the live
enrollment check. No attendance guard and no `is_active` gate (ADR-076).

|                  |                                                                                  |
| ---------------- | -------------------------------------------------------------------------------- |
| **Response 204** | No content                                                                       |
| **Errors**       | 404 `offering_not_found` · 404 `student_not_found` · 404 `enrollment_not_found` |

#### `GET /admin/offerings/{offering_id}/students`

Offering roster read (wireframes.md 4.5d Enrolled tab; drives the D2 `section`
filters on professor screens and the active-session "Enrolled" count).

|                  |                                                                   |
| ---------------- | ----------------------------------------------------------------- |
| **Query**        | `?section?&page=1&size=20`                                        |
| **Response 200** | `{ items: [{ student_id, name, section, enrolled_at }], total, page, size }` |

---

| **Errors**       | 404 `offering_not_found` |
### Face Enrollment

#### `POST /admin/face-enrollment/{student_id}`

Upload 3 photos (front, left, right) for face embedding generation.

|                  |                                                                                             |
| ---------------- | ------------------------------------------------------------------------------------------- |
| **Request**      | `multipart/form-data: front=Image, left=Image, right=Image`                                 |
| **Response 201** | `{ student_id, face_enrolled_at, face_embedding_version: int }`                             |
| **Errors**       | 400 `invalid_image` · 400 `no_face_detected` · 400 `multiple_faces` · 422 `quality_too_low` · 404 `student_not_found` |

#### `GET /admin/face-enrollment/{student_id}`

Check enrollment status.

|                  |                                                                  |
| ---------------- | ---------------------------------------------------------------- |
| **Response 200** | `{ enrolled: bool, face_enrolled_at?, face_embedding_version? }` |

---

| **Errors**       | 404 `student_not_found` |
### Analytics

#### `GET /admin/analytics/overview`

|                  |                                                                                                  |
| ---------------- | ------------------------------------------------------------------------------------------------ |
| **Role**         | admin                                                                                            |
| **Query**        | `?program_id?&year_level_id?&semester?&course_ids?&date_from?&date_to?`                          |
| **Response 200** | `{ total_students, total_courses, avg_compliance_rate, avg_participation_rate, total_sessions }` |

#### `GET /admin/analytics/course-options`

Courses with **at least one offering in the selected scope** — the Analytics
filter rail's course picker. Uses the same scope predicate as every report
read, so a course no report can show in the picked Program/Year/Term cannot
be offered as an option; a course with no offering can never produce a
silently empty report. No `is_active` gate (mirrors the report reads). `q`
matches course code or name; `total` lets the picker flag truncation
honestly instead of silently capping.

|                  |                                                               |
| ---------------- | ------------------------------------------------------------- |
| **Role**         | admin                                                         |
| **Query**        | `?program_id?&year_level_id?&semester?&q?&limit?`             |
| **Response 200** | `{ items: [{ course_id, course_code, course_name }], total }` |

#### `GET /admin/analytics/course-comparison`

One item per **(course, program, year level)** cohort: the same subject offered
to two programs/year levels is two rows, not one blended row (D6/D34).
Semester/dates are filter axes, not identity.

|                  |                                                                                                                                |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| **Query**        | `?program_id?&year_level_id?&semester?&course_ids?&date_from?&date_to?&page?&size?`                                            |
| **Response 200** | `{ items: [{ course_id, course_code, program_id, year_level_id, compliance_rate, participation_rate, total_sessions }], total, page, size }` |

#### `GET /admin/analytics/trends`

|                  |                                                                                   |
| ---------------- | --------------------------------------------------------------------------------- |
| **Query**        | `?program_id?&year_level_id?&semester?&course_ids?&granularity=daily              | weekly | monthly&date_from?&date_to?` |
| **Response 200** | `{ items: [{ date, compliance_rate, participation_rate, total_sessions }], ... }` |

#### `GET /admin/analytics/at-risk`

|                  |                                                                                                                                                               |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Query**        | `?program_id?&year_level_id?&semester?&course_ids?&risk_level=low                                                                                             | medium | high` |
| **Response 200** | `{ items: [{ student_id, student_name, program, year_level, offering_id, course_code, course_name, absence_rate, max_streak, trend_slope, risk_level, computed_at }], ... }` |

#### `POST /admin/analytics/export`

Export analytics as CSV/PDF.

|                  |                            |
| ---------------- | -------------------------- |
| **Request**      | `{ format: "csv", program_id?, year_level_id?, semester?, course_ids?, date_from?, date_to? }` |
| **Response 200** | File download (CSV) |
| **Errors**       | 422 `unsupported_export_format` for any format other than `csv` |

#### `POST /admin/analytics/refresh-risk`

Trigger manual risk-score recalculation (admin-only). Synchronous and scoped —
no async job. Rate-limited to 1 call per 60 seconds per admin.

|                  |                                                          |
| ---------------- | -------------------------------------------------------- |
| **Query**        | `student_id?` `offering_id?` `semester?` (all optional)  |
| **Response 200** | `{ processed: N, high: X, medium: Y, low: Z, duration_ms: T }` |
| **Notes**        | No filter = run the full batch. `student_id` refreshes one student across their offerings; `offering_id` refreshes all students in a course offering (`semester` required when `offering_id` is set). Sourced from `risk-model.md` §6. When `RISK_BATCH_DRY_RUN=true`, results are staged instead of going live (see `risk-staging` below). |

#### `GET /admin/analytics/risk-staging`

Review staged dry-run risk scores before promoting them to live scores (admin-only).
Staging is populated by the risk batch / `refresh-risk` while `RISK_BATCH_DRY_RUN=true`;
live `student_risk_scores` are untouched until `promote`.

|                  |                                                                                                                                                               |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Role**         | admin                                                                                                                                                         |
| **Query**        | `?program_id?&year_level_id?&semester?&course_ids?&risk_level=low                                                                                             | medium | high&unpromoted_only=false&...` |
| **Response 200** | `{ items: [{ student_id, student_name, program, year_level, offering_id, course_code, course_name, absence_rate, max_streak, trend_slope, risk_level, computed_at, promoted_at }], ... }` |

#### `POST /admin/analytics/risk-staging/promote`

Copy unpromoted staged rows into live `student_risk_scores` (UPSERT per student/offering/semester/day)
and stamp them `promoted_at` (admin-only). Already-promoted rows in scope are counted as `skipped`.

|                  |                                                                                        |
| ---------------- | -------------------------------------------------------------------------------------- |
| **Role**         | admin                                                                                  |
| **Query**        | `student_id?` `offering_id?` `semester?` `program_id?` `year_level_id?` `course_ids?`   |
| **Response 200** | `{ promoted: N, skipped: M, duration_ms: T }`                                          |
| **Notes**        | No filter = promote all unpromoted rows. `semester` required when `offering_id` is set. Program/year/course scope the promoted set to match the review list (issue #279); risk level and paging remain list-only. Re-promoting with no fresh dry-run yields `{ promoted: 0, ... }`. |

---

### System Settings & Backups

#### `GET /admin/system/settings`

|                  |                                                                                                                                   |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| **Response 200** | `{ geofence_default_radius, present_window_default, late_window_default, backup_retention_daily, backup_retention_monthly, pending_sync_count, ... }` |
| **Notes**        | Persisted in the `app_settings` key-value table (seeded from env defaults at startup) — PATCH writes rows, no in-memory-only updates. `pending_sync_count` is an unprocessed `sync_queue` row count for the maintenance line (wireframes.md 4.9 "Pending sync: N"). |

#### `PATCH /admin/system/settings`

|                  |                         |
| ---------------- | ----------------------- |
| **Request**      | Partial settings object |
| **Response 200** | Updated settings        |

#### `GET /admin/system/academic-structure`

List structural changes (audit log for program/year/course mutations).

|                  |                                                                                                                                                                                                                     |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Query**        | `?page=1&size=20`                                                                                                                                                                                                      |
| **Response 200** | `{ items: [{ id, action, entity_type, entity_id, old_value, new_value, performed_by, performed_at }], ... }`                                                                                                              |
| **Notes**        | Admin-only. `entity_type` is one of `program`, `year_level`, `course`, `course_offering`; assignment/enrollment changes are audited separately and surface on `GET /admin/audit-logs`. `old_value`/`new_value` are JSON snapshots, null on create/delete respectively. |

| **Errors**       | 503 `storage_unconfigured` |
#### `GET /admin/audit-logs`

The full audit trail — every sensitive mutation, not just the structural ones.

|                  |                                                                                                                                        |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| **Query**        | `?entity_type=&action=&performed_by=&date_from=&date_to=&page=1&size=20`                                                                 |
| **Response 200** | `{ items: [{ id, action, entity_type, entity_id, old_value, new_value, performed_by, performed_at }], total, page, size }`              |
| **Notes**        | Admin-only. Filters AND-combine and are each optional; a blank value (`?action=`) means "no filter". `date_from` is inclusive from 00:00 UTC, `date_to` inclusive to the end of that day, so `date_from == date_to` selects one day. |

**Vocabulary.** `entity_type` is one of `program`, `year_level`, `course`,
`course_offering`, `student`, `professor`, `enrollment`, `course_professor`,
`excuse`, `session`, `face_enrollment`, `attendance_record`, `backup`,
`app_setting`, `user`, `maintenance` (aggregate subject of the sync-flush and
cleanup runs, one audit row per run with counts in `new_value`). `action` is one of `create`, `update`, `archive`,
`delete`, `import`, `enroll`, `assign`, `unassign`, `open`, `close`, `approve`,
`reject`, `revoke`, `lock`, `unlock`, `login_failed`, `password_reset`. A value
outside either list is **422 `invalid_audit_filter`** rather than an empty page,
so a mistyped filter can never read as "nothing happened". An inverted range is
**422 `invalid_audit_date_range`**.

**`entity_id` is nullable.** It is null for `course_professor` (composite
primary key, so there is no single-column id), for the `app_setting` rows a
PATCH writes, and for the aggregate `import` / `enroll` rows that describe a
batch. Those rows are identified by `old_value`/`new_value` instead.

**`performed_by` is nullable.** It is null when nobody was authenticated: a
lockout or failed login triggered by an anonymous attempt, or the nightly cron.
The subject is still `entity_type` + `entity_id`.

#### `GET /admin/backups`

|                  |                                                                                                          |
| ---------------- | -------------------------------------------------------------------------------------------------------- |
| **Response 200** | `{ items: [{ id, filename, kind, size_bytes, storage_backend, started_at, finished_at, status }], ... }` |

#### `POST /admin/backups`

Trigger a full backup.

|                  |                                   |
| ---------------- | --------------------------------- |
| **Response 202** | `{ backup_id, status: "started" }` |

| **Errors**       | 503 `storage_unconfigured` · 409 `backup_in_progress` · 500 `backup_failed` |
#### `GET /admin/backups/{backup_id}/download`

Download backup file.

|                  |                      |
| ---------------- | -------------------- |
| **Response 200** | Binary file download |

| **Errors**       | 503 `storage_unconfigured` · 404 `backup_not_found` |
#### `POST /admin/system/sync/flush`

Reconcile pending `sync_queue` rows now. Each queued entry mirrors a scan
that already landed in `attendance_records` — the payload carries ids only,
no scan evidence, so the run confirms each entry against the row it names
rather than resubmitting the scan: id match on both sides marks the entry
`done`, anything else (orphan, mismatch, unparseable payload) marks it
`failed` with another retry counted. One bad entry never aborts the run.
Refuses to start while a maintenance run, backup, or scheduled batch is
active (**409 `maintenance_in_progress`**). Audited as one aggregate row
(`action: update`, `entity_type: maintenance`).

|                  |                                    |
| ---------------- | ---------------------------------- |
| **Response 200** | `{ processed, succeeded, failed }` |

#### `POST /admin/system/cleanup`

Prune expired data: OTP codes older than 7 days and finished (`done` /
`failed`) `sync_queue` rows older than 30 days, both measured on
`created_at`. Pending queue rows are never touched no matter their age.
Refuses to start while a maintenance run, backup, or scheduled batch is
active (**409 `maintenance_in_progress`**). Audited as one aggregate row
(`action: delete`, `entity_type: maintenance`, per-table counts in
`new_value`).

|                  |                  |
| ---------------- | ---------------- |
| **Response 200** | `{ removed }`    |

---

### Excuses (Admin View)

#### `GET /admin/excuses`

List pending excuse requests.

|                  |                                                 |
| ---------------- | ----------------------------------------------- |
| **Query**        | `?status=pending                                | approved | rejected&page=1&size=20` |
| **Response 200** | `{ items: [ExcuseRequest], total, page, size }` |

---

### Attendance Overview

#### `GET /admin/attendance/overview`

Per-course attendance overview (wireframes.md 4.6). Backs the **Attendance**
tab of Analytics & Reports (`/admin/analytics?tab=attendance`) and the
dashboard's "Attendance at a glance" strip. See ADR-083.

|                  |                                                                                          |
| ---------------- | ---------------------------------------------------------------------------------------- |
| **Query**        | `?course_id?&professor_id?&date_from?&date_to?`                                          |
| **Response 200** | `{ items: [{ course_id, course_code, course_name, sessions_count, avg_rate, trend }] }`  `trend: "up" \| "down" \| "flat"` |

#### `GET /admin/attendance/overview/export`

CSV export of the current overview filter set (wireframes.md 4.6 "Export Overview", Attendance tab).

|                  |                                                                                            |
| ---------------- | ------------------------------------------------------------------------------------------ |
| **Query**        | Same filters as `GET /admin/attendance/overview`                                            |
| **Response 200** | CSV file download (all rows, not just the page)                                            |

#### `GET /admin/attendance/recent-scans`

Latest scans feed for the admin dashboard (wireframes.md 4.1).

|                  |                                                                     |
| ---------------- | ------------------------------------------------------------------- |
| **Query**        | `?limit=10`                                                          |
| **Response 200** | `{ items: [{ id, scanned_at, student_name, course_code, status }] }` |

### Liveness Review

Queue of attendance records flagged for manual review — records whose
`face_match_score` fell in the review band
`[FACE_REVIEW_BAND_LOW, FACE_MATCH_THRESHOLD)` (0.65–0.70) submitted with
`liveness_evidence.review=true` and `validation_status=pending`.

#### `GET /admin/attendance/liveness-review`

List flagged records for manual review.

|                  |                                                                     |
| ---------------- | ------------------------------------------------------------------- |
| **Query**        | `?status=pending                                                    | approved | rejected&page=1&size=20` |
| **Response 200** | `{ items: [{ id, student_number, student_name, session_code, course_code, face_match_score, evidence, scanned_at }], total, page, size }` |
| **Notes**        | `evidence` is the stored `liveness_evidence` JSONB (review flag, EAR/PnP samples). Only `status=pending` records are actionable. |

#### `PATCH /admin/attendance/liveness-review/{record_id}/resolve`

Approve or reject a flagged record.

|                  |                                                                                   |
| ---------------- | --------------------------------------------------------------------------------- |
| **Request**      | `{ decision: "approve" \| "reject", note?: string }`                              |
| **Response 200** | `{ id, status, reviewed_by, reviewed_at }`                                        |
| **Notes**        | `approve` restores the computed present/late status; `reject` sets `rejected`. Both clear `liveness_evidence.review`. `note` (≤1000 chars, stripped) is stored as `liveness_evidence.review_note` and returned by the list endpoint's `evidence`. Resolving an already-resolved record is 409 `review_not_pending`. The decision is also written to the audit trail as `approve` / `reject` on `attendance_record`, visible on `GET /admin/audit-logs`. |

| **Errors**       | 404 `review_not_found` · 409 `review_not_pending` |
### Students, Professors & Archive

#### `POST /admin/students/import`

CSV roster import — creates NEW student records (wireframes.md 4.3).
Columns: `student_id, first_name, middle_name, last_name, email, program_code, section, year_level`.

|                  |                                                                             |
| ---------------- | --------------------------------------------------------------------------- |
| **Request**      | `multipart/form-data` CSV file                                               |
| **Response 200** | `{ imported, duplicates, errors: [{ line, reason }] }`                       |

#### `POST /admin/professors/import`

CSV professor import — creates new records (wireframes.md 4.4).
Columns: `first_name, middle_name, last_name, email, department`.

|                  |                                                              |
| ---------------- | ------------------------------------------------------------ |
| **Request**      | `multipart/form-data` CSV file                                |
| **Response 200** | `{ imported, duplicates, errors: [{ line, reason }] }`        |

#### `GET /admin/students/import/template`

CSV template download for the import screen (wireframes.md 4.3 Step 1).
Columns: `student_id, first_name, middle_name, last_name, email, program_code, section, year_level`.

|                  |                       |
| ---------------- | --------------------- |
| **Response 200** | CSV file download     |

#### `POST /admin/programs/import`

CSV program import — creates NEW program records. Year levels are not
created here; they are added later on the program detail page, matching
single-create semantics.
Columns: `code, name, description, total_years`.

|                  |                                                              |
| ---------------- | ------------------------------------------------------------ |
| **Request**      | `multipart/form-data` CSV file                                |
| **Response 200** | `{ imported, duplicates, errors: [{ line, reason }] }`        |

#### `GET /admin/programs/import/template`

CSV template download for the program import screen.
Columns: `code, name, description, total_years`.

|                  |                       |
| ---------------- | --------------------- |
| **Response 200** | CSV file download     |

#### `POST /admin/courses/import`

CSV course import — creates NEW standalone course templates (D44: no
program, schedule, or classroom linkage; offerings attach later).
Columns: `course_code, course_name, units, session_duration_hours`.

|                  |                                                              |
| ---------------- | ------------------------------------------------------------ |
| **Request**      | `multipart/form-data` CSV file                                |
| **Response 200** | `{ imported, duplicates, errors: [{ line, reason }] }`        |

#### `GET /admin/courses/import/template`

CSV template download for the course import screen.
Columns: `course_code, course_name, units, session_duration_hours`.

|                  |                       |
| ---------------- | --------------------- |
| **Response 200** | CSV file download     |

#### `DELETE /admin/students/{student_id}/archive`

Permanent delete — allowed only on archived (`is_active=false`) students
(wireframes.md 4.10).

|                  |                          |
| ---------------- | ------------------------ |
| **Response 204** | No content               |
| **Errors**       | 409 `not_archived` (record is still `is_active=true`)<br>409 `student_has_records` (enrollments / attendance_records / excuse_requests still reference this student — ADR-057) · 404 `student_not_found` |

> The `is_active` check alone is not sufficient. `enrollments`,
> `attendance_records` and `excuse_requests` all reference `students.id` with
> `ondelete="RESTRICT"`, so a hard delete of any student who has ever enrolled or
> scanned would otherwise raise a foreign-key violation and return 500. The
> has-records guard returns 409 instead. The FKs stay `RESTRICT` on purpose:
> cascading them would silently destroy the attendance audit trail (ADR-057).
> Hard-delete deactivates (never deletes) the linked `users` row, so the audit
> trail stays joinable and a later re-creation can reclaim the login (D71/D72).

#### `DELETE /admin/professors/{professor_id}/archive`

Same semantics as the student archive delete, for professors, including
`409 professor_has_records` when `sessions` still reference the professor
(`course_professors` is CASCADE, `sessions` is RESTRICT). Hard-delete
deactivates (never deletes) the linked login, so the audit trail stays
joinable (D71).

#### `GET /admin/students`

List students with search and filters (wireframes.md 4.2).

|                  |                                                                                                                              |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| **Query**        | `?search?&program_id?&year_level_id?&section?&is_active?&sort_by?&sort_dir?&page=1&size=20`                                  |
| **Response 200** | `{ items: [{ id, student_id, first_name, middle_name, last_name, email, program_code, year_level_label, section, is_active, face_enrolled: bool, created_at, scan_count }], total, page, size }` |
| **Notes**        | `search` matches `student_id`/name/email; `face_enrolled`/`created_at`/`scan_count` feed the roster + profile (wireframes.md 2.10). |

#### `POST /admin/students`

Create a student (wireframes.md 4.2 -> Create Student).

|                  |                                                                                                                                             |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| **Request**      | `{ student_id, first_name, middle_name?, last_name, email, program_id, year_level_id, section }`                        |
| **Response 201** | `{ id, student_id, first_name, middle_name, last_name, email, program_code, year_level_label, section, is_active }`                          |
| **Notes**        | Identity is by email only, and email is unique across users. There is no `username` field anywhere in the contract (removed in ADR-073). Re-creating a roster row for an address whose login was deactivated by a prior hard-delete reclaims that login: fresh CLAIM OTP proof + exactly one live unclaimed roster match required (D72); otherwise 409 `user_exists` / `ambiguous_account` / `unrecognized_email` / `roster_link_impossible`. |

| **Errors**       | 404 `year_level_not_found` · 409 `student_email_exists` · 409 `student_id_exists` · 422 `year_level_program_mismatch` |
#### `GET /admin/students/{student_id}`

Single student detail.

|                  |                                                                                                        |
| ---------------- | ------------------------------------------------------------------------------------------------------ |
| **Response 200** | `{ id, student_id, first_name, middle_name, last_name, email, program_code, year_level_label, section, is_active, created_at, scan_count, face_enrolled: bool, face_enrolled_at?, face_embedding_version? }` |
| **Notes**        | Detail response also carries `student_number` (same `students.student_id` column) — see `GET /student/profile`. |

| **Errors**       | 404 `student_not_found` · 404 `year_level_not_found` |
#### `PATCH /admin/students/{student_id}`

Update student fields (program/year-level/sections; clears face enrollment on identity change).

|                  |                                                       |
| ---------------- | ----------------------------------------------------- |
| **Request**      | `{ first_name?, middle_name? (null clears), last_name?, email?, program_id?, year_level_id?, section?, is_active? }` |
| **Response 200** | Updated student                                      |
| **Notes**        | Soft-deactivate via `is_active=false` (re-activate with `true`). Archiving also deactivates the linked `users` row (`users.is_active=false`); reactivating restores it — the login gate reads `users.is_active` alone (D71). Each sync writes one `UPDATE/USER` audit row. |

| **Errors**       | 404 `student_not_found` · 404 `year_level_not_found` · 409 `student_email_exists` · 422 `year_level_program_mismatch` |
#### `GET /admin/professors`

List professors with claim status (wireframes.md 4.4).

|                  |                                                                                                                  |
| ---------------- | ---------------------------------------------------------------------------------------------------------------- |
| **Query**        | `?search?&department?&is_active?&sort_by?&sort_dir?&page=1&size=20`                                              |
| **Response 200** | `{ items: [{ id, first_name, middle_name, last_name, email, department, is_active, claim_status: "Unclaimed" \| "Claimed", assigned_courses: [{ offering_id, course_code }] }], total, page, size }` |

#### `POST /admin/professors`

Create a professor (wireframes.md 4.4).

|                  |                                                                                                                            |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------- |
| **Request**      | `{ first_name, middle_name?, last_name, email, department, courses?: [offering_id] }`                   |
| **Response 201** | `{ id, first_name, middle_name, last_name, email, department, is_active, claim_status }`                                   |
| **Notes**        | `courses` assigns offerings immediately via `assign_professor` (course_professors rows); users are NOT created for professors. Identity is by email only (no `username` — ADR-073). |

| **Errors**       | 404 `offering_not_found` · 409 `professor_email_exists` |
#### `GET /admin/professors/{professor_id}`

Single professor detail.

|                  |                                                                                                                              |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| **Response 200** | `{ id, first_name, middle_name, last_name, email, department, is_active, claim_status, assigned_courses, created_at }`        |

#### `PATCH /admin/professors/{professor_id}`

Update professor fields + course assignments.

|                  |                                                                       |
| ---------------- | --------------------------------------------------------------------- |
| **Request**      | `{ first_name?, middle_name? (null clears), last_name?, email?, department?, is_active?, courses?: [offering_id] }` |
| **Response 200** | Updated professor                                                    |
| **Notes**        | `courses` replaces the assignment set (removes missing; keeps provided). `is_active=false` also deactivates the linked `users` row; `true` restores it (D71, same as students). |

---

| **Errors**       | 404 `offering_not_found` · 409 `professor_email_exists` |
### Admin Users & Reset

Admin accounts are never self-registered (wireframes.md 4.13). Super Admins manage
admins; admins manage students/professors. Password resets set a temp password
(returned once) and force `must_change_password=true`.

| Method | Path                                    | Purpose                                            | Role        |
| Errors |
| --- |
| ------ | --------------------------------------- | -------------------------------------------------- | ----------- |
| GET    | `/admin/users`                          | List admins (search, role/status filters, sortable) | super_admin | — |
| POST   | `/admin/users`                          | Create admin (name, email, role, temp password?)   | super_admin | 409 `admin_user_email_exists` · 409 `roster_link_impossible` |
| PATCH  | `/admin/users/{user_id}/deactivate`          | Soft-deactivate admin (rejects self-deactivation)  | super_admin | 404 `admin_user_not_found` · 409 `self_deactivation_forbidden` |
| PATCH  | `/admin/users/{user_id}/reactivate`          | Reactivate a deactivated admin (rejects self-reactivation; preserves password, MFA, lockout, and role) | super_admin | 404 `admin_user_not_found` · 409 `self_deactivation_forbidden` |
| POST   | `/admin/users/{user_id}/reset-password`      | Reset admin password → temp + `must_change_password` | super_admin | 404 `user_not_found` |
| POST   | `/admin/students/{student_id}/reset-password`   | Reset linked student-account password (temp once)  | admin | 404 `student_not_found` · 404 `user_not_found` · 409 `student_account_unlinked` |
| POST   | `/admin/professors/{professor_id}/reset-password` | Reset linked professor-account password (temp once)| admin | 404 `professor_not_found` · 404 `user_not_found` · 409 `professor_account_unlinked` |

**Reset response:** `{ temp_password: string }` — shown once. All resets audited.

> **One implementation.** All three routes delegate to
> `AuthService.admin_reset_password`; the student and professor variants resolve the
> roster row to a `users.id` first, and a roster row with no linked account is 409
> `student_account_unlinked` / `professor_account_unlinked`. An admin reset also
> clears `failed_login_attempts`/`is_locked`/`locked_at` so it can actually rescue a
> locked-out account, and deliberately does **not** clear MFA —
> `POST /auth/mfa/disable` is that path, password-verified. Every reset writes a
> `password_reset` audit row with `performed_by` set to the admin.

---

## PROFESSOR Endpoints

### Courses

#### `GET /professor/courses`

List professor's active course assignments with program/year badges.

|                  |                                                                                                                                                |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| **Role**         | professor                                                                                                                                      |
| **Response 200** | `{ items: [{ offering_id, course_id, course_code, course_name, program_id, program_code, year_level_id, year_level_label, semester, academic_year, section, is_primary, effective_from, effective_to, units, enrolled_count, schedule_ok }], ... }` |
| **Notes**        | `section` is derived (from `students.section` via enrollment), not its own column. `units` comes from `courses.units`; `enrolled_count` is the active-enrollment count (wireframes.md 3.6 cards). `schedule_ok` is False when the configured meetings mismatch the units requirement (D82) — the professor UI badges those rows and disables opening up front; rows with no configured meetings read True. |

---

### Sessions

**Session scope (D62).** `sessions.professor_id` records who *opened* a session;
it is attribution, not authorization (D8). Every endpoint below admits a
professor who either opened the session or holds a current `course_professors`
assignment on its offering, and a professor with neither claim gets
`403 not_assigned` (unified with the excuse slice; the admin remove path keeps
its `404 assignment_not_found`, which answers "nothing to remove"). The column
is never rewritten, so history stays
attributed to whoever opened the session. The three read endpoints
(`GET /professor/sessions`, `/sessions/history`, `/professor/attendance`) scope
as a union of both claims rather than replacing ownership with the assignment -
an assignment window is anchored to today, so an assignment-only scope would
hide a professor's own past sessions once that assignment's `effective_to`
passes. The same rule governs the excuse endpoints under `/professor`.

#### `GET /professor/sessions`

|                  |                                                                                                                                        |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| **Query**        | `?from?&to?&offering_id?&session_type=lecture\|lab?&page=1&size=20`                                                                                               |
| **Response 200** | `{ items: [{ id, offering_id, session_type, session_code, created_at, expires_at, duration_minutes, present_count, late_count, absent_count, status }], ... }` |
| **Notes**        | `present_count`/`late_count`/`absent_count` and `status` are computed DTOs (no columns). `status` is `active`/`closed` derived from `expires_at`/close time. `expires_at` is a regular column populated by service layer at creation (D49). |

#### `POST /professor/sessions`

Open a new attendance session.

|                  |                                                                                                                                                                                                         |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Request**      | `{ offering_id: int, session_type?: "lecture" \| "lab" (default "lecture"), duration_minutes?: int, present_window_minutes?: int, late_window_minutes?: int, classroom_radius_meters?: int, classroom_name?: string, classroom_lat?: numeric, classroom_lng?: numeric }` |
| **Response 201** | `{ id, session_code, offering_id, session_type, qr_payload: QRPayload, expires_at, scheduled_end_time, created_at }`                                                                                                            |
| **Errors**       | 409 `session_already_active` · 422 `windows_exceed_duration` · 422 `lab_coordinates_required` · 422 `offering_schedule_mismatch` · 403 `not_assigned` · 404 `offering_not_found` |
| **Notes**        | Session created against a course offering. Schedule/classroom/window defaults copied from offering. `expires_at = min(created_at + duration_minutes, scheduled_end_time)` computed in service layer (D12, D49). The classroom falls back payload → matching active component of the same type → offering. Laboratory sessions always enforce the geofence, so a lab open that resolves to no coordinates is rejected with `lab_coordinates_required`; lecture sessions keep coordinates optional. Opening additionally requires the merged meeting total to equal the course units requirement (D82) — 422 `offering_schedule_mismatch` otherwise — except when no meetings are configured at all, which is exempt as legacy. Closing is never gated. |

#### `GET /professor/sessions/active/{session_id}`

Live session detail with dual timers.

|                  |                                                                                                                                                                                                            |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Response 200** | `{ id, offering, session_type, session_code, scan_window_remaining, scheduled_end_time, status, enrolled_count, remaining, pending_sync_count, students: [{ student_number, name, section, status, scanned_at?, excuse_reason? }], counts: { present, late, pending, absent, excused } }` |
| **Notes**        | `status` and `scan_window_remaining` are computed DTOs (no columns); `scan_window_remaining` is expressed in **seconds**, unlike `duration_minutes` / `present_window_minutes` / `late_window_minutes`. `students[].student_number` maps `students.student_id`; `students[].status` maps `attendance_records.validation_status`; `students[].scanned_at` maps `attendance_records.timestamp`. `enrolled_count`/`remaining` feed the projector stat tiles; `pending_sync_count` feeds the "waiting for offline syncs" banner (wireframes.md 3.3). |

#### `POST /professor/sessions/{session_id}/close`

Manually close session scanning.

|                  |                                                 |
| ---------------- | ----------------------------------------------- |
| **Response 200** | `{ id, status: "closed", final_counts: {...} }`                               |
| **Notes**        | `status: "closed"` is a server-side computed DTO — sessions have no `status` column. |

---

### Excuses

#### `POST /professor/sessions/{session_id}/attendance/{student_id}/excuse`

Quick-excuse a student for this session.

|                  |                                                                                     |
| ---------------- | ----------------------------------------------------------------------------------- |
| **Request**      | `{ reason: string }`                                                                |
| **Response 201** | `{ excuse_request_id, status: "approved", original_status, new_status: "excused" }` |
| **Errors**       | `404 attendance_not_found` · `409 already_excused` · `422 excuse_not_eligible` (`present`/`pending` records) · `403 not_assigned` · `404 professor_not_found` · 404 `attendance_not_found` · 409 `already_excused` · 409 `duplicate_excuse` · 422 `excuse_not_eligible` |
| **Notes**        | `new_status`/`original_status` are DTO fields mapping `attendance_records.validation_status`. |

#### `PATCH /professor/sessions/{session_id}/attendance/{student_id}/excuse`

Update/edit existing excuse.

|                  |                       |
| ---------------- | --------------------- |
| **Request**      | `{ reason?: string }` |
| **Response 200** | Updated excuse        |

#### `DELETE /professor/sessions/{session_id}/attendance/{student_id}/excuse`

Revoke excuse (revert to original status).

|                  |                                    |
| ---------------- | ---------------------------------- |
| **Response 200** | `{ reverted_to: original_status }` |

| **Errors**       | 404 `attendance_not_found` · 404 `excuse_not_found` |
#### `POST /professor/sessions/{session_id}/excuse-all-absent`

Bulk excuse all absent students.

|                  |                                                  |
| ---------------- | ------------------------------------------------ |
| **Request**      | `{ reason: string }`                             |
| **Response 200** | `{ excused_count: int, reason }`                 |
| **Idempotent**   | Re-running with same session returns same result |

| **Errors**       | 404 `attendance_not_found` · 409 `already_excused` · 422 `excuse_not_eligible` |
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

| **Errors**       | 404 `attendance_not_found` · 404 `excuse_not_found` · 409 `already_excused` · 409 `excuse_not_pending` · 422 `excuse_not_eligible` |
### Attendance

#### `GET /professor/attendance`

Query attendance records with filters.

|                  |                                                                                                                                                 |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| **Query**        | `?course_id?&offering_id?&section?&session_id?&session_type=lecture\|lab?&status?&date_from?&date_to?&sort_by?&sort_dir?&page=1&size=20` |
| **Response 200** | `{ items: [{ id, student_number, student_name, section, session_id, session_type, status, original_status?, scanned_at, scanned_via, face_match_score? }], ... }` |
| **Notes**        | `student_number` maps `students.student_id`; `status` maps `attendance_records.validation_status`; `scanned_at` maps `attendance_records.timestamp`; `original_status` is the preserved pre-excuse value. `sort_by` accepts `date`/`student`/`section`/`status`/`time` (wireframes.md 3.4 column headers). |

#### `GET /professor/sessions/history`

Session history with filters.

|                  |                                                            |
| ---------------- | ---------------------------------------------------------- |
| **Query**        | `?offering_id?&section?&session_type=lecture\|lab?&date_from?&date_to?&sort_by?&sort_dir?&page=1&size=20` |
| **Response 200** | `{ items: [{ id, offering_id, session_type, session_code, created_at, expires_at, present_count, late_count, absent_count, compliance_rate, participation_rate }], ... }` |
| **Notes**        | Per-session `present_count`/`late_count`/`absent_count` + both rates feed the 3.5 columns and the compliance/participation tooltip (D36). |

---

### Reports

#### `GET /professor/reports/all-courses`

Aggregate attendance across all assigned courses.

|                  |                                                                                                                                 |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| **Query**        | `?granularity=daily                                                                                                             | weekly | monthly&date_from?&date_to?` |
| **Response 200** | `{ items: [{ date, total_sessions, total_students, compliance_rate, participation_rate }], avg_compliance, avg_participation }` |

#### `GET /professor/reports/comparison`

Per-course comparison sliced by **(course, program, year level)** cohort
(D6/D34): the same subject taught to two cohorts is two rows, not one. Each row
carries its own `program_code`/`year_level_label` so the client labels it
without a course-id lookup (which cannot tell two cohorts apart).

|                  |                                                                                                                                |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| **Query**        | `?program_id?&year_level_id?&semester?&date_from?&date_to?&page?&size?`                                                       |
| **Response 200** | `{ items: [{ course_id, course_code, program_id, year_level_id, program_code, year_level_label, compliance_rate, participation_rate, total_sessions }], total, page, size }` |

(Compare rows at `:451` and `:1023` do accept `granularity=daily|weekly|monthly`; this scoped row does not.)

#### `GET /professor/reports/trends`

Multi-series trend data.

|                  |                                                            |
| ---------------- | ---------------------------------------------------------- |
| **Query**        | `?course_ids?&metric=compliance                            | participation&granularity=daily | weekly | monthly&date_from?&date_to?` |
| **Response 200** | `{ items: [{ date, course_id, course_code, rate }], ... }` |

#### `POST /professor/reports/export`

Export attendance for the professor's own assigned courses (wireframes.md 3.7/3.8). Mirrors the admin analytics export shape, scoped + professor-only.

|                  |                                                                                                                       |
| ---------------- | --------------------------------------------------------------------------------------------------------------------- |
| **Request**      | `{ course_id?, date_from?, date_to?, format: "csv", include: ["student_id","name","timestamp","gps","liveness"], statuses: [ValidationStatus] }` |
| **Response 200** | Generated file (download)                                                                                             |

**Scope note:** Excel/Print are frontend concerns — backend emits CSV or PDF only.

---

### Profile

#### `GET /professor/profile`

Read-only profile.

|                  |                                                                                                                         |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------- |
| **Response 200** | `{ id, first_name, middle_name, last_name, email, department, assigned_courses: [{ offering_id, course_code, course_name, program_code, year_level_label, is_primary }], claim_status, created_at, session_count }` |
| **Notes**        | No `employee_number` column exists on `professors` — omitted. `claim_status` is a computed DTO derived from `professors.user_id` non-null; `session_count`/`created_at` feed the 3.9 "Account · Sessions" line. |

#### `PATCH /professor/profile/password`

Change password.

|                  |                                                                  |
| ---------------- | ---------------------------------------------------------------- |
| **Request**      | `{ current_password: string, new_password: string }` (strong only: 8+ chars, 1 upper, 1 lower, 1 number, 1 symbol → 422 otherwise) |
| **Response 200** | `{ message: "Password updated" }`                                |
| **Errors**       | 400 `current_password_invalid` · 400 `password_reused` · 404 `professor_not_found` |

---

## STUDENT Endpoints

### Session Verification

#### `POST /student/sessions/verify-code`

Verify a typed session code or scan session QR.

|                  |                                                                                                                                                                    |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Role**         | student                                                                                                                                                            |
| **Request**      | `{ code: string }`                                                                                                                                                 |
| **Response 200** | `{ session_id, offering_id, session_type, course_code, course_name, program_code, year_level_label, expires_at, scheduled_end_time, geofence: { radius, lat, lng }, present_window_minutes, late_window_minutes }` |
| **Notes**        | Nested `geofence` keys map to columns: `radius` → `classroom_radius_meters`, `lat` → `classroom_lat`, `lng` → `classroom_lng`. |
| **Errors**       | 404 `session_not_found` · 410 `session_expired` · 404 `offering_not_found` |

---

### Attendance Scan

#### `POST /student/attendance/scan`

Submit attendance scan (online or queued for offline sync).

|                  |                                                                                                                                                                                                                                                                                              |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Request**      | `{ session_id: int, student_number: string, gps: { lat: number, lng: number, accuracy: number }, liveness_evidence: { blink_detected: bool, head_turn_left: bool, head_turn_right: bool, ear_samples: number[], pnp_evidence: object }, face_match_score: number, scanned_at: ISO-8601 }` |
| **Response 200** | `{ id, status: "present"                                                                                                                                                                                                                                                          | "late" | "rejected", scanned_at, expires_at }` |
| **Errors**       | 409 `duplicate_scan` · 403 `outside_geofence` · 403 `liveness_failed` · 403 `face_mismatch` · 403 `not_enrolled` · 403 `student_number_mismatch` · 410 `session_expired` · 404 `student_not_found` |
| **Notes**        | `student_number` maps `students.student_id` and **must match the authenticated account** (case-insensitive); a body naming a different student is refused with 403 `student_number_mismatch` rather than honoured — the student is resolved from the bearer token, never from the body. `gps` is kept as a nested input object but stored flat as `gps_lat`/`gps_lng`; `accuracy` is folded into `liveness_evidence`. `scanned_at` maps `attendance_records.timestamp`; response `status` maps `validation_status`. `scanned_via` (recorded on `attendance_records`): `"qr_camera"` when submitted from a QR scan of the session/student-ID QR, `"manual_code"` when the session code was typed via verify-code. |
| **Idempotency**  | `X-Idempotency-Key` (≤64 chars). A repeat within 15 minutes returns the first `ScanResponse` instead of 409. The cache key is `user_id:session_id:key` and is process-local, so a repeated key from another student never collides and a key does not survive a restart or expire the window. |
| **Offline**      | If offline, client stores locally. On sync, server validates `scanned_at` against session window; expired → `rejected` with reason `session_expired` (D16).                                                                                                                                  |

#### `POST /student/attendance/precheck`

Scan Step 2 gate (wireframes.md 2.2b) — resolves the student and checks enrollment +
duplicate BEFORE GPS/face are captured. **Never writes attendance.**

|                  |                                                                                       |
| ---------------- | ------------------------------------------------------------------------------------- |
| **Role**         | student                                                                               |
| **Request**      | `{ session_id: int, student_number: string }`                                         |
| **Response 200** | `{ enrolled: true, already_scanned: false, student: { student_id, name, section } }` |
| **Errors**       | 404 `session_not_found` · 410 `session_expired` · 403 `student_number_mismatch` · 404 `student_not_found` |
| **Notes**        | Read-only gate — the full submission still goes through `POST /student/attendance/scan`; duplicate-scan is re-checked atomically at submit time. `student_number` is checked against the authenticated account, not used to select the row (see the scan endpoint). `not_enrolled` and `duplicate_scan` are reported as `enrolled: false` / `already_scanned: true` in the 200 body rather than raised, so the client gets both flags in one round trip. |

---

### Attendance History

#### `GET /student/attendance/history`

|                  |                                                                                                                                                                                                                                                           |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Query**        | `?program_id?&year_level_id?&semester?&course_id?&status?&date_from?&date_to?&sort_by?&sort_dir?&page=1&size=20`                                                                                                                                          |
| **Response 200** | `{ items: [{ id, session_id, course_code, course_name, status, original_status?, excuse_reason?, scanned_at, scanned_via }], total, page, size, summary: { compliance_rate, participation_rate, counts: { present, late, absent, excused, rejected } } }` |
| **Notes**        | `course_id`/`date_from`/`date_to` match the 2.7 filters; `sort_by` accepts `date`/`course`/`section`/`status`/`time`. |

| **Errors**       | 404 `student_not_found` |
#### `GET /student/attendance/history/export`

CSV export of the filtered history — **all rows** (not just the page). Same filters
as the list endpoint.

|                  |                       |
| ---------------- | --------------------- |
| **Response 200** | CSV file download     |

---

| **Errors**       | 404 `student_not_found` |
### Schedule

#### `GET /student/schedule`

|                  |                                                                                                                                                                                 |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Response 200** | `{ offerings: [{ offering_id, course_id, course_code, course_name, program_code, year_level_label, semester, schedule_days, schedule_start_time, schedule_end_time, classroom_name, professor_name }] }` |

---

| **Errors**       | 404 `student_not_found` |
### Excuses

#### `POST /student/excuse-requests`

Submit an excuse request with evidence.

|                  |                                                                                   |
| ---------------- | --------------------------------------------------------------------------------- |
| **Request**      | JSON `{ session_id: int, reason: string, attachment_urls: string[1..5] }` (presigned-upload flow; the `multipart/form-data` form is superseded) |
| **Response 201** | `{ id, status: "pending", requested_at }`                                         |
| **Errors**       | `404 attendance_not_found` · `403 not_enrolled` · `409 already_excused` (record already excused) · `422 excuse_not_eligible` (record is `present`/`pending`, nothing to excuse) · `409 duplicate_excuse` · 404 `student_not_found` · 404 `attendance_not_found` · 409 `already_excused` · 409 `duplicate_excuse` · 422 `excuse_not_eligible` |

#### `GET /student/excuse-requests`

|                  |                                                                                                                |
| ---------------- | -------------------------------------------------------------------------------------------------------------- |
| **Query**        | `?page=1&size=20`                                                                                              |
| **Response 200** | `{ items: [{ id, session_id, status, reason, requested_at, reviewed_by?, reviewed_at?, review_notes? }], ... }` |

| **Errors**       | 404 `student_not_found` |
#### `GET /student/excuse-requests/{rid}`

|                  |                            |
| ---------------- | -------------------------- |
| **Response 200** | Full excuse request detail |

---

| **Errors**       | 404 `student_not_found` · 404 `excuse_not_found` |
### Face Embedding

#### `GET /student/me/face-embedding`

Pull face embedding (version-gated, D29).

|                  |                                                                                                                    |
| ---------------- | ------------------------------------------------------------------------------------------------------------------ |
| **Query**        | `?current_version=0`                                                                                               |
| **Response 200** | `{ version: int, embedding: string (base64-encoded encrypted blob) }` — only if `current_version < server_version` |
| **Response 204** | No content (version matches, no update needed)                                                                     |

---

| **Errors**       | 404 `face_embedding_not_found` · 404 `student_not_found` |
### Profile & Settings

#### `GET /student/profile`

Read-only identity fields.

|                  |                                                                                                                                          |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| **Response 200** | `{ student_number, first_name, middle_name, last_name, email, program_code, year_level_label, section, is_active, face_enrolled: bool, created_at, scan_count, face_enrolled_at?, face_embedding_version }` |
| **Notes**        | Also carries `student_id` alongside `student_number` — the same `students.student_id` column under the name the admin roster rows use (:615/:634). Both spellings are emitted on this response and on `GET /admin/students/{student_id}` so either client reads the name it expects. |
| **Notes**        | `created_at` (Account date) + `scan_count` + face-enrollment meta feed wireframes.md 2.10 ("Account: Jun 2026 · Scans: 42", "Enrolled (vN)"). |

| **Errors**       | 404 `student_not_found` |
#### `PATCH /student/profile/password`

Same contract as professor password change.

---

| **Errors**       | 404 `student_not_found` |
## Dashboard Summaries

One-call stat summaries for the three dashboards (wireframes.md 2.1/3.1/4.1). Each is
a single aggregate query set — no new tables — so the frontend renders the stat cards
and primary lists without composing several calls.

#### `GET /student/dashboard`

|                  |                                                                                                     |
| ---------------- | --------------------------------------------------------------------------------------------------- |
| **Role**         | student                                                                                             |
| **Response 200** | `{ compliance_rate, scans_today, total_scans, today_schedule: [...], recent_activity: [...] }`      |

| **Errors**       | 404 `student_not_found` |
#### `GET /professor/dashboard`

|                  |                                                                                     |
| ---------------- | ----------------------------------------------------------------------------------- |
| **Role**         | professor                                                                           |
| **Response 200** | `{ sessions_today, sessions_completed, total_students, avg_rate, today_sessions: [{ session_id, offering_id, scanned, enrolled }] }` |

(`today_sessions` items are keyed by `session_id`; the schema splits the contract's bare
`offering` into both `session_id` and `offering_id` so the client can link onward.)

#### `GET /admin/dashboard`

|                  |                                                                  |
| ---------------- | ---------------------------------------------------------------- |
| **Role**         | admin                                                             |
| **Response 200** | `{ student_count, professor_count, program_count, avg_rate, scans_today, pending_sync, recent_scans: [...] }` |

---

## Attachment Uploads

Excuse evidence is uploaded straight to storage, so the file bytes never pass
through the API (D24, `excuse-workflow.md` §7). The client mints a URL here, PUTs
the bytes itself, then submits the excuse carrying the returned `object_url` — the
database stores URL references only, never file bytes.

#### `POST /upload/presigned-url`

|                  |                                                                                |
| ---------------- | ------------------------------------------------------------------------------ |
| **Role**         | any authenticated account (student, professor, admin)                           |
| **Request**      | `{ filename: string, size_bytes: int, content_type?: string }`                  |
| **Response 200** | `{ upload_url, object_url, object_key, expires_in }`                             |
| **Errors**       | 400 `invalid_attachment` · 413 `file_too_large` · 503 `storage_unconfigured` |

| Constraint                  | Value                              | Enforced by                          |
| --------------------------- | ---------------------------------- | ------------------------------------ |
| Max file size               | 5 MiB (`ATTACHMENTS_MAX_BYTES`)    | rejected before any storage call      |
| Allowed types               | PDF, JPG, PNG, HEIC                | filename extension, case-insensitive  |
| Max attachments per request | 5                                  | the excuse schemas, not this endpoint |
| Immutability                | uploaded objects are never deleted | no delete endpoint exists             |

The content type handed to storage is derived from the validated extension, never
taken from the client; a `content_type` contradicting the extension (e.g.
`evidence.pdf` announced as `application/x-msdownload`) is rejected.

Which backend serves the URL follows `ATTACHMENTS_STORAGE_TYPE`. `local` (the dev
default) returns a `file://` URL and needs no dependency; `s3` presigns a
`put_object` against the shared backup bucket and needs `boto3` plus
`BACKUP_S3_BUCKET`. Attachments sit under their own `attachments/` key prefix, so
backup retention pruning never touches them.

---

## SHARED Auth Endpoints

Phase 2 auth surface. Schemas live in `backend/src/features/auth/schema.py`.
The register is an exact-one roster match and captures the security question;
login applies the OTP + MFA gates; refresh returns tokens in the body; accounts
lock after 5 failed attempts.

| Method | Path                               | Purpose                                              |
| Errors |
| --- |
| ------ | ---------------------------------- | ---------------------------------------------------- |
| POST   | `/auth/otp/request`                | Request 6-digit OTP (email) | 400 `invalid_credentials` |
| POST   | `/auth/otp/verify`                 | Verify OTP code | 400 `otp_expired` · 400 `otp_invalid` |
| POST   | `/auth/register`                   | Claim-based registration (OTP + password + security question; revives a deactivated login for a re-created roster row) | 400 `otp_expired` · 400 `otp_invalid` · 404 `unrecognized_email` · 409 `ambiguous_account` · 409 `user_exists` |
| POST   | `/auth/login`                      | Email/password login (+ OTP & MFA gates) | 400 `invalid_credentials` · 423 `account_locked` |
| POST   | `/auth/login/verify`               | Verify login OTP → tokens (or MFA challenge for admins with MFA) | 400 `invalid_credentials` · 400 `otp_expired` · 400 `otp_invalid` · 423 `login_otp_locked` · 429 `rate_limited` |
| POST   | `/auth/login/resend`               | Resend login OTP (burns the previous code) | 400 `invalid_credentials` |
| POST   | `/auth/refresh`                    | Refresh-token rotation | 400 `invalid_credentials` |
| POST   | `/auth/forgot-password`            | Forgot-password step 1 — returns the security question | — |
| POST   | `/auth/forgot-password/verify`     | Step 2 — verify answer (3-attempt cap, then lock) → 200 `RecoveryGrantResponse` | 400 `security_answer_invalid` · 423 `recovery_locked` |
| POST   | `/auth/reset-password`             | Step 4 — reset password with OTP, returns the session (or an MFA challenge) | 400 `otp_expired` · 400 `otp_invalid` · 400 `password_reused` · 404 `unrecognized_email` |
| POST   | `/auth/change-password`            | Change password (authenticated) | 400 `current_password_invalid` · 400 `password_reused` |
| POST   | `/auth/security-question`          | Set/update security question (authenticated) | — |
| POST   | `/auth/mfa/backup-codes`           | Generate 10 backup codes (plaintext, once) | — |
| GET    | `/auth/mfa/backup-codes`           | Backup-code summary (total/remaining) | — |
| GET    | `/auth/me`                         | Current user info (role + security/MFA state) | — |
| POST   | `/auth/mfa/setup`                  | Generate TOTP secret | 409 `mfa_already_enabled` |
| POST   | `/auth/mfa/verify`                 | Verify TOTP or backup code (login exchange or setup) | 400 `invalid_credentials` · 400 `invalid_mfa_code` |
| POST   | `/auth/mfa/disable`                | Disable MFA (password required; clears backup codes) | 400 `current_password_invalid` · 409 `mfa_not_enabled` |

**Login OTP (mandatory second factor):** a password-OK `POST /auth/login` no
longer issues tokens directly, except for students/professors with MFA enabled
(who keep the TOTP preauth path and receive no email — TOTP is strictly
stronger than an emailed code). Everyone else gets `{otp_pending: true,
otp_token}` plus a 6-digit LOGIN OTP by email (`otp_codes` row, purpose
`login`, 5-minute expiry, Argon2id hash, single-use). `POST /auth/login/verify`
exchanges `{otp_token, code}` for the token pair — or, for an admin with MFA
enabled, for `{mfa_pending: true, preauth_token}` (OTP then TOTP). `POST
 /auth/login/resend` mints a fresh code and burns the previous one — and resets
 the email's wrong-code budget, since guesses against the burned code are
 guesses against a dead credential. Wrong codes are capped at 3 per email
 inside the 5-minute OTP window (then 423 `login_otp_locked`); a second,
 failure-only cap of 15 misses per client IP (then 429 `rate_limited`) survives
 email rotation — resends do not reset it. Expired codes and correct codes
 spend neither budget. The `otp_token` is a
5-minute `type="login_otp"` JWT carrying the account email: a missing,
malformed, expired, wrong-typed, or email-mismatched grant — like a missing or
inactive account — returns generic 400 `invalid_credentials`, and the grant is
rejected by the access-token dependency so it can never buy API access.

**Forgot-password flow (wireframes.md:152-260, ADR-052, hardened by ADR-056):**
Step 1 (`/auth/forgot-password`, email) → Step 2 (`/auth/forgot-password/verify`,
answer hash-checked with Argon2id; max 3 attempts per email then the recovery
attempt locks) → Step 3 OTP (`/auth/otp/request` with purpose `forget_password`) →
Step 4 (`/auth/reset-password`). The security question is mandatory and set at
claim registration (`/auth/register`).

Non-enumeration (ADR-056): step 1 returns `{question, set: true}` for every email.
For an unknown address the question is a **deterministic** decoy — an HMAC of the
normalized email over `SECURITY_QUESTION_POOL` — so a given address always yields
the same question and a real account's question never changes between requests.
`set` is always `true` and carries no information. The response shape, status, and
timing are identical to the known-email case, so step 1 is not an enumeration
oracle; an unknown address simply fails at step 2 with the same
`security_answer_invalid` error. Note this is *not* byte-identical output — the
decoy text differs from a real question — so it mitigates rather than fully
prevents enumeration. Emailing the question instead of returning it would close
the gap; that is deferred (ADR-056).

Step gating (ADR-056): step 2 returns **200** with a `RecoveryGrantResponse`
carrying `recovery_token`, a signed JWT with `type="recovery"`, the account's
email, and a 5-minute expiry. Step 3 will not mint a `forget_password` OTP without
a valid grant — a missing, malformed, expired, or email-mismatched grant returns
`400 invalid_credentials` with a generic message, so the gate is not itself
probeable. The grant is rejected by the access-token dependency (it carries a
`type` claim) and so cannot be replayed for API access. `/auth/reset-password`
(step 4) consumes the OTP and returns the session directly — a `TokenResponse`
with the token pair, or `{mfa_pending: true, preauth_token}` for MFA-enabled
accounts (same shape as login, finished with TOTP). Like registration, there
is no second login dance: recovery already proved inbox access plus the
security answer, and `must_change_password` is False because the password is
user-chosen, not admin-issued.

**Security-question storage (ADR-056):** only the **answer** is hashed
(`users.security_answer_hash`, Argon2id). `users.security_question_hash` stores the
question in **readable plaintext** under a legacy column name, because step 1 must
return it for the user to read. The question is non-secret by design — it is drawn
from a small preset pool in the settings UI. See
[security-model.md](security-model.md) and
[database-er.md](../design/database-er.md).

**Captcha (ADR-053):** `LoginRequest` and `ForgotPasswordStep1Request`
carry an optional `turnstile_token`. Server calls Cloudflare `siteverify` via
`shared/captcha.py`; when `TURNSTILE_SECRET_KEY` is unset the check passes
through (captcha disabled in dev/test/prod-until-key-set); with the key set, a
missing or invalid token is `400 invalid_captcha`. Deployment runbook:
[production-checklist.md §3](../deployment/production-checklist.md).

**MFA backup codes (ADR-054):** `POST /auth/mfa/backup-codes` returns
`{codes: [10×, shown once], remaining: 10}` and invalidates unconsumed codes; codes
hash-checked single-use in `/auth/mfa/verify` (preauth exchange or setup). Each code
is a 10-char base32 string (e.g. `X4T7-K9M2-PL`) — the 1.6 login/mfa input strips
separators before verification. `POST /auth/mfa/disable` verifies the current
password, sets `mfa_enabled=false`, clears the TOTP secret, and invalidates all
unconsumed backup codes.

**GET /auth/me (role + security state):** returns
`{ id, role, first_name, last_name, email, mfa_enabled, security_question_set,
must_change_password, last_login? }` plus role-scoped context — student:
`face_enrolled`/`face_enrolled_at?`/`face_embedding_version`/`scan_count`;
professor: `claim_status`; admin: `role` (is `super_admin`/`admin`). Feeds the
status lines on 2.10/2.11/3.9/4.11 and the client auth guard.

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
| Forgot-password 4-step + security question          | ADR-052            |
| Turnstile `turnstile_token` fields                  | ADR-053            |
| MFA backup-code endpoints                          | ADR-054            |
| Recovery grant gating steps 3–4                     | ADR-056            |
| Deterministic decoy question on step 1              | ADR-056            |
| Security-question plaintext storage (answer only hashed) | ADR-056        |
| Admin routing: separate `admin_router.py` per feature | ADR-057            |
| No `/admin/enrollments` mount; bulk-enroll lives under offerings | ADR-057 |
| Archive delete 409 `student_has_records` / `professor_has_records` | ADR-057 |
| `GET /admin/programs` optional `?search=` filter | ADR-058            |
| Program aggregates derived per request (`terms_count` via the `terms` JSONB key, `course_count` via `course_offerings`) | ADR-058 |
| Program archive is program-row-only (no cascade)    | ADR-058            |
