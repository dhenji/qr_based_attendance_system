# 08 — End-to-End Workflow

## Online scan

```mermaid
sequenceDiagram
    participant S as Student Client
    participant API as Server API
    participant DB as Database
    S->>API: POST /student/sessions/verify-code {code}
    API->>DB: SELECT session + offering context
    API-->>S: 200 {session_id, geofence, windows, ...}
    S->>API: POST /student/attendance/precheck {session_id, student_number}
    API->>API: Resolve student by user_id; compare number (403 on mismatch)
    API->>DB: Check enrollment + duplicate
    API-->>S: 200 {enrolled, already_scanned, student}
    S->>S: GPS + Face liveness (MediaPipe)
    S->>API: POST /student/attendance/scan {session_id, student_number, gps, liveness_evidence, live_face_image, scanned_at}
    API->>API: idempotency → session active/expired → student resolve → enrollment → face enrollment → duplicate → geofence → liveness → score band → status
    API->>DB: INSERT attendance_records
    API-->>S: 200 {id, status, scanned_at, expires_at}
```

## Precheck

Read-only: validates session, enrollment, duplicate scan. Does not write rows
(`attendance/service.py:458`).

## Offline replay

Client enqueues on network error; drains oldest-first with `X-Idempotency-Key`;
server allows expired sessions when key present. Stale gate queues server-side
sync row only when `(now - scanned_at) > 60 s`.

## Review

Flagged rows (`evidence.review == true`) listed via `/admin/attendance/liveness-review`.
Resolve approve restores computed present/late; reject marks rejected. Audit row
written (`attendance/service.py:1212`).

## History

`GET /student/attendance/history` returns paginated items + summary over the
full filter set (compliance/participation via `shared/rates.py`).
