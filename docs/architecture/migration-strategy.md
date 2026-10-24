# Migration Strategy: Target Schema

> Target schema reference (§6) and rollback guide. This project is **greenfield** — the
> baseline migration (`679a319c12d6`) creates the current 16 tables directly. `alembic upgrade head`
> on a fresh database produces the current target schema with correct columns, constraints,
> and FKs. **No backfill functions or data migration scripts are needed.**
>
> **Forward-looking:** four tables landed with later backend-phases —
> `mfa_backup_codes` (Phase 2.11), `audit_logs` (Phase 8.5), `app_settings` (Phase
> 12.0) and `student_risk_scores_staging` (`d4e5f6a7b8c9`) — bringing the baseline
> to a **20-table** target schema. Each addition gets its own
> `alembic revision --autogenerate`. `audit_logs` (`f4a9c2b7d103`) carries structural
> rows today and takes the broader audit coverage in Phase 8.7.
>
> **Alembic import rule:** Every new model (`features/program/model.py`, plus new tables in
> `analytics`, `excuse`, `system` features) MUST be imported in `backend/alembic/env.py`
> alongside the existing thirteen feature imports so autogenerate sees them in
> `target_metadata`. Run alembic from `backend/`.

---

## Historical Reference: Legacy Schema (Superseded)

> The 9-step incremental migration narrative below was the original plan before the
> full-baseline approach was adopted. It is **reference documentation only** — useful for
> institutions migrating from an existing flat-schema database. For greenfield deployments,
> ignore the backfill and migration steps entirely.

Tables from the original flat schema (Alembic head `996b2fb85c6f`, now replaced):

- `users` — auth + roles + security fields
- `otp_codes` — OTP for claim/forgot-password
- `students` — legacy `course` string, `section`, `year_level` (int), `user_id` FK
- `professors` — `department`, `user_id` FK
- `courses` — flat: `course_code`, `course_name`, `classroom_lat/lng`, `schedule` (string)
- `enrollments` — `student_id`, `course_id`, `academic_year`
- `sessions` — `course_id`, `professor_id`, `session_code`, `expires_at`, `classroom_radius_meters`
- `attendance_records` — `student_id`, `session_id`, `timestamp`, `gps_lat/lng`, `validation_status` (valid/pending/rejected), `sync_status`
- `sync_queue` — `record_data` JSON, `status`, `retry_count`

Enums: `UserRole`, `OtpPurpose`, `ValidationStatus` (valid/pending/rejected), `SyncStatus`, `QueueStatus`

---

## Target Schema (§6 — Authoritative Reference)

Tables: `users`, `otp_codes`, `programs`, `year_levels`, `courses`, `course_offerings`, `course_professors`, `students`, `professors`, `enrollments`, `sessions`, `attendance_records`, `excuse_requests`, `student_risk_scores`, `backup_log`, `sync_queue`

The baseline migration creates these 16 tables with correct columns, constraints, and FKs. See [database-er.md](../design/database-er.md) for the full ERD.

> **Target grows to 20 tables** as the four later tables are added: `mfa_backup_codes`
> (Phase 2.11), `audit_logs` (Phase 8.5), `app_settings` (Phase 12.0),
> `student_risk_scores_staging` (`d4e5f6a7b8c9`). All four
> models are imported into `backend/alembic/env.py` (the first two via
> `features.auth.model` / `features.system.model`) and have their own revisions.

---

## Migration Steps (Ordered)

### Step 1: Create `programs` Table

**Migration:** `alembic revision --autogenerate -m "create programs table"`

**Model:** `features/program/model.py` (new feature)

```python
class Program(Base):
    __tablename__ = "programs"
    id = BigInteger PK
    code = String(20) UK  -- e.g., "BSCS"
    name = String(100)
    description = Text
    total_years = Integer
    is_active = Boolean default True
    created_at, updated_at = TimestampMixin
```

**Programs are created by admins via `POST /admin/programs`.** No seed data — the table starts empty.

**Rollback:** `DROP TABLE programs` (destructive — backup first)

---

### Step 2: Create `year_levels` Table

**Migration:** `alembic revision --autogenerate -m "create year_levels table"`

**Model:** `features/program/model.py` (same feature)

```python
class YearLevel(Base):
    __tablename__ = "year_levels"
    id = BigInteger PK
    program_id = BigInteger FK → programs.id CASCADE
    year_number = Integer  -- 1..total_years
    label = String(50)  -- "1st Year"
    term_structure = JSONB  -- {"terms": [{"code": "1st_sem", "label": "1st Semester"}, ...]}
    sort_order = Integer
    UNIQUE(program_id, year_number)
```

**Year levels are created by admins via `POST /admin/programs/{pid}/years`.** No seed data.

**Rollback:** `DROP TABLE year_levels` (CASCADE drops nothing yet)

---

### Step 3: Extend `courses` + Create `course_offerings` Table

**Migration:** `alembic revision --autogenerate -m "extend courses with metadata and create course_offerings"`

**Changes to `features/course/model.py`:**

Course becomes a pure template — no program/year FKs. Scheduling and classroom
details move to `course_offerings` since they vary per program/semester.

```python
class Course(TimestampMixin, Base):
    # Existing: id, course_code, course_name, classroom_lat, classroom_lng, schedule
    # REMOVED: classroom_lat, classroom_lng (moved to course_offerings)
    # NEW:
    units = Integer
    session_duration_hours = Numeric(3,1)
    is_active = Boolean default True
    created_at, updated_at = TimestampMixin
```

**New table `course_offerings`** (in `features/course/model.py`):

```python
class CourseOffering(Base):
    __tablename__ = "course_offerings"
    id = BigInteger PK
    course_id = BigInteger FK → courses.id RESTRICT
    program_id = BigInteger FK → programs.id RESTRICT
    year_level_id = BigInteger FK → year_levels.id RESTRICT
    semester = String(20)  -- '1st_sem', '2nd_sem', 'midyear'
    academic_year = String(20)  -- '2025-2026'
    sessions_per_week = Integer
    semester_weeks = Integer
    schedule_days = String(10)  -- "MWF", "TTh", etc.
    schedule_start_time = Time
    schedule_end_time = Time
    classroom_name = String(100)
    classroom_lat = Float
    classroom_lng = Float
    default_present_window_minutes = Integer default 5
    default_late_window_minutes = Integer default 10
    is_active = Boolean default True
    created_at, updated_at = TimestampMixin
    UNIQUE(course_id, program_id, semester, academic_year)
```

**Design rationale:**
- Course is a reusable template (e.g., "CS101: Intro to Programming")
- CourseOffering is a specific instance for a program + year level + semester
- Same course can have different schedules/classrooms per program offering
- `Session` and `Enrollment` will reference `offering_id` in later steps

> **Reference Only** — In greenfield deployments, `course_offerings` rows are created by
> admins via the API. No backfill needed. The steps below apply only when migrating from
> the legacy flat schema.

**Backfill strategy (legacy data only):**

1. Add new columns to `courses` as **nullable** first
2. For each existing `courses` row:
   - Set defaults: units (3), session_duration_hours (1.5)
3. Create `course_offerings` rows: for each course, create one offering per
   program that has enrolled students (via enrollments → students), inferring
   program_id/year_level_id from enrolled students
   - Parse legacy `schedule` string for schedule_days/times; else default
   - Set defaults: sessions_per_week (2), semester_weeks (18), windows (5/10)
4. After backfill: `ALTER COLUMN ... SET NOT NULL` on critical `courses` metadata
5. Drop legacy `schedule`, `classroom_lat`, `classroom_lng` from `courses`
   (data now lives in `course_offerings`)

**Rollback:** Drop `course_offerings` rows, revert `courses` columns to nullable, restore dropped columns from backup. **Backup before migrate.**

---

### Step 4: Create `course_professors` Table

**Migration:** `alembic revision --autogenerate -m "create course_professors many-to-many with effectiveness dates"`

**Model:** `features/professor/model.py` (extend) or new `features/course_professor/model.py`

```python
class CourseProfessor(Base):
    __tablename__ = "course_professors"
    offering_id = BigInteger FK → course_offerings.id RESTRICT
    professor_id = BigInteger FK → professors.id RESTRICT
    is_primary = Boolean default False
    effective_from = Date NOT NULL
    effective_to = Date NULL  -- NULL = ongoing
    semester = String(20)  -- validated against year_level.term_structure
    assigned_by = BigInteger FK → users.id
    assigned_at = DateTime(timezone=True) default now()
    PK(offering_id, professor_id, effective_from)
```

**Service-layer rule (enforced in Python, not DB):** Reject overlapping `[effective_from, effective_to)` ranges for same `(offering_id, professor_id)`.

> **Delete rule history:** the baseline `679a319c12d6` created all three FKs as
> `ON DELETE CASCADE`; `a562c3f8a6f7_restrict_fks_course_professors_risk_.py` dropped
> those constraints and recreated them as `RESTRICT` (it did the same for
> `student_risk_scores`). RESTRICT is the current contract — it forces the has-records
> guard on offering and professor delete instead of silently deleting assignments.
> `assigned_by` was `RESTRICT` in the baseline and is unchanged.

> **Reference Only** — In greenfield deployments, `course_professors` rows are created via
> admin API. The steps below apply only when migrating from legacy session data.

**Migrate implied assignments (legacy data only):** For each existing `sessions` row, look up the `course_offerings` row matching the session's course + inferred program/semester, create a `course_professors` entry with `effective_from = session.created_at::date`, `effective_to = NULL`, `semester = enrollment.semester` (or default), `is_primary = true`.

**Rollback:** `DROP TABLE course_professors`

---

### Step 5: Extend `enrollments` — Add `semester` + `offering_id` FK

> **Reference Only** — In greenfield deployments, enrollments are created with
> `offering_id` and `semester` directly. The steps below apply only when migrating
> from the legacy enrollment schema.

**Migration:** `alembic revision --autogenerate -m "add semester and offering_id to enrollments with backfill"`

**Changes:**

1. Add `offering_id = BigInteger FK → course_offerings.id` nullable
2. Add `semester VARCHAR(20)` nullable
3. Backfill: for each enrollment, look up the matching `course_offerings` row
   (via course_id + student's program/year_level) and set `offering_id`
   - Set `semester` from `course_offerings.semester` (default `'1st_sem'`)
4. After backfill: `ALTER COLUMN offering_id SET NOT NULL`, `ALTER COLUMN semester SET NOT NULL`
5. Drop `course_id` column (offering_id provides the course link via course_offerings.course_id)
6. Update unique constraint from `(student_id, course_id, academic_year)` to `(student_id, offering_id, academic_year)`

**Backfill SQL:**
```sql
UPDATE enrollments e
SET
    offering_id = co.id,
    semester = COALESCE(co.semester, '1st_sem')
FROM students s
JOIN programs p ON p.code = s.course
JOIN year_levels yl ON yl.program_id = p.id AND yl.year_number = s.year_level
JOIN course_offerings co
    ON co.course_id = e.course_id
    AND co.program_id = p.id
    AND co.year_level_id = yl.id
    AND (co.academic_year = e.academic_year OR e.academic_year IS NULL)
WHERE e.student_id = s.id;
```

> **Note:** `COALESCE(co.semester, '1st_sem')` handles the case where multiple offerings exist for the same (course, program, year_level) with different semesters. Rows with ambiguous semester default to `'1st_sem'` and can be corrected post-migration.

**Validation:** Application logic validates `semester` against `student.year_level.term_structure` (via `student.year_level` → `year_levels.term_structure`).

**Rollback:** Drop columns (data loss — backup first)

---

### Step 6: Extend `sessions` — Duration, Windows, Scheduled Times, Override

**Migration:** `alembic revision --autogenerate -m "extend sessions with duration windows scheduled times and classroom override"`

**Changes to `features/session/model.py`:**

```python
class Session(Base):
    # Existing: id, session_code, expires_at, classroom_radius_meters
    # DROP: course_id (redundant — reachable via offering_id → course_offerings.course_id)
    # NEW FK: offering_id → course_offerings.id
    # RETARGET: professor_id FK from users.id → professors.id
    # NEW:
    duration_minutes = Integer
    present_window_minutes = Integer
    late_window_minutes = Integer
    CHECK (present_window_minutes + late_window_minutes <= duration_minutes)
    scheduled_start_time = DateTime(timezone=True)  -- copied from course_offering at open
    scheduled_end_time = DateTime(timezone=True)    -- copied from course_offering at open
    expires_at = DateTime(timezone=True)  -- regular column, app-computed via @property (D49)
    classroom_name = String(100) NULL
    classroom_lat = Float NULL
    classroom_lng = Float NULL

    # @property computed_expires_at:
    #   return min(created_at + timedelta(minutes=duration_minutes), scheduled_end_time)
    #   NOTE: the model docstring cites a "-12s clock-skew buffer", but the property
    #   does NOT subtract it — expires_at is written verbatim (D49; documented, unchanged).
    # Service sets: session.expires_at = session.computed_expires_at
```

> **Reference Only** — In greenfield deployments, sessions are created with all fields
> populated. The steps below apply only when migrating from the legacy session schema.

**Backfill (legacy data only):**

- `offering_id` = look up `course_offerings` row matching session's course + inferred program/semester
- `course_id` = **DROP** after `offering_id` is backfilled and NOT NULL
- `duration_minutes` = `course.session_duration_hours * 60` (default 90)
- `present_window_minutes` = `course_offering.default_present_window_minutes` (5)
- `late_window_minutes` = `course_offering.default_late_window_minutes` (10)
- `scheduled_start_time/end_time` = `course_offering` schedule for that day (compute from `schedule_days` + date)
- `classroom_lat/lng/name` = `course_offering` classroom (override for session-specific room changes)
- `expires_at` = set by service layer: `min(created_at + duration_minutes * interval '1 min', scheduled_end_time)`

**Rollback:** Drop new columns, restore `course_id` from backup.

---

### Step 7: Extend `attendance_records` — Evidence, Excuse, Expanded Status

**Migration:** `alembic revision --autogenerate -m "extend attendance_records with evidence excuse and expanded status enum"`

**Changes to `features/attendance/model.py`:**

```python
class Attendance(Base):
    # Existing: id, student_id, session_id, timestamp, gps_lat, gps_lng, validation_status, sync_status
    # NEW:
    liveness_evidence = JSONB  -- {gps{lat,lng,accuracy}, liveness_evidence{blink_detected, head_turn_left, head_turn_right, ear_samples, pnp_evidence}, face_match_score, scanned_via, scanned_at, rejection_reason?}
    face_match_score = Numeric(5,4)  -- client-submitted score; no cosine comparison
    scanned_via = String(20)  -- 'qr_camera' | 'manual_code'
    original_status = String(20) NULL  -- status before excuse
    excuse_reason = Text NULL
    excused_by = BigInteger FK → users.id NULL
    excused_at = DateTime(timezone=True) NULL
    excuse_type = String(30) NULL  -- 'quick' | 'prof_with_evidence' | 'request_approved'
    excuse_request_id = BigInteger FK → excuse_requests.id NULL
```

**Data migration for status enum:**

| Old Value  | New Value                                                   |
| ---------- | ----------------------------------------------------------- |
| `valid`    | `present`                                                   |
| `pending`  | `pending` (unchanged)                                       |
| `rejected` | `rejected` (add `rejection_reason` to evidence if possible) |

**Enum change:** `ValidationStatus` enum in code expands; DB column remains `VARCHAR(20)` (no native enum type).

**Rollback:** Map `present` → `valid`, drop new columns. **Backup before migrate.**

---

### Step 8: Create New Tables — `excuse_requests`, `student_risk_scores`, `backup_log`

**Migration:** `alembic revision --autogenerate -m "create excuse_requests student_risk_scores backup_log tables"`

#### `excuse_requests` (feature: `excuse`)

```python
class ExcuseRequest(Base):
    __tablename__ = "excuse_requests"
    id = BigInteger PK
    student_id = BigInteger FK → students.id
    session_id = BigInteger FK → sessions.id
    initiated_by = String(20)  -- 'professor' | 'student'
    initiated_via = String(30)  -- 'quick' | 'prof_with_evidence' | 'request'
    reason = Text
    attachment_urls = JSONB  -- array of S3/local URLs
    status = String(20) default 'pending'  -- 'pending' | 'approved' | 'rejected'
    requested_at = DateTime(timezone=True) default now()
    reviewed_by = BigInteger FK → users.id NULL
    reviewed_at = DateTime(timezone=True) NULL
    review_notes = Text NULL
```

#### `student_risk_scores` (feature: `analytics`)

```python
class StudentRiskScore(Base):
    __tablename__ = "student_risk_scores"
    id = BigInteger PK
    student_id = BigInteger FK → students.id
    offering_id = BigInteger FK → course_offerings.id
    semester = String(20)
    risk_probability = Numeric(5,4)
    risk_level = String(10)  -- 'low' | 'medium' | 'high'
    features = JSONB  -- {absence_rate, max_streak, sync_lag, trend_slope, expected_sessions}
    computed_at = DateTime(timezone=True) default now()
    UNIQUE(student_id, offering_id, semester, computed_day)
```

#### `backup_log` (feature: `system`)

```python
class BackupLog(Base):
    __tablename__ = "backup_log"
    id = BigInteger PK
    filename = String(255)
    kind = String(20)  -- 'full' | 'analytics'
    size_bytes = BigInteger
    sha256 = String(64)
    storage_backend = String(20)  -- 'local' | 's3'
    encryption_key_version = Integer
    started_at = DateTime(timezone=True)
    finished_at = DateTime(timezone=True) NULL
    status = String(20)  -- 'started' | 'completed' | 'failed'
    error = Text NULL
```

**Rollback:** `DROP TABLE excuse_requests, student_risk_scores, backup_log`

---

### Step 9: Extend `students` — Year Level FK + Face Columns + Drop Legacy `course`

**Migration:** `alembic revision --autogenerate -m "add face embedding columns to students and drop legacy course string"`

**Changes to `features/student/model.py`:**

```python
class Student(Base):
    # Existing: id, user_id, student_id, email, names, section, year_level, is_active
    # NEW FK: year_level_id → year_levels.id (RESTRICT) — NOT program_id
    year_level_id = BigInteger FK → year_levels.id
    # RETAINED: section — kept as a snapshot on the row (year level via FK)
    # NEW:
    face_embedding = LargeBinary NULL  -- BYTEA: encrypted JSON blob
    face_enrolled_at = DateTime(timezone=True) NULL
    face_embedding_version = Integer default 0
    # DROP: course (string) — after backfill to FK-based year_levels/enrollments
```

> **Reference Only** — In greenfield deployments, students are created with
> `year_level_id` directly. The steps below apply only when migrating from the legacy
> `students.course` string format.

**Backfill legacy `course` string (legacy data only):**

1. For each student, parse `student.course` string (e.g., "BSCS-1")
2. Match to `programs.code` + `year_levels.year_number`
3. Set `student.year_level_id` from the matching `year_levels` row
4. Ensure enrollment exists for that course in the correct program/year
5. After verification: `ALTER COLUMN year_level_id SET NOT NULL`, then drop `course` column

**Rollback:** Recreate `course` VARCHAR column, restore from backup. `year_level_id` and face columns dropped.

---

## Alembic Import Rule (Critical)

**File:** `backend/alembic/env.py`

Current imports — all 13 features:

```python
import features.analytics.model  # noqa: F401        # student_risk_scores
import features.attendance.model  # noqa: F401
import features.auth.model  # noqa: F401
import features.course.model  # noqa: F401
import features.course_professor.model  # noqa: F401  # course_professors
import features.enrollment.model  # noqa: F401
import features.excuse.model  # noqa: F401            # excuse_requests
import features.professor.model  # noqa: F401
import features.program.model  # noqa: F401           # programs, year_levels
import features.session.model  # noqa: F401
import features.student.model  # noqa: F401           # + face_enrollment columns
import features.sync.model  # noqa: F401
import features.system.model  # noqa: F401            # backup_log
```

**Run alembic from `backend/` directory** so `features.*` imports resolve.

---

## Rollback Strategy Summary

> For greenfield deployments, rollback is simply `DROP TABLE` — no data to lose. The
> complex scenarios below apply only to legacy-data migrations.

| Step                           | Reversible? | Notes                                                                          |
| ------------------------------ | ----------- | ------------------------------------------------------------------------------ |
| 1. programs                    | ✅          | `DROP TABLE` — no dependencies yet                                             |
| 2. year_levels                 | ✅          | `DROP TABLE` — CASCADE only to programs (safe)                                 |
| 3. courses + course_offerings  | ⚠️          | **Backup first**. New table + data migration; drop offering rows + revert columns on rollback |
| 4. course_professors           | ✅          | `DROP TABLE`                                                                   |
| 5. enrollments.semester+offering | ⚠️          | **Backup first**. Data loss on rollback                                        |
| 6. sessions extend             | ✅          | Columns + regular column (no STORED expression); reversible                    |
| 7. attendance_records          | ⚠️          | **Backup first**. Enum data migration; rollback maps `present→valid`           |
| 8. new tables                  | ✅          | `DROP TABLE`                                                                   |
| 9. students face + drop course | ⚠️          | **Backup first**. Legacy `course` string unrecoverable after drop              |

---

## Staging-First Rule

> For greenfield deployments, this is not needed — `alembic upgrade head` on a fresh
> database is sufficient. The staging-first approach applies to legacy-data migrations
> where production data must be preserved.

1. **Always test migrations on staging** (copy of production DB) before production.
2. Run `alembic upgrade head` on staging; verify all tables/columns match §6 exactly.
3. Run application smoke tests against migrated schema.
4. Only then promote to production with maintenance window.

---

## Verification Checklist (per §6 Column-for-Column)

After all migrations, verify:

- [ ] `programs`: id, code(UK), name, description, total_years, is_active, created_at, updated_at
- [ ] `year_levels`: id, program_id(FK CASCADE), year_number, label, term_structure(JSONB), sort_order, UNIQUE(program_id, year_number)
- [ ] `courses`: course_code(UK), course_name, units, session_duration_hours, is_active, timestamps (no FKs — template only)
- [ ] `course_offerings`: course_id(FK), program_id(FK), year_level_id(FK), semester, academic_year, schedule/classroom fields, windows, is_active, timestamps, UNIQUE(course_id, program_id, semester, academic_year)
- [ ] `course_professors`: composite PK(offering_id, professor_id, effective_from), effectiveness dates, is_primary, semester, assigned_by, assigned_at
- [x] `enrollments`: offering_id NOT NULL, semester NOT NULL, academic_year NOT NULL, UNIQUE(student_id, offering_id, academic_year), validated against year_level.term_structure
- [ ] `sessions`: offering_id, professor_id FK → professors, duration/windows/scheduled/expires_at(regular column set by service layer)/override coords, CHECK constraint; course_id DROPPED
- [ ] `attendance_records`: evidence, face_score, scanned_via, original_status, excuse_*, UNIQUE not needed
- [ ] `excuse_requests`: all columns, status enum, initiated_by/via
- [ ] `student_risk_scores`: features JSONB, computed_day DATE, UNIQUE on (student_id, offering_id, semester, computed_day)
- [ ] `backup_log`: all columns including sha256, key_version; status = started/completed/failed
- [ ] `students`: year_level_id FK → year_levels; section retained (snapshot per D2); face_embedding(BYTEA), face_enrolled_at, face_embedding_version; legacy `course` DROPPED (no program_id)
- [ ] All enums in code match §6 (ValidationStatus expanded, etc.)

