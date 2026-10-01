# Excuse Workflow Architecture

> **Decisions covered:** D20–D24

## 1. Overview

Excused attendance is a **first-class status** (D20) with a mandatory reason and
full audit trail. The system supports three distinct initiation paths (D21), each
with different permission models and evidence requirements. All paths ultimately
write to the `excuse_requests` table and may mutate
`attendance_records.validation_status`.

Key properties:

- Excusing **overrides** the scanned status (D22): if a late-scanning student is
  excused, final status = `excused` while `original_status` preserves what actually
  happened.
- Excused students are treated as **present** for compliance rate calculations (D36).
- Bulk "Excuse All Absent" is supported per session (D23) with idempotency.
- Evidence attachments use S3-compatible storage; the DB stores URL references
  only (D24).

---

## 2. State Machine

```
                    ┌──────────────────────────────────────────┐
                    │              excuse_requests              │
                    │                                          │
  ┌───────────┐    │  ┌───────────┐    ┌──────────────────┐   │
  │  (no row)  │───┼─▶│  pending   │───▶│    approved      │   │
  └───────────┘    │  └───────────┘    └──────────────────┘   │
       ▲           │       │                    ▲              │
       │           │       │                    │              │
       │           │       ▼                    │              │
       │           │  ┌───────────┐             │              │
       │           │  │ rejected   │             │              │
       │           │  └───────────┘             │              │
       │           └──────────────────────────┘              │
       │                                                        │
       │    Path (a): quick-excuse ────────────────────────────┘
       │    (prof marks student excused; row created + approved atomically)
       │
       │    Path (b): prof_with_evidence ──────────────────────┘
       │    (prof uploads evidence; row created + approved atomically)
       │
       └──── Path (c): request (student-initiated) ──▶ pending ──▶ approved/rejected
```

### 2.1 Transition Rules

| Transition             | Who                            | Preconditions                                                                          | Side Effects                                                                                                                        |
| ---------------------- | ------------------------------ | -------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| (create) → `approved`  | Professor (quick)              | Student has absent/late record for session; professor has active assignment for course | `excuse_requests` row created with `status=approved`; `attendance_records.validation_status` mutated to `excused`; `original_status` preserved |
| (create) → `approved`  | Professor (prof_with_evidence) | Same as above + at least 1 attachment uploaded                                         | Same as quick + `attachment_urls` populated                                                                                         |
| (create) → `pending`   | Student (request)              | Student has absent/late/rejected record for session; reason text provided              | `excuse_requests` row created with `status=pending`; no mutation to `attendance_records` yet                                        |
| `pending` → `approved` | Professor (review)             | Professor has active assignment for the course; `reviewed_by` set                      | `attendance_records.validation_status` mutated to `excused`; `original_status` preserved                                                       |
| `pending` → `rejected` | Professor (review)             | Same as above + optional `review_notes`                                                | No mutation to `attendance_records`; student notified                                                                               |

---

## 3. Three Initiation Paths (D21)

### Path A: Professor Quick-Excuse

**When:** Professor notices a student was absent/late and has direct knowledge
(e.g., student informed professor after class).

**Flow:**

```
Professor opens session active view (3.3) or attendance list (3.4)
    │
    ▼
Clicks [📝 Excuse] on absent/late student row
    │
    ▼
Quick-excuse modal opens
    ├─ Required: reason (text, min 10 chars)
    ├─ Optional: notes (internal)
    │
    ▼
Professor submits
    │
    ▼
Server atomically:
    1. INSERT INTO excuse_requests
       (student_id, session_id, initiated_by='professor',
        initiated_via='quick', reason=..., status='approved',
        reviewed_by=prof_user_id, reviewed_at=NOW())
    2. UPDATE attendance_records
       SET original_status = validation_status,
           validation_status = 'excused',
           excuse_reason = ...,
           excused_by = prof_user_id,
           excused_at = NOW(),
           excuse_type = 'quick',
           excuse_request_id = <new row id>
       WHERE student_id = ... AND session_id = ...
    3. RETURN success
```

**Permission:** Any professor with an active `course_professors` assignment
(D7–D9) for the session's course may quick-excuse.

### Path B: Professor-Initiated with Evidence

**When:** Professor holds physical proof (e.g., excuse letter, medical certificate)
and files + approves immediately.

**Flow:**

```
Professor opens excuse action (from session view or attendance list)
    │
    ▼
Selects "File Excuse with Evidence"
    │
    ▼
Excuse form opens
    ├─ Required: reason (text)
    ├─ Required: attachment(s) — upload to S3-compatible storage
    │   ├─ Allowed types: PDF, JPG, PNG, HEIC
    │   ├─ Max size: ATTACHMENTS_MAX_BYTES (default 5 MiB)
    │   └─ Returns presigned URLs
    │
    ▼
Professor submits
    │
    ▼
Server atomically:
    1. INSERT INTO excuse_requests
       (student_id, session_id, initiated_by='professor',
        initiated_via='prof_with_evidence', reason=...,
        attachment_urls=<JSONB array of URLs>,
        status='approved', reviewed_by=prof_user_id, reviewed_at=NOW())
    2. UPDATE attendance_records (same mutation as Path A, excuse_type='prof_with_evidence')
    3. RETURN success
```

**Permission:** Same as Path A — any assigned professor for the course.

### Path C: Student-Initiated Request

**When:** Student was absent/late/rejected and wants to submit an excuse with
evidence for professor review.

**Flow:**

```
Student opens history (2.7) → clicks [Request Excuse] on eligible row
    │
    ▼
Excuse request form opens
    ├─ Required: reason (text, min 20 chars)
    ├─ Required: at least 1 attachment (presigned URL upload)
    │
    ▼
Student submits
    │
    ▼
Server:
    1. INSERT INTO excuse_requests
       (student_id, session_id, initiated_by='student',
        initiated_via='request', reason=...,
        attachment_urls=..., status='pending')
    2. No mutation to attendance_records (status stays as-is)
    3. Notify professor(s) assigned to course
    4. RETURN { request_id, status: 'pending' }
```

**Permission:** The student whose attendance record is being excused. Record must
be in a scannable state (absent, late, or rejected).

**Professor review:**

```
Professor views pending excuse requests (3.4 filter or /professor/excuse-requests)
    │
    ▼
Reviews reason + attachments
    │
    ├─ Approve → server mutates attendance_records (same as Path A/B)
    │            excuse_request.status → 'approved'
    │
    └─ Reject → excuse_request.status → 'rejected'
                + review_notes (optional)
                Student notified
```

---

## 4. Swimlane Diagrams

### 4.1 Path A: Quick-Excuse

```
  Professor               Server                  DB
     │                      │                      │
     │  [📝 Excuse] click   │                      │
     │─────────────────────▶│                      │
     │                      │  BEGIN TX            │
     │                      │─────────────────────▶│
     │                      │  INSERT excuse_req   │
     │                      │─────────────────────▶│
     │                      │  UPDATE attendance   │
     │                      │  SET original_status │
     │                      │  = validation_status │
     │                      │  validation_status = │
     │                      │  'excused'           │
     │                      │─────────────────────▶│
     │                      │  COMMIT              │
     │                      │─────────────────────▶│
     │  success             │                      │
     │◀─────────────────────│                      │
```

### 4.2 Path B: Professor with Evidence

```
  Professor               Server               S3 Storage          DB
     │                      │                     │                  │
     │  Upload attachments  │                     │                  │
     │─────────────────────▶│                     │                  │
     │  presigned URLs      │                     │                  │
     │◀─────────────────────│                     │                  │
     │                      │                     │                  │
     │  Submit excuse       │                     │                  │
     │─────────────────────▶│                     │                  │
     │                      │  BEGIN TX           │                  │
     │                      │──────────────────────────────────────▶│
     │                      │  INSERT excuse_req  │                  │
     │                      │  (attachment_urls)  │                  │
     │                      │──────────────────────────────────────▶│
     │                      │  UPDATE attendance  │                  │
     │                      │──────────────────────────────────────▶│
     │                      │  COMMIT             │                  │
     │                      │──────────────────────────────────────▶│
     │  success             │                     │                  │
     │◀─────────────────────│                     │                  │
```

### 4.3 Path C: Student Request

```
  Student                 Server                  DB              Professor
     │                      │                      │                  │
     │  POST /excuse-       │                      │                  │
     │  requests            │                      │                  │
     │─────────────────────▶│                      │                  │
     │                      │  INSERT excuse_req   │                  │
     │                      │  status='pending'    │                  │
     │                      │─────────────────────▶│                  │
     │  { id, pending }     │                      │                  │
     │◀─────────────────────│                      │                  │
     │                      │                      │   notify         │
     │                      │                      │─────────────────▶│
     │                      │                      │                  │
     │                      │        ... time passes ...              │
     │                      │                      │                  │
     │                      │  POST /excuse-       │                  │
     │                      │  requests/{id}/review│                  │
     │                      │  { action: approve } │◀─────────────────│
     │                      │─────────────────────▶│                  │
     │                      │  UPDATE excuse_req   │                  │
     │                      │  → approved          │                  │
     │                      │─────────────────────▶│                  │
     │                      │  UPDATE attendance   │                  │
     │                      │  validation_status → │                  │
     │                      │  'excused'           │                  │
     │                      │─────────────────────▶│                  │
     │                      │                      │   notify student │
     │                      │                      │─────────────────▶│
```

---

## 5. Bulk Excuse All Absent (D23)

### Endpoint

```
POST /professor/sessions/{session_id}/excuse-all-absent
Body: { "reason": "Class cancelled due to typhoon" }
```

### Algorithm

```
1. Validate professor has active assignment for session's course
2. BEGIN TX
3. SELECT all attendance_records WHERE session_id = ? AND validation_status = 'absent'
4. For each record:
   a. INSERT INTO excuse_requests
      (student_id, session_id, initiated_by='professor',
       initiated_via='quick', reason=..., status='approved',
       reviewed_by=prof_user_id, reviewed_at=NOW())
   b. UPDATE attendance_records
      SET original_status = 'absent',
          validation_status = 'excused',
          excuse_reason = ...,
          excused_by = prof_user_id,
          excused_at = NOW(),
          excuse_type = 'quick',
          excuse_request_id = <new id>
5. COMMIT TX
6. Return { excused_count: N }
```

### Idempotency

- If called twice for the same session with the same reason, the second call
  is a **no-op** for students already excused. Only students still marked
  `absent` (not yet processed) are excused.
- The server checks: `WHERE validation_status = 'absent'` — already-excused rows are
  skipped by the WHERE clause.
- Response always returns the count of **newly** excused students.

---

## 6. original_status Preservation (D22)

When an excuse is approved (any path), the `attendance_records` row is updated:

```sql
UPDATE attendance_records
SET
    original_status = validation_status, -- preserve what actually happened
    validation_status = 'excused',       -- override to excused
    excuse_reason = $1,
    excused_by = $2,
    excused_at = NOW(),
    excuse_type = $3,                -- attendance_records.excuse_type:
                                     -- 'quick' | 'prof_with_evidence' | 'request_approved'
                                     -- (distinct from excuse_requests.initiated_via,
                                     --  whose student path uses 'request')
    excuse_request_id = $4
WHERE student_id = $5 AND session_id = $6;
```

**Purpose:** Audit trail. A student who arrived late and was later excused will
show `validation_status = 'excused'` but `original_status = 'late'`, preserving
the factual record of what happened at scan time.

---

## 7. Attachment Handling (D24)

### Storage

- Attachments are stored in **S3-compatible storage** (Supabase Storage / R2 / S3;
  local filesystem in dev).
- Same storage backend as backups, controlled by `ATTACHMENTS_STORAGE_TYPE` env var.
- The database stores **URL references only** — never raw file bytes.

### Upload Flow

1. Client requests presigned upload URL(s) from server.
2. Client uploads file(s) directly to storage via presigned URL (bypasses server
   for the actual bytes).
3. Server records the final object URL(s) in `excuse_requests.attachment_urls`
   (JSONB array).
4. **Virus-scan hook point:** After upload completes, the server triggers an
   asynchronous virus scan (e.g., ClamAV sidecar, cloud function, or storage-provider
   native scanning). If the scan flags a file, the attachment URL is retained for
   audit but the excuse request is placed on hold with a `scan_failed` note in
   `review_notes`. The professor is notified to re-upload from a clean source.
   This hook is **pluggable** — deployments without a scanner simply skip it
   (no-op) and rely on manual review.

### Constraints

| Constraint                  | Value                                                                                         | Env Var                 |
| --------------------------- | --------------------------------------------------------------------------------------------- | ----------------------- |
| Max file size               | 5 MiB                                                                                         | `ATTACHMENTS_MAX_BYTES` |
| Allowed types               | PDF, JPG, PNG, HEIC                                                                           | Hardcoded (extendable)  |
| Max attachments per request | 5                                                                                             | Hardcoded               |
| Immutability                | Once uploaded, attachments are **never deleted** even if the excuse is rejected (audit trail) | —                       |

---

## 8. Notifications

| Event                          | Recipient             | Channel        | Content                                                                   |
| ------------------------------ | --------------------- | -------------- | ------------------------------------------------------------------------- |
| Student submits excuse request | Assigned professor(s) | In-app + email | "New excuse request from {name} for {course} — {session_date}"            |
| Professor approves excuse      | Student               | In-app + email | "Your excuse for {course} on {date} has been approved"                    |
| Professor rejects excuse       | Student               | In-app + email | "Your excuse for {course} on {date} was rejected. Reason: {review_notes}" |
| Bulk Excuse All                | All affected students | In-app (batch) | "You have been excused for {course} on {date}. Reason: {reason}"          |

**Implementation:** only the **email** half is built. Copy lives in
`features/excuse/notifications.py` (pure subject/body builders, one per event);
`features/excuse/service.py` resolves the recipients and hands the batch to
`shared.email.dispatch_emails`, which sends off the request thread on an executor
worker. Recipients are read from `users.email`, falling back to the
`students.email` / `professors.email` roster column for a profile with no linked
account.

Two consequences worth knowing before deploying:

- **The in-app channel is not implemented.** There is no notification table and
  no read side, so nothing is recorded in-app and a missed notice is recovered
  by re-opening the request. Adding the in-app half means a table, which is
  deliberately out of scope here.
- **Delivery is best-effort.** A relay failure is logged, never raised, so a
  student's excuse request never fails because mail is down — and a notice that
  fails to send is invisible to the sender. Grep the API log for
  `Email sent to=` when verifying a deployment. See
  [production-checklist.md](../deployment/production-checklist.md#7-email--smtp).

The four events above are the whole set. `quick_excuse`, `excuse_with_evidence`,
`edit_excuse` and `revoke_excuse` send nothing: the professor already knows they
did it, and §8 lists no notice for them.

---

## 9. Reporting Impact (D36)

### Compliance Rate

```
Compliance Rate = present / total
```

Excused records are **NOT counted as present** in the compliance rate. They are
excluded from the numerator. Only `validation_status = 'present'` counts.

### Participation Rate

```
Participation Rate = (present + late + excused) / total
```

Excused records **ARE counted** in the participation rate. An excused student
is considered to have participated (they had a legitimate reason for absence).

### Per-Course/Student Breakdown

| Status   | Compliance | Participation | Counted in "total" |
| -------- | ---------- | ------------- | ------------------ |
| present  | Yes        | Yes           | Yes                |
| late     | No         | Yes           | Yes                |
| excused  | No         | Yes           | Yes                |
| absent   | No         | No            | Yes                |
| pending  | No         | No            | Yes                |
| rejected | No         | No            | Yes                |

---

## 10. API Endpoints

| Method | Path                                               | Role      | Description                                                   |
| ------ | -------------------------------------------------- | --------- | ------------------------------------------------------------- |
| POST   | `/professor/sessions/{id}/attendance/{sid}/excuse` | Professor | Quick-excuse (Path A) or prof-with-evidence (Path B)          |
| PATCH  | `/professor/sessions/{id}/attendance/{sid}/excuse` | Professor | Update existing excuse (reason, notes)                        |
| DELETE | `/professor/sessions/{id}/attendance/{sid}/excuse` | Professor | Revoke a prof-initiated excuse (sets status back to original) |
| POST   | `/professor/sessions/{id}/excuse-all-absent`       | Professor | Bulk excuse all absent (Path: quick, D23)                     |
| GET    | `/professor/excuse-requests?status=pending`        | Professor | List pending excuse requests for review                       |
| POST   | `/professor/excuse-requests/{rid}/review`          | Professor | Approve or reject a student-initiated request                 |
| POST   | `/student/excuse-requests`                         | Student   | Submit excuse request (Path C)                                |
| GET    | `/student/excuse-requests`                         | Student   | List own excuse requests                                      |
| GET    | `/student/excuse-requests/{rid}`                   | Student   | Get detail of own excuse request                              |
| GET    | `/admin/excuses?status=pending`                    | Admin     | View all pending excuses system-wide                          |

---

## 11. Cross-References

| Topic                                    | Document                                        |
| ---------------------------------------- | ----------------------------------------------- |
| Database schema                          | [migration-strategy.md](migration-strategy.md)  |
| Data flow diagrams                       | [data-flow.md](data-flow.md)                    |
| Security model                           | [security-model.md](security-model.md)          |
| Wireframes: professor session/attendance | `docs/design/wireframes.md` (sections 3.3, 3.4) |
| Wireframes: student history              | `docs/design/wireframes.md` (section 2.7)       |
| Admin manual                             | `docs/guides/admin-manual.md`                   |
| Professor manual                         | `docs/guides/professor-manual.md`               |
| Student manual                           | `docs/guides/student-manual.md`                 |
