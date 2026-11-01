# Data Flow Diagrams

> Layered, code-grounded attendance workflow docs:
> [`docs/architecture/attendance-workflow/`](attendance-workflow/README.md). This file keeps
> the system-wide sequence diagrams; that directory holds the per-layer audit.
> Analytics layer docs: [`docs/architecture/analytics.md`](analytics.md).
> Anti-spoofing layer docs: [`docs/architecture/anti-spoofing.md`](anti-spoofing.md).

> Mermaid sequence diagrams for all major system flows. References the
> [target schema](../design/database-er.md) and its column names.

---

## 1. Full Online Scan (D27, amended by ADR-083)

```mermaid
sequenceDiagram
    participant S as Student Client
    participant API as Server API
    participant DB as Database

    Note over S,DB: Step 0 — Authenticated Identity (ADR-083)

    S->>API: POST /auth/login
    API-->>S: 200 {access_token, ...} (student role)

    Note over S,DB: Step 1 — Session Entry (D27.1)

    S->>API: POST /student/sessions/verify-code {code: "A7X9K2M4"}
    API->>DB: SELECT sessions.id, sessions.session_code, sessions.expires_at,<br>course_offerings.id, course_offerings.classroom_lat, course_offerings.classroom_lng<br>WHERE session_code = 'A7X9K2M4' AND expires_at > now()
    DB-->>API: Session row + offering context
    API-->>S: 200 {session_id, offering_id, session_type, is_remote, course_code, course_name, program_code, year_level_label,<br>expires_at, scheduled_end_time, classroom_name, geofence: {radius, lat, lng},<br>present_window_minutes, late_window_minutes}

    Note over S,DB: Step 2 — Student-ID Confirmation (D27.2 as amended)

    S->>S: Prefill student number from the signed-in profile
    S->>API: POST /student/attendance/precheck {session_id, student_number}
    API->>API: Resolve Student WHERE Student.user_id = token user_id
    API->>API: Compare student_number case-insensitively → 403 student_number_mismatch on mismatch
    API->>DB: Check enrollment + duplicate scan
    API-->>S: 200 {enrolled, already_scanned, student}

    Note over S,DB: Step 3 — Session QR Camera (current UI)

    S->>S: QRScanner reads the session code
    S->>API: POST /student/sessions/verify-code {code}
    Note right of S: Session discovery only — it never reads a student ID.<br>The professor UI currently shows the session code, not a rendered QR.

    Note over S,DB: Step 4 — GPS + Face Liveness (D27.3–D27.4)

    S->>S: MediaPipe FaceLandmarker WASM
    S->>S: Challenge: Blink → Turn Left → Turn Right
    S->>S: EAR check (blink), PnP check (head turns)
    S->>S: Capture scan frame (live_face_image) — server computes embedding (MobileFaceNet) and score
    S->>S: navigator.geolocation.getCurrentPosition() + Haversine pre-check
    alt Outside geofence
        S-->>S: Show error "Outside geofence"
    end

    Note over S,DB: Step 5 — Submit Attendance

    S->>API: POST /student/attendance/scan {<br>session_id: 456,<br>student_number: "24-2111",<br>gps: {lat, lng, accuracy},<br>liveness_evidence: {blink_detected, head_turn_left,<br>head_turn_right, ear_samples, pnp_evidence},<br>live_face_image: "<base64 scan frame>",<br>scanned_at: "2026-08-25T10:15:30Z"<br>}

    API->>API: 1. Check idempotency key → return prior result<br>(key = "user_id:session_id:X-Idempotency-Key", 15-min TTL)
    API->>API: 2. Verify session exists & is active + not expired
    API->>API: 3. Resolve student by token user_id; compare student_number
    API->>API: 4. Check enrollment (students.id → enrollments)
<    API->>API: 5. Check face enrollment (students.face_embedding NOT NULL) → 403 face_not_enrolled
    API->>API: 6. Check duplicate scan
    API->>API: 7. Validate geofence (server-side Haversine) — only when benchmark_mode is off
    API->>API: 8. Validate liveness evidence — only when benchmark_mode is off
    API->>API: 9. Generate embedding from live_face_image (MobileFaceNet) or live_face_embedding; cosine_similarity vs enrolled; score band: < 0.65 → 403 face_mismatch; 0.65–0.70 → pending review

    API->>API: 10. Compute status (elapsed since max(session.created_at, session.scheduled_start_time)):<br>elapsed ≤ present_window → present<br>elapsed ≤ present_window + late_window → late<br>else → rejected

    API->>DB: INSERT INTO attendance_records<br>(session_id, student_id, validation_status, timestamp,<br>scanned_via, liveness_evidence, face_match_score,<br>gps_lat, gps_lng, original_status, sync_status)
    DB-->>API: attendance_records.id

    API-->>S: 200 {id: 789, status: "present",<br>scanned_at, expires_at}
```

> **Identity note:** `student_number` is a confirmation check only. The student
> row is selected by `Student.user_id`, so a client cannot submit as somebody
> else. `face_match_score` is computed server-side from the enrolled embedding
> and the embedding generated from `live_face_image` (MobileFaceNet, cosine
> similarity); the client supplies the image, not a score (threshold 0.70,
> review band 0.65). See `shared/face_embeddings.py` and
> `shared/face_embedding_generator.py`.

---

## 2. Offline Scan → Sync

```mermaid
sequenceDiagram
    participant S as Student Client
    participant IDB as IndexedDB
    participant API as Server API
    participant DB as Database

    Note over S,IDB: Offline scan captured

    S->>S: Steps 1–4 same as online scan (session code, ID confirmation, liveness, GPS)
    S->>S: Local validation passes
    S->>IDB: INSERT INTO attendance_queue<br>{id: UUID, session_id, session_code, student_number,<br>payload: {gps, liveness_evidence, scanned_at},<br>status: "pending" (client queue state), attempts: 0}
    IDB-->>S: Stored locally
    S-->>S: Show "Evidence saved — will verify after sync"

    Note over S,IDB: `student_number` is queued for the confirmation check only;<br>the server re-resolves the student from the sync token.<br>The replay path supplies the same placeholder `face_match_score`.

    Note over S,DB: Network restored — background sync

    S->>IDB: SELECT * FROM attendance_queue<br>WHERE status = 'pending' (client queue state)<br>ORDER BY created_at ASC
    IDB-->>S: [item1, item2, ...]

    loop For each pending item
        S->>IDB: UPDATE status = 'syncing' (client queue state)
        S->>API: POST /student/attendance/scan<br>+ X-Idempotency-Key: user_id:session_id:item.id
        API->>DB: Check idempotency key (user_id:session_id:key, 15-min TTL)
        API->>API: Validate elapsed vs session window (D16)

        alt scanned_at > expires_at (D16)
            API-->>S: 410 {detail: {code: "session_expired", message: "Scan submitted after window closed"}}
            S->>IDB: UPDATE status = 'rejected' (client queue state),<br>last_error = 'session_expired'
        else scanned_at within window
            API->>DB: INSERT attendance_records
            API-->>S: 200 {status: "present"|"late"}
            S->>IDB: UPDATE status = 'synced' (client queue state)
        end
    end
```

> **Client vs DB statuses:** `pending`/`syncing`/`synced`/`rejected` above are
> **client-local queue states** on the `attendance_queue` IndexedDB store — NOT
> server enums. The DB uses `SyncStatus` (`synced`/`pending`/`failed`) on
> `attendance_records.sync_status` and `QueueStatus`
> (`pending`/`processing`/`done`/`failed`) on the `sync_queue` table.

---

## 3. Excuse Workflow (D20–D24)

### Path A: Professor Quick-Excuse

```mermaid
sequenceDiagram
    participant P as Professor Client
    participant API as Server API
    participant DB as Database

    P->>API: POST /professor/sessions/{sid}/attendance/{stid}/excuse<br>{reason: "Student was present but camera failed"}
    API->>DB: SELECT attendance_records WHERE session_id=sid AND student_id=stid
    DB-->>API: Record (validation_status: "absent")

    API->>DB: BEGIN
    API->>DB: UPDATE attendance_records SET<br>original_status = 'absent',<br>validation_status = 'excused',<br>excuse_reason = '...',<br>excused_by = professor_user_id,<br>excused_at = now(),<br>excuse_type = 'quick'
    API->>DB: INSERT INTO excuse_requests<br>(student_id, session_id, initiated_by='professor',<br>initiated_via='quick', reason, status='approved',<br>reviewed_by=professor_user_id, reviewed_at=now())
    DB-->>API: excuse_request.id
    API->>DB: UPDATE attendance_records SET<br>excuse_request_id = excuse_request.id
    API->>DB: COMMIT

    API-->>P: 201 {excuse_request_id, status: "approved",<br>original_status: "absent", new_status: "excused"}
```

### Path B: Professor-Initiated with Evidence

```mermaid
sequenceDiagram
    participant P as Professor Client
    participant API as Server API
    participant S3 as S3 Storage
    participant DB as Database

    P->>API: POST /professor/sessions/{sid}/attendance/{stid}/excuse<br>{reason: "...", attachment_urls: [url]}
    Note over API,S3: bytes went up earlier via
    POST /upload/presigned-url → client PUT to storage;
    the server never brokers the file itself
    API->>DB: BEGIN
    API->>DB: INSERT INTO excuse_requests<br>(student_id, session_id, initiated_by='professor',<br>initiated_via='prof_with_evidence',<br>reason, attachment_urls: [url],<br>status='approved',<br>reviewed_by=professor_user_id, reviewed_at=now())
    DB-->>API: excuse_request.id
    API->>DB: UPDATE attendance_records SET<br>original_status = current_status,<br>validation_status = 'excused',<br>excuse_type = 'prof_with_evidence',<br>excuse_request_id = id
    API->>DB: COMMIT

    API-->>P: 201 {status: "approved", attachment_saved: true}
```

### Path C: Student-Initiated Request

```mermaid
sequenceDiagram
    participant ST as Student Client
    participant API as Server API
    participant S3 as S3 Storage
    participant DB as Database
    participant P as Professor Client

    ST->>API: POST /student/excuse-requests<br>{session_id, reason, attachment_urls?}
    Note over API,S3: presigned upload (POST /upload/presigned-url)
    completed client-side before this; server stores URL references
    API->>DB: INSERT INTO excuse_requests<br>(student_id, session_id,<br>initiated_by='student',<br>initiated_via='request',<br>reason, attachment_urls, status='pending')
    DB-->>API: excuse_request.id
    API-->>ST: 201 {id, status: "pending"}

    Note over P,DB: Professor reviews

    P->>API: GET /professor/excuse-requests?status=pending
    API-->>P: 200 {items: [{id, student_name, session, reason, ...}]}

    P->>API: POST /professor/excuse-requests/{rid}/review<br>{status: "approved", review_notes: "Legitimate medical reason"}
    API->>DB: UPDATE excuse_requests SET<br>status = 'approved',<br>reviewed_by = professor_user_id,<br>reviewed_at = now(),<br>review_notes = '...'
    API->>DB: UPDATE attendance_records SET<br>original_status = current_status,<br>validation_status = 'excused',<br>excuse_type = 'request_approved',<br>-- (request_approved is a valid attendance_records.excuse_type;<br>-- differs from excuse_requests.initiated_via = 'request')<br>excuse_request_id = rid
    API-->>P: 200 {id, status: "approved"}

    API-->>ST: (notification: excuse request approved)
```

---

## 4. Nightly Risk Batch (D35)

```mermaid
sequenceDiagram
    participant CRON as Cron Trigger (02:00)
    participant API as Server API
    participant DB as Database

    CRON->>API: Trigger risk-score batch job

    API->>DB: SELECT DISTINCT e.student_id, e.offering_id, e.semester<br>FROM enrollments e<br>JOIN course_offerings co ON e.offering_id = co.id<br>WHERE co.is_active = true
    DB-->>API: Active enrollment pairs

    loop For each (student_id, offering_id, semester)
        Note over API,DB: One batched cohort fetch (not per-student COUNT):
        API->>DB: SELECT attendance rows for the cohort<br>(student_id, offering_id, status, timestamp, sync_status)
        DB-->>API: rows

        API->>API: Compute features:<br>expected_sessions = term_weeks(year_level.term_structure, offering.semester) × offering.sessions_per_week<br>absence_rate = count(ABSENT) / expected_sessions<br>max_streak = longest consecutive ABSENT run<br>sync_lag = count(sync_status='pending' AND older than 24h)<br>weekly_absences = compute_weekly_absences(...)  # counts per ISO week<br>trend_slope = 4-week linear regression of weekly_absences

        API->>API: Apply heuristic thresholds (D35):<br>absence_rate > 0.30 → high<br>absence_rate > 0.15 → medium<br>streak ≥ 3 → high<br>sync_lag ≥ 5 → medium<br>trend_slope < -0.05 → medium

        API->>DB: INSERT INTO student_risk_scores<br>(student_id, offering_id, semester,<br>risk_probability, risk_level,<br>features: {absence_rate, expected_sessions, max_streak,<br>sync_lag, weekly_absences, trend_slope},<br>computed_at = now(), computed_day = computed_at.date())
        Note over DB: UNIQUE(student_id, offering_id,<br>semester, computed_day)
    end

    API-->>CRON: Batch complete (logged)
```

---

## 5. Backup Pipeline (D39)

```mermaid
sequenceDiagram
    participant ADM as Admin Client
    participant API as Server API
    participant DB as PostgreSQL
    participant FS as Storage (local/S3)
    participant LOG as backup_log table

    ADM->>API: POST /admin/backups
    API->>DB: INSERT INTO backup_log (kind='full', status='started', started_at=now())
    DB-->>API: backup_log.id

    API->>DB: pg_dump -Fc --compress=9<br>→ stdout
    DB-->>API: Binary dump stream

    API->>API: gzip compress
    API->>API: AES-256-GCM encrypt<br>(key from BACKUP_ENCRYPTION_KEY env,<br>key_version from BACKUP_ENCRYPTION_KEY_VERSION)
    API->>API: Generate SHA-256 sidecar

    API->>FS: Write encrypted file<br>filename: backup_{timestamp}.dump.enc
    API->>FS: Write sidecar<br>filename: backup_{timestamp}.dump.enc.sha256

    API->>DB: UPDATE backup_log SET<br>filename = '...',<br>size_bytes = ...,<br>sha256 = '...',<br>storage_backend = 'local',<br>encryption_key_version = N,<br>finished_at = now(),<br>status = 'completed'

    API-->>ADM: 202 {backup_id}

    Note over API,LOG: Retention prune (daily)

    API->>DB: SELECT * FROM backup_log<br>WHERE kind = 'full'<br>AND finished_at < now() - INTERVAL '30 days'<br>AND EXTRACT(day FROM finished_at) != 1
    DB-->>API: Old daily backups to prune

    loop For each expired backup
        API->>FS: DELETE file + sidecar
        API->>DB: DELETE FROM backup_log WHERE id = ?
    end

    Note over API,LOG: Retention prune (monthly — keep last 12)

    API->>DB: SELECT * FROM backup_log<br>WHERE kind = 'full'<br>AND EXTRACT(day FROM finished_at) = 1<br>AND finished_at < now() - INTERVAL '12 months'
    DB-->>API: Old monthly backups to prune

    loop For each expired monthly
        API->>FS: DELETE file + sidecar
        API->>DB: DELETE FROM backup_log WHERE id = ?
    end
```

---

## Appendix: Table/Column Reference

All diagrams above reference the target schema in
[`../design/database-er.md`](../design/database-er.md):

| Diagram      | Tables Referenced                                                                    |
| ------------ | ------------------------------------------------------------------------------------ |
| Online Scan  | `sessions`, `course_offerings`, `enrollments`, `attendance_records`, `students`    |
| Offline Sync | `attendance_records` (client persists to IndexedDB `attendance_queue`)        |
| Excuse       | `excuse_requests` (reviewed_by), `attendance_records` (excused_by)                    |
| Risk Batch   | `enrollments`, `sessions`, `attendance_records`, `student_risk_scores` (reads `attendance_records.sync_status`) |
| Backup       | `backup_log`, all tables via `pg_dump`                                               |
