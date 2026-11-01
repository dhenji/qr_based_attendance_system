# 08 — End-to-End Workflow

## Online scan (anti-spoofing controls)

```mermaid
sequenceDiagram
    participant S as Student Client
    participant API as Server API
    participant DB as Database
    S->>API: POST /student/sessions/verify-code {code}
    S->>API: POST /student/attendance/precheck {session_id, student_number}
    API->>API: Resolve student by user_id; compare number (403 on mismatch)
    API->>DB: Check enrollment + duplicate
    S->>S: GPS check (requestBestPosition) + face liveness (MediaPipe)
    S->>API: POST /student/attendance/scan {session_id, student_number, gps, liveness_evidence, live_face_image, scanned_at}
    API->>API: idempotency → session active/expired → student resolve → enrollment → face enrollment → duplicate → score vs review_low → (unless benchmark) geofence → liveness → score band → status
    API->>DB: INSERT attendance_records (validation_status, original_status, liveness_evidence, face_match_score)
    API-->>S: 200 {id, status, scanned_at, expires_at}
```

## Review flow

Flagged rows (`evidence.review == true`) listed via
`/admin/attendance/liveness-review`. Resolve approve restores computed
present/late; reject marks rejected. Audit row written.

## Enrollment and revoke

Admin enrolls 3 photos (quality gates + embedding generation) or revokes
(clears blob, bumps version). Revocation invalidates cached device embeddings
via version bump.
```
