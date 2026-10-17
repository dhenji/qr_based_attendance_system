# At-Risk Student Prediction Model

> **Decisions covered:** D35

## 1. Overview

The at-risk prediction system identifies students likely to fail or disengage based
on attendance patterns. The MVP uses **heuristic thresholds** (env-configurable);
a future upgrade to logistic regression will keep the identical feature vector.

Key properties:

- Runs as a **nightly batch job** at 02:00 (configurable via `RISK_BATCH_CRON`).
- Writes results to `student_risk_scores` table.
- Manual refresh endpoint available (admin-only).
- Expected sessions derived from the offering and its term: `term_weeks(year_level.term_structure, offering.semester) × offering.sessions_per_week` (D35, term-scoped per D86).

---

## 2. Feature Definitions

For each (student, offering, semester) tuple, the batch job computes:

### 2.1 Expected Sessions

```
expected_sessions = term_weeks(year_level.term_structure, offering.semester) × offering.sessions_per_week
```

Example: a 3-unit course meeting 2×/week over a 16-week term = 32 expected sessions.

### 2.2 Absence Rate

```
absence_rate = count(absent records for student+offering+semester) / expected_sessions
```

Only **`absent`** records are counted in the numerator — `absent_count =
count(validation_status == 'absent')`, computed over records whose
`validation_status != 'rejected'` (`batch.py:91-95,159`). Rejected rows are
dropped entirely (`_usable_records`). `absent`, `late` and `excused` are **not**
included in the numerator: `late` and `excused` are resolved attendance
(handled by the student), and `pending` rows are mid-validation.

The denominator is **not** record count. It is
`expected_sessions = term_weeks(year_level.term_structure, offering.semester) × offering.sessions_per_week`
(`batch.py::_load_expected_by_offering`) — the number of sessions the course scheduled. Records with
any `validation_status` simply mean the student had (or did not have) a row for
one of those sessions; "pending" rows sit nowhere in that framing because
`expected_sessions` derives from course metadata, not from rows on file.

### 2.3 Maximum Consecutive Streak

```
max_streak = longest run of consecutive absent records
```

Computed by ordering attendance records by session date and counting consecutive
`absent` statuses. A `late` or `excused` record breaks the streak. A `pending`
record does NOT break the streak (treated as unknown — conservative).

### 2.4 Sync Lag (Pending Records)

```
sync_lag = count(attendance_records WHERE sync_status = 'pending'
                 AND timestamp < now() - interval '24 hours')
```

Count of attendance records still awaiting sync (offline scans not yet
drained); only records pending in `sync_status` and older than 24 hours count.

Students with many unresolved pending records may have device issues or
deliberate sync avoidance.

### 2.5 Four-Week Trend Slope

```
trend_slope = linear regression slope of weekly absence counts over last 4 weeks
```

Computed by bucketing attendance records into weekly bins (Monday–Sunday),
counting absences per week, and fitting a line. A negative slope indicates
improving attendance; a positive slope indicates worsening attendance.

| Slope Value | Interpretation                                                                                                               |
| ----------- | ---------------------------------------------------------------------------------------------------------------------------- |
| < −0.05     | Strongly improving (D35 medium-risk trigger — unusually fast improvement may indicate data issues or disengagement patterns) |
| −0.05 to 0  | Stable or slightly improving                                                                                                 |
| 0 to +0.05  | Slightly worsening                                                                                                           |
| > +0.05     | Strongly worsening                                                                                                           |

---

## 3. Heuristic Decision Table

The model evaluates features in the following order. **First match wins** —
higher-severity rules are checked first.

| Priority | Condition                                 | Risk Level | Env Variable               | Threshold                      |
| -------- | ----------------------------------------- | ---------- | -------------------------- | ------------------------------ |
| 1        | `absence_rate > RISK_ABSENCE_RATE_HIGH`   | **high**   | `RISK_ABSENCE_RATE_HIGH`   | `0.30`                         |
| 2        | `max_streak >= RISK_STREAK_GAPS_HIGH`     | **high**   | `RISK_STREAK_GAPS_HIGH`    | `3`                            |
| 3        | `absence_rate > RISK_ABSENCE_RATE_MEDIUM` | **medium** | `RISK_ABSENCE_RATE_MEDIUM` | `0.15`                         |
| 4        | `sync_lag >= RISK_SYNC_LAG_HIGH`          | **medium** | `RISK_SYNC_LAG_HIGH`       | `5`                            |
| 5        | `trend_slope < RISK_TREND_NEGATIVE`       | **medium** | `RISK_TREND_NEGATIVE`      | `−0.05` (check: slope < −0.05) |
| 6        | None of the above                         | **low**    | —                          | —                              |

### 3.1 Risk Probability

The `risk_probability` field is a synthetic score (0.0–1.0) derived from the
features for sorting/display. It is NOT a true probability in the ML sense.

```
risk_probability = (
    0.40 × min(absence_rate / RISK_ABSENCE_RATE_HIGH, 1.0) +
    0.25 × min(max_streak / RISK_STREAK_GAPS_HIGH, 1.0) +
    0.15 × min(sync_lag / RISK_SYNC_LAG_HIGH, 1.0) +
    0.20 × min(max(trend_slope, 0) / 0.10, 1.0)
)
```

Clamped to [0.0, 1.0]. Higher = more at-risk.

---

## 4. Output Schema: `student_risk_scores`

```sql
CREATE TABLE student_risk_scores (
    id              BIGSERIAL PRIMARY KEY,
    student_id      BIGINT NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
    offering_id     BIGINT NOT NULL REFERENCES course_offerings(id) ON DELETE RESTRICT,
    semester        VARCHAR(20) NOT NULL,
    risk_probability NUMERIC(5,4) NOT NULL,   -- 0.0000–1.0000
    risk_level      VARCHAR(10) NOT NULL      -- 'low' | 'medium' | 'high'
                    CHECK (risk_level IN ('low','medium','high')),
    features        JSONB NOT NULL,           -- full feature snapshot
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    computed_day    DATE NOT NULL,            -- set by service: computed_at.date() (D50)
);
CREATE UNIQUE INDEX uq_student_risk_scores_student_offering_semester_day
    ON student_risk_scores (student_id, offering_id, semester, computed_day);
```

Matches `analytics/model.py` (`BigInteger` FKs with `ondelete='RESTRICT'`, a CHECK constraint,
and a surrogate **unique index** rather than an inline `UNIQUE` constraint). The staging twin,
`student_risk_scores_staging`, has the same columns **plus** `promoted_at TIMESTAMPZ NULL`, so
it is identical schema *except* for that column (see §5.4).

### 4.1 Features JSONB Structure

```json
{
  "expected_sessions": 32,
  "actual_sessions": 24,
  "absent_count": 8,
  "absence_rate": 0.3333,
  "max_streak": 4,
  "sync_lag": 2,
  "weekly_absences": [2, 3, 1, 2],
  "trend_slope": 0.0833,
  "present_count": 12,
  "late_count": 3,
  "excused_count": 1
}
```

---

## 5. Batch Job Specification

### 5.1 Schedule

```
RISK_BATCH_CRON="0 2 * * *"    # daily at 02:00 **scheduler** time (UTC by
                                # default via SCHEDULER_TIMEZONE)
```

### 5.2 Execution Flow

```
Scheduler triggers at 02:00
    │
    ▼
BEGIN BATCH
    │
    ├─ 1. Load all active enrollments
    │     SELECT e.student_id, e.offering_id, e.semester,
    │            co.sessions_per_week, yl.term_structure
    │     FROM enrollments e
    │     JOIN course_offerings co ON e.offering_id = co.id
    │     JOIN year_levels yl ON co.year_level_id = yl.id
    │     WHERE co.is_active = true
    │     -- weeks resolved per offering: term_weeks(yl.term_structure, co.semester)
    │
    ├─ 2. For each (student, offering, semester):
    │     a. Fetch attendance records for student+offering+semester
    │     b. Compute features (§2)
    │     c. Evaluate heuristic rules (§3)
    │     d. Compute risk_probability (§3.1)
    │     e. UPSERT INTO student_risk_scores
     │        (ON CONFLICT (student_id, offering_id, semester, computed_day)
    │         DO UPDATE SET risk_probability = ..., risk_level = ..., features = ...,
    │                       computed_at = NOW())
    │
    ├─ 3. Log batch summary
    │     { total_enrollments: N, high: X, medium: Y, low: Z, duration_ms: T }
    │
    └─ END BATCH
```

### 5.3 Runtime Budget

- Target: complete within 5 minutes for 10,000 active enrollments.
- If exceeded, log a warning but do not abort — partial results are still written.
- Optimization: batch SQL queries (fetch all attendance records for the cohort in
  one query, compute in Python) rather than per-student queries.
- Scoring is order-preservingly sharded across a `ThreadPoolExecutor` of
  `RISK_BATCH_WORKERS` threads in chunks of `RISK_BATCH_CHUNK_SIZE`
  (`config.py:67`, `batch.py:474`, `:303-308`) — these shards run concurrently
  but the merge into the output list is order-preserving, so the result matches a
  single-threaded run (ADR-067, covered by
  `test_risk_batch_workers_match_serial_output`).

### 5.4 Dry-Run Mode

Set `RISK_BATCH_DRY_RUN=true` to:

1. Compute all features and risk levels as normal.
2. Write to a staging table, `student_risk_scores_staging` — same columns as the
   live table **plus `promoted_at TIMESTAMPTZ NULL`** (set when a dry-run batch is
   promoted; mirrored DDL documented next to `student_risk_scores`, §4).
3. Log the summary without affecting production data.
4. Admin can review staging results via `GET /admin/analytics/risk-staging` and
   promote them via `POST /admin/analytics/risk-staging/promote`.

---

## 6. Refresh Endpoint

```
POST /admin/analytics/refresh-risk
```

- **Role:** Admin only.
- Triggers the same batch computation as the nightly job but for a **single**
  (student, offering, semester) tuple or all enrollments if no filter provided.
- Query params (all optional):
  - `student_id` — refresh one student across all their offerings
  - `offering_id` — refresh all students in a course offering
  - `semester` — filter by semester (required if `offering_id` provided)
- Returns: `{ processed: N, high: X, medium: Y, low: Z, duration_ms: T }`
- Rate-limited: max 1 call per 60 seconds **per IP** (`rate_limit(1, 60)` defaults to the
  IP key, `analytics/router.py:155`), not per admin.

---

## 7. Worked Numeric Example

### Scenario

**Student:** Maria Santos, ID 24-2111
**Course:** CS101 — Introduction to Programming (BSCS Year 1)
**Semester:** 1st_sem
**Course metadata:** term `1st_sem` `weeks = 16`, `sessions_per_week = 2`
**Expected sessions:** 16 × 2 = 32

### Attendance Record (last 12 weeks, 24 sessions)

The table below shows weeks 1–6 (12 sessions). Weeks 7–12 (12 additional
sessions) are all `absent` — Maria stopped attending after week 6.

| Week | Session 1 | Session 2 | Status          |
| ---- | --------- | --------- | --------------- |
| 1    | present   | present   | ✅✅            |
| 2    | present   | late      | ✅⏰            |
| 3    | absent    | absent    | ❌❌            |
| 4    | absent    | absent    | ❌❌            |
| 5    | present   | absent    | ✅❌            |
| 6    | absent    | present   | ❌✅            |
| 7–12 | absent    | absent    | ❌❌ (×6 weeks) |

**Totals (of 24 sessions occurred):**

- present: 5
- late: 1
- absent: 18
- excused: 0
- pending: 0

### Feature Computation

```
expected_sessions = 16 × 2 = 32
sessions_occurred = 24  (12 weeks × 2; 8 weeks remaining in semester)
```

```
absence_rate = 18 / 32 = 0.5625

max_streak: all 24 session records in order:
  present, present, present, late,
  absent, absent, absent, absent, present, absent, absent, present,
  absent, absent, absent, absent, absent, absent, absent, absent,
  absent, absent, absent, absent

  The longest consecutive run of 'absent' is 12 (sessions 13–24,
  weeks 7–12 — Maria stopped attending entirely).

  max_streak = 12

sync_lag = 0 (all records resolved)

weekly_absences (last 4 weeks — weeks 9–12):
  Week 9: 2, Week 10: 2, Week 11: 2, Week 12: 2
  x = [1, 2, 3, 4], y = [2, 2, 2, 2]
  slope = (4×(1×2 + 2×2 + 3×2 + 4×2) - (1+2+3+4)×(2+2+2+2)) / (4×(1+4+9+16) - 10²)
        = (4×(2+4+6+8) - 10×8) / (120 - 100)
        = (4×20 - 80) / 20
        = (80 - 80) / 20
        = 0

  trend_slope = 0.00 (stable — consistently 2 absences/week)
```

### Heuristic Evaluation

| Priority | Condition           | Check         | Result      |
| -------- | ------------------- | ------------- | ----------- |
| 1        | absence_rate > 0.30 | 0.5625 > 0.30 | ✅ **HIGH** |

**Risk level: HIGH** (matched at priority 1).

### Risk Probability

```
risk_probability = (
    0.40 × min(0.5625 / 0.30, 1.0) +     = 0.40 × 1.0 = 0.4000
    0.25 × min(12 / 3, 1.0) +             = 0.25 × 1.0 = 0.2500
    0.15 × min(0 / 5, 1.0) +              = 0.15 × 0.0 = 0.0000
    0.20 × min(max(0.00, 0) / 0.10, 1.0) = 0.20 × 0.0 = 0.0000
) = 0.6500
```

### Output Row

```json
{
  "student_id": 42,
  "offering_id": 7,
  "semester": "1st_sem",
  "risk_probability": 0.65,
  "risk_level": "high",
  "features": {
    "expected_sessions": 32,
    "actual_sessions": 24,
    "absent_count": 18,
    "absence_rate": 0.5625,
    "max_streak": 12,
    "sync_lag": 0,
    "weekly_absences": [2, 2, 2, 2],
    "trend_slope": 0.0,
    "present_count": 5,
    "late_count": 1,
    "excused_count": 0
  },
  "computed_at": "2026-08-25T02:00:00Z"
}
```

**Note:** Maria is flagged HIGH due to the high absence rate (56%) and a long
consecutive streak (12 sessions). The flat trend (slope = 0.00) shows she
consistently misses 2 sessions/week with no improvement — valuable context for
the professor's intervention conversation.

---

## 8. ML Upgrade Path (D35 Tail)

The current heuristic model and the future logistic regression model share the
**identical feature vector**:

```json
{
  "absence_rate": float,
  "max_streak": int,
  "sync_lag": int,
  "trend_slope": float
}
```

### Upgrade Steps

1. **Collect labeled data:** As professors use the system, manually tag students
   as "at-risk" or "not at-risk" in the admin dashboard. Store labels in a
   `risk_labels` table (future/planned — not part of the current schema).
2. **Train logistic regression:** Use scikit-learn or similar; 4-feature input,
   binary output. No GPU required.
3. **Shadow mode:** Run both heuristic and LR models; compare outputs for 30 days
   without acting on LR results.
4. **Promote LR:** Replace heuristic scoring with LR probability; keep heuristic
   as fallback if LR model file is missing.
5. **Feature expansion (future):** Same vector can accept additional features
   (e.g., assignment submission rates, quiz scores) without changing the pipeline.

---

## 9. Cross-References

| Topic                   | Document                                              |
| ----------------------- | ----------------------------------------------------- |
| Database schema         | [migration-strategy.md](migration-strategy.md)        |
| Data flow (batch job)   | [data-flow.md](data-flow.md)                          |
| Wireframes: at-risk tab | `docs/design/wireframes.md` (section 4.7 At-Risk tab) |
| API: refresh endpoint   | [api-contracts.md](api-contracts.md)                  |
| Admin manual            | `docs/guides/admin-manual.md`                         |
