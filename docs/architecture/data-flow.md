# Data Flow Diagrams

> Mermaid sequence diagrams for all major system flows. References §6 table
> and column names from DOCS_REFACTOR_PLAN.md.

---

## 1. Full Online Scan (D27)

```mermaid
sequenceDiagram
    participant S as Student Client
    participant API as Server API
    participant DB as Database

    Note over S,DB: Step 1 — Session Entry (D27.1)

    S->>API: POST /student/sessions/verify-code {code: "A7X-9K2M"}
    API->>DB: SELECT sessions.id, sessions.code, sessions.expires_at,<br>courses.id, courses.classroom_lat, courses.classroom_lng<br>WHERE code = 'A7X-9K2M' AND expires_at > now()
    DB-->>API: Session row + course context
    API-->>S: 200 {session_id, course_code, course_name, expires_at,<br>scheduled_end_time, geofence: {radius, lat, lng},<br>present_window_minutes, late_window_minutes}

    Note over S,DB: Step 2 — Student-ID QR Scan (D27.2)

    S->>S: Camera scans student-ID QR → resolves student_number "24-2111"
    S->>API: (implicit in scan POST) Student number resolves to student_id

    Note over S,DB: Step 3 — GPS Geofence (D27.3)

    S->>S: navigator.geolocation.getCurrentPosition()
    S->>S: Haversine(student_gps, session_gps) ≤ radius?
    alt Outside geofence
        S-->>S: Show error "Outside geofence"
    end

    Note over S,DB: Step 4 — Face Liveness (D27.4)

    S->>S: MediaPipe Face Mesh WASM
    S->>S: Challenge: Blink → Turn Left → Turn Right
    S->>S: EAR check (blink), PnP check (head turns)
    S->>S: Embedding comparison vs cached face_embedding
    S->>S: cosine_similarity(student, enrolled) ≥ 0.7?
    alt Face check failed
        S-->>S: Show error with specific reason
    end

    Note over S,DB: Step 5 — Submit Attendance

    S->>API: POST /student/attendance/scan {<br>session_id: 456,<br>qr_student_number: "24-2111",<br>gps: {lat, lng, accuracy},<br>liveness_evidence: {blink_detected, head_turn_left,<br>head_turn_right, ear_samples, pnp_evidence},<br>face_match_score: 0.82,<br>scanned_at: "2026-08-25T10:15:30Z"<br>}

    API->>API: 1. Validate session active + not expired
    API->>API: 2. Check idempotency key
    API->>API: 3. Validate scanned_at vs session window
    API->>API: 4. Validate geofence (server-side Haversine)
    API->>API: 5. Validate liveness evidence
    API->>API: 6. Validate face_match_score ≥ FACE_MATCH_THRESHOLD
    API->>API: 7. Check enrollment (students.id → enrollments)
    API->>API: 8. Check duplicate scan

    API->>API: 9. Compute status:<br>scanned_at ≤ present_window → present<br>scanned_at ≤ present_window + late_window → late<br>else → rejected

    API->>DB: INSERT INTO attendance_records<br>(session_id, student_id, status, scanned_at,<br>scanned_via, liveness_evidence, face_match_score,<br>gps_lat, gps_lng)
    DB-->>API: attendance_record.id

    API-->>S: 200 {attendance_id: 789, status: "present",<br>scanned_at, expires_at}
```

---

## 2. Offline Scan → Sync

```mermaid
sequenceDiagram
    participant S as Student Client
    participant IDB as IndexedDB
    participant API as Server API
    participant DB as Database

    Note over S,IDB: Offline scan captured

    S->>S: Steps 1–4 same as online scan
    S->>S: Local validation passes
    S->>IDB: INSERT INTO attendance_queue<br>{id: UUID, session_id, gps, liveness,<br>face_score, scanned_at, status: "pending"}
    IDB-->>S: Stored locally
    S-->>S: Show "Evidence saved — will verify after sync"

    Note over S,DB: Network restored — background sync

    S->>IDB: SELECT * FROM attendance_queue<br>WHERE status = 'pending'<br>ORDER BY created_at ASC
    IDB-->>S: [item1, item2, ...]

    loop For each pending item
        S->>IDB: UPDATE status = 'syncing'
        S->>API: POST /student/attendance/scan<br>+ X-Idempotency-Key: item.id
        API->>DB: Check idempotency key
        API->>API: Validate scanned_at vs session.expires_at (D16)

        alt scanned_at > expires_at (D16)
            API-->>S: 410 {code: "session_expired"}
            S->>IDB: UPDATE status = 'rejected',<br>last_error = 'session_expired'
        else scanned_at within window
            API->>DB: INSERT attendance_record
            API-->>S: 200 {status: "present"|"late"}
            S->>IDB: UPDATE status = 'synced'
        end
    end
```

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
    DB-->>API: Record (status: "absent")

    API->>DB: BEGIN
    API->>DB: UPDATE attendance_records SET<br>original_status = 'absent',<br>status = 'excused',<br>excuse_reason = '...',<br>excused_by = professor_user_id,<br>excused_at = now(),<br>excuse_type = 'quick'
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

    P->>API: POST /professor/sessions/{sid}/attendance/{stid}/excuse<br>{reason: "...", attachment: file.jpg}
    API->>S3: Upload attachment (content-addressable SHA-256 key)
    S3-->>API: attachment_url

    API->>DB: BEGIN
    API->>DB: INSERT INTO excuse_requests<br>(student_id, session_id, initiated_by='professor',<br>initiated_via='prof_with_evidence',<br>reason, attachment_urls: [url],<br>status='approved',<br>reviewed_by=professor_user_id, reviewed_at=now())
    DB-->>API: excuse_request.id
    API->>DB: UPDATE attendance_records SET<br>original_status = current_status,<br>status = 'excused',<br>excuse_type = 'prof_with_evidence',<br>excuse_request_id = id
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

    ST->>API: POST /student/excuse-requests<br>multipart: {session_id, reason, attachment?}
    API->>S3: Upload attachment (if provided)
    S3-->>API: attachment_url

    API->>DB: INSERT INTO excuse_requests<br>(student_id, session_id,<br>initiated_by='student',<br>initiated_via='request',<br>reason, attachment_urls, status='pending')
    DB-->>API: excuse_request.id
    API-->>ST: 201 {id, status: "pending"}

    Note over P,DB: Professor reviews

    P->>API: GET /professor/excuse-requests?status=pending
    API-->>P: 200 {items: [{id, student_name, session, reason, ...}]}

    P->>API: POST /professor/excuse-requests/{rid}/review<br>{decision: "approved", review_notes: "Legitimate medical reason"}
    API->>DB: UPDATE excuse_requests SET<br>status = 'approved',<br>reviewed_by = professor_user_id,<br>reviewed_at = now(),<br>review_notes = '...'
    API->>DB: UPDATE attendance_records SET<br>original_status = current_status,<br>status = 'excused',<br>excuse_type = 'request_approved',<br>excuse_request_id = rid
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

    API->>DB: SELECT DISTINCT student_id, course_id, semester<br>FROM enrollments<br>WHERE is_active = true
    DB-->>API: Active enrollment pairs

    loop For each (student_id, course_id, semester)
        API->>DB: SELECT COUNT(*) FROM sessions<br>WHERE course_id = ? AND created_at<br>BETWEEN semester_start AND now()
        DB-->>API: total_sessions

        API->>DB: SELECT COUNT(*) FROM attendance_records ar<br>JOIN sessions s ON ar.session_id = s.id<br>WHERE s.course_id = ? AND ar.student_id = ?<br>AND ar.status = 'absent'
        DB-->>API: absent_count

        API->>API: Compute features:<br>absence_rate = absent_count / total_sessions<br>max_streak = longest consecutive absent run<br>sync_lag = COUNT(sync_queue WHERE status='pending')<br>trend_slope = 4-week linear regression of weekly rates

        API->>API: Apply heuristic thresholds (D35):<br>absence_rate > 0.30 → high<br>absence_rate > 0.15 → medium<br>streak ≥ 3 → high<br>sync_lag ≥ 5 → medium<br>trend_slope < -0.05 → medium

        API->>DB: INSERT INTO student_risk_scores<br>(student_id, course_id, semester,<br>risk_probability, risk_level,<br>features: {absence_rate, max_streak,<br>sync_lag, trend_slope},<br>computed_at = now())
        Note over DB: UNIQUE(student_id, course_id,<br>semester, computed_at::date)
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

    API-->>ADM: 202 {backup_id, status: "completed"}

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

## Appendix: Table/Column Reference (§6)

All diagrams above reference the target schema in §6:

| Diagram      | Tables Referenced                                                                    |
| ------------ | ------------------------------------------------------------------------------------ |
| Online Scan  | `sessions`, `courses`, `enrollments`, `attendance_records`, `students`               |
| Offline Sync | `attendance_records`, `sync_queue` (client-side `attendance_queue`)                  |
| Excuse       | `excuse_requests`, `attendance_records`, `users` (excused_by, reviewed_by)           |
| Risk Batch   | `enrollments`, `sessions`, `attendance_records`, `student_risk_scores`, `sync_queue` |
| Backup       | `backup_log`, all tables via `pg_dump`                                               |
