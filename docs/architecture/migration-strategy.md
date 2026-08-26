# Migration Strategy: Current → Target Schema

> Ordered Alembic migration plan from the current 7-feature schema to the §6 target schema.
> **Alembic import rule:** Every new model (`features/program/model.py`, plus new tables in `analytics`, `excuse`, `system` features) MUST be imported in `backend/alembic/env.py` alongside the existing eight feature imports so autogenerate sees them in `target_metadata`. Face enrollment columns live on `features.student/model.py` — no separate import needed. Run alembic from `backend/`.

---

## Current Schema (Baseline)

Tables from existing models (Alembic head `996b2fb85c6f`):

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

## Target Schema (Reference §6)

New tables: `programs`, `year_levels`, `course_professors`, `excuse_requests`, `student_risk_scores`, `backup_log`
Modified tables: `courses` (+9 cols, +2 FKs), `enrollments` (+semester), `sessions` (+7 cols, STORED expires_at), `attendance_records` (+9 cols, expanded status enum), `students` (+3 face cols, drop legacy `course`)

---

## Migration Steps (Ordered)

### Step 1: Create `programs` Table + Seed Defaults

**Migration:** `alembic revision --autogenerate -m "create programs table and seed defaults"`

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

**Seed data (per D3 examples):**

| code  | name                                           | total_years | term_structure (per year_level)                                                                         |
| ----- | ---------------------------------------------- | ----------- | ------------------------------------------------------------------------------------------------------- |
| BSCS  | Bachelor of Science in Computer Science        | 4           | Y1: [1st_sem, 2nd_sem]; Y2: [1st_sem, 2nd_sem]; Y3: [1st_sem, 2nd_sem, midyear]; Y4: [1st_sem, 2nd_sem] |
| BSIT  | Bachelor of Science in Information Technology  | 4           | Y1-4: [1st_sem, 2nd_sem]                                                                                |
| BSECE | Bachelor of Science in Electronics Engineering | 5           | Y1-5: [1st_sem, 2nd_sem]                                                                                |

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

**Seed:** Create year levels for each seeded program per their `total_years`, populate `term_structure` from D3 examples.

**Rollback:** `DROP TABLE year_levels` (CASCADE drops nothing yet)

---

### Step 3: Extend `courses` — Add FKs + Metadata Columns

**Migration:** `alembic revision --autogenerate -m "extend courses with program/year_level FKs and scheduling metadata"`

**Changes to `features/course/model.py`:**

```python
class Course(Base):
    # Existing: id, course_code, course_name, classroom_lat, classroom_lng, schedule
    # NEW:
    program_id = BigInteger FK → programs.id RESTRICT
    year_level_id = BigInteger FK → year_levels.id RESTRICT
    units = Integer
    sessions_per_week = Integer
    session_duration_hours = Numeric(3,1)
    semester_weeks = Integer
    schedule_days = String(10)  -- "MWF", "TTh", etc.
    schedule_start_time = Time
    schedule_end_time = Time
    classroom_name = String(100)
    default_present_window_minutes = Integer default 5
    default_late_window_minutes = Integer default 10
    is_active = Boolean default True
    created_at, updated_at = TimestampMixin
```

**Backfill strategy:**

1. Add new columns as **nullable** first
2. For each existing `courses` row:
   - Infer `program_id`/`year_level_id` from `students` enrolled in that course (most common program/year)
   - Parse legacy `schedule` string to extract days/times if possible; else default
   - Set defaults for units (3), sessions_per_week (2), session_duration_hours (1.5), semester_weeks (18), windows (5/10)
3. After backfill: `ALTER COLUMN ... SET NOT NULL` on FKs and critical metadata
4. Drop legacy `schedule` column (or keep as deprecated text)

**Rollback:** Revert columns to nullable, drop NOT NULL, restore `schedule` if dropped. **Backup before migrate.**

---

### Step 4: Create `course_professors` Table

**Migration:** `alembic revision --autogenerate -m "create course_professors many-to-many with effectiveness dates"`

**Model:** `features/professor/model.py` (extend) or new `features/course_assignment/model.py`

```python
class CourseProfessor(Base):
    __tablename__ = "course_professors"
    course_id = BigInteger FK → courses.id CASCADE
    professor_id = BigInteger FK → professors.id CASCADE
    is_primary = Boolean default False
    effective_from = Date NOT NULL
    effective_to = Date NULL  -- NULL = ongoing
    semester = String(20)  -- validated against year_level.term_structure
    assigned_by = BigInteger FK → users.id
    assigned_at = DateTime(timezone=True) default now()
    PK(course_id, professor_id, effective_from)
```

**Service-layer rule (enforced in Python, not DB):** Reject overlapping `[effective_from, effective_to)` ranges for same `(course_id, professor_id)`.

**Migrate implied assignments:** For each existing `sessions` row, create a `course_professors` entry with `effective_from = session.created_at::date`, `effective_to = NULL`, `semester = enrollment.semester` (or default), `is_primary = true`.

**Rollback:** `DROP TABLE course_professors`

---

### Step 5: Extend `enrollments` — Add `semester`

**Migration:** `alembic revision --autogenerate -m "add semester to enrollments with backfill"`

**Change:** Add `semester VARCHAR(20)` nullable → backfill default `'1st_sem'` → set NOT NULL.

**Validation:** Application logic validates `semester` against `student.year_level.term_structure` (via `student.year_level` → `year_levels.term_structure`).

**Rollback:** Drop column (data loss — backup first)

---

### Step 6: Extend `sessions` — Duration, Windows, Scheduled Times, Override

**Migration:** `alembic revision --autogenerate -m "extend sessions with duration windows scheduled times and classroom override"`

**Changes to `features/session/model.py`:**

```python
class Session(Base):
    # Existing: id, course_id, professor_id, session_code, expires_at, classroom_radius_meters
    # NEW:
    duration_minutes = Integer
    present_window_minutes = Integer
    late_window_minutes = Integer
    CHECK (present_window_minutes + late_window_minutes <= duration_minutes)
    scheduled_start_time = DateTime(timezone=True)  -- copied from course at open
    scheduled_end_time = DateTime(timezone=True)    -- copied from course at open
    expires_at = DateTime(timezone=True)  -- STORED: LEAST(created_at + duration_minutes * interval '1 min', scheduled_end_time)
    classroom_name = String(100) NULL
    classroom_lat = Float NULL
    classroom_lng = Float NULL
```

**Backfill:**

- `duration_minutes` = `course.session_duration_hours * 60` (default 90)
- `present_window_minutes` = `course.default_present_window_minutes` (5)
- `late_window_minutes` = `course.default_late_window_minutes` (10)
- `scheduled_start_time/end_time` = course schedule for that day (compute from `schedule_days` + date)
- `expires_at` = recomputed via STORED expression (PostgreSQL `GENERATED ALWAYS AS ... STORED`)

**Rollback:** Drop new columns. STORED column requires `ALTER TABLE ... ALTER COLUMN expires_at DROP EXPRESSION` first.

---

### Step 7: Extend `attendance_records` — Evidence, Excuse, Expanded Status

**Migration:** `alembic revision --autogenerate -m "extend attendance_records with evidence excuse and expanded status enum"`

**Changes to `features/attendance/model.py`:**

```python
class Attendance(Base):
    # Existing: id, student_id, session_id, timestamp, gps_lat, gps_lng, validation_status, sync_status
    # NEW:
    liveness_evidence = JSONB  -- {gps, liveness_scores, face_match_score, scanned_at, device_info, rejection_reason?}
    face_match_score = Numeric(5,4)  -- cosine similarity
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
    course_id = BigInteger FK → courses.id
    semester = String(20)
    risk_probability = Numeric(5,4)
    risk_level = String(10)  -- 'low' | 'medium' | 'high'
    features = JSONB  -- {absence_rate, max_streak, sync_lag, trend_slope, expected_sessions}
    computed_at = DateTime(timezone=True) default now()
    UNIQUE(student_id, course_id, semester, computed_at::date)
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
    status = String(20)  -- 'success' | 'failed'
    error = Text NULL
```

**Rollback:** `DROP TABLE excuse_requests, student_risk_scores, backup_log`

---

### Step 9: Extend `students` — Face Columns + Drop Legacy `course`

**Migration:** `alembic revision --autogenerate -m "add face embedding columns to students and drop legacy course string"`

**Changes to `features/student/model.py`:**

```python
class Student(Base):
    # Existing: id, user_id, student_id, email, names, course (string), section, year_level, is_active
    # NEW:
    face_embedding = LargeBinary NULL  -- BYTEA: encrypted JSON blob
    face_enrolled_at = DateTime(timezone=True) NULL
    face_embedding_version = Integer default 0
    # DROP: course (string) — after backfill to FK-based courses/enrollments
```

**Backfill legacy `course` string:**

1. For each student, parse `student.course` string (e.g., "BSCS-1")
2. Match to `programs.code` + `year_levels.year_number`
3. Ensure enrollment exists for that course in the correct program/year
4. After verification, drop `course` column

**Rollback:** Recreate `course` VARCHAR column, restore from backup. Face columns dropped.

---

## Alembic Import Rule (Critical)

**File:** `backend/alembic/env.py`

Current imports (lines 8–15):

```python
import features.attendance.model  # noqa: F401
import features.auth.model  # noqa: F401
import features.course.model  # noqa: F401
import features.enrollment.model  # noqa: F401
import features.professor.model  # noqa: F401
import features.session.model  # noqa: F401
import features.student.model  # noqa: F401
import features.sync.model  # noqa: F401
```

**After adding new features, MUST add:**

```python
import features.program.model  # noqa: F401        # programs, year_levels
import features.course_assignment.model  # noqa: F401  # course_professors (or professor.model if extended)
import features.excuse.model  # noqa: F401        # excuse_requests
import features.analytics.model  # noqa: F401      # student_risk_scores
import features.system.model  # noqa: F401        # backup_log
# face_enrollment columns live on features.student.model — no separate import needed
```

**Run alembic from `backend/` directory** so `features.*` imports resolve.

---

## Rollback Strategy Summary

| Step                           | Reversible? | Notes                                                                          |
| ------------------------------ | ----------- | ------------------------------------------------------------------------------ |
| 1. programs                    | ✅          | `DROP TABLE` — no dependencies yet                                             |
| 2. year_levels                 | ✅          | `DROP TABLE` — CASCADE only to programs (safe)                                 |
| 3. courses extend              | ⚠️          | **Backup first**. Data migration; NOT NULL after backfill makes rollback lossy |
| 4. course_professors           | ✅          | `DROP TABLE`                                                                   |
| 5. enrollments.semester        | ⚠️          | **Backup first**. Data loss on rollback                                        |
| 6. sessions extend             | ✅          | Columns + STORED expression; reversible                                        |
| 7. attendance_records          | ⚠️          | **Backup first**. Enum data migration; rollback maps `present→valid`           |
| 8. new tables                  | ✅          | `DROP TABLE`                                                                   |
| 9. students face + drop course | ⚠️          | **Backup first**. Legacy `course` string unrecoverable after drop              |

---

## Staging-First Rule

1. **Always test migrations on staging** (copy of production DB) before production.
2. Run `alembic upgrade head` on staging; verify all tables/columns match §6 exactly.
3. Run application smoke tests against migrated schema.
4. Only then promote to production with maintenance window.

---

## Verification Checklist (per §6 Column-for-Column)

After all migrations, verify:

- [ ] `programs`: id, code(UK), name, description, total_years, is_active, created_at, updated_at
- [ ] `year_levels`: id, program_id(FK CASCADE), year_number, label, term_structure(JSONB), sort_order, UNIQUE(program_id, year_number)
- [ ] `courses`: all §6 columns including FKs, metadata, windows, is_active, timestamps
- [ ] `course_professors`: composite PK, effectiveness dates, is_primary, semester, assigned_by, assigned_at
- [ ] `enrollments`: semester NOT NULL, validated against year_level.term_structure
- [ ] `sessions`: duration/windows/scheduled/expires_at(STORED)/override coords, CHECK constraint
- [ ] `attendance_records`: evidence, face_score, scanned_via, original_status, excuse_*, UNIQUE not needed
- [ ] `excuse_requests`: all columns, status enum, initiated_by/via
- [ ] `student_risk_scores`: features JSONB, UNIQUE on (student_id, course_id, semester, date)
- [ ] `backup_log`: all columns including sha256, key_version
- [ ] `students`: face_embedding(BYTEA), face_enrolled_at, face_embedding_version; legacy `course` DROPPED
- [ ] All enums in code match §6 (ValidationStatus expanded, etc.)

