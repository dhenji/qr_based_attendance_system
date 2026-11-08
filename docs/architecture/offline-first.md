# Offline-First Architecture

> Layered, code-grounded attendance workflow docs:
> [`docs/architecture/attendance-workflow/`](attendance-workflow/README.md).
> Anti-spoofing layer docs: [`docs/architecture/anti-spoofing.md`](anti-spoofing.md).

> Client-side offline storage, sync algorithm, and server-side validation for
> scans that occur without network connectivity.

---

## Overview

The student scanner must work reliably in lecture halls with poor connectivity.
All scan data is captured client-side first; network is optional. On connectivity
restoration, the sync queue drains to the server, which validates timestamps
and rejects expired-window submissions.

---

## IndexedDB Stores

All client storage uses IndexedDB via a thin wrapper around the raw browser
API (`sync/service.ts:56-61`) — there is no `idb` dependency. Four object stores:

### 1. `attendance_queue`

Stores pending scan submissions.

| Column              | Type     | Notes                                                        |
| ------------------- | -------- | ------------------------------------------------------------ |
| `id`                | UUID     | Auto-generated client ID                                     |
| `session_id`        | int      | FK to server session                                         |
| `session_code`      | string   | For display/debug                                            |
| `student_number`    | string   | Student number from the signed-in profile; confirmation check only |
| `payload.gps`       | object   | `{lat, lng, accuracy}` nested, not flat columns              |
| `payload.liveness_evidence` | JSON | blink, head turns, EAR, PnP                            |
| `payload.face_match_score` | float (optional) | Placeholder supplied by the replay path; never compared to an embedding |
| `payload.scanned_at` | ISO-8601 | **Device timestamp at scan** (validated server-side per D16) |
| `status`            | enum     | `pending` → `syncing` → `synced` / `rejected` — **client-local queue states** (NOT DB enums; server uses `SyncStatus` = `synced`/`pending`/`failed` and `QueueStatus` = `pending`/`processing`/`done`/`failed`) |
| `attempts`          | int      | Retry counter, incremented per failure, never reset           |
| `max_attempts`      | int      | Terminal after N tries (`DEFAULT_MAX_ATTEMPTS = 25`)         |
| `last_error`        | string   | `error.code` from the failed POST, not the message            |
| `created_at`        | ISO-8601 | Local enqueue time                                           |

The queue row nests the scan payload under `payload` rather than flattening `gps_lat` /
`gps_lng` / `gps_accuracy` into top-level columns (`sync/service.ts:24,39`). Retries count
`attempts` toward `max_attempts` and are **never reset** on a later enqueue — the row's
history is kept, not cleared.

### 2. `face_embeddings`

Cached face embeddings, encrypted at rest via WebCrypto (AES-GCM) with a device-generated
non-extractable key. The key itself lives in the fourth store, `face_keys` — it is never
serialised, so a steal of `face_embeddings` ciphertext alone is not sufficient to decrypt it.

| Column       | Type        | Notes                                              |
| ------------ | ----------- | -------------------------------------------------- |
| `student_id` | int         | Own embedding                                      |
| `version`    | int         | Server embedding version                           |
| `embedding`  | string      | Base64 **ciphertext** (iv + ciphertext), not raw bytes |
| `fetched_at` | ISO-8601    | Cache freshness                                    |

### 3. `session_cache`

Read-only snapshots of active session config (for offline display and GPS checks).

| Column                   | Type     | Notes                  |
| ------------------------ | -------- | ---------------------- |
| `session_id`             | int      |                        |
| `course_code`            | string   |                        |
| `geofence`               | JSON     | `{ radius, lat, lng }` |
| `expires_at`             | ISO-8601 | For local expiry check |
| `present_window_minutes` | int      |                        |
| `late_window_minutes`    | int      |                        |

### 4. `face_keys`

Stores the single device-generated AES-GCM `CryptoKey` used to encrypt the cached
`face_embeddings` rows. Non-extractable, persisted via structured clone — no salt, no
passphrase, and **no decrypt-on-sync path exists**: the client encrypts the server blob for
at-rest protection and only ever compares against it locally.

---

## Storage Security Note

`face_embeddings` rows are encrypted at rest with a device-generated
non-extractable AES-GCM key (see store 2 above). The `attendance_queue`
payloads — including captured face images and liveness evidence — are **not**
encrypted today; they rely on the browser's origin-scoped IndexedDB storage.
Shared-device and XSS scenarios are covered by the threat model in
`security-model.md`; encrypting the queue the same way as embeddings is a
future hardening item.

## Sync Algorithm

```
┌─────────────────────────────────────────────────────┐
│                   Client Side                        │
│                                                      │
│  1. Online scan happy path:                          │
│     scan → validate locally → POST /student/attendance/scan  │
│     → server responds → update queue (synced)        │
│                                                      │
│  2. Offline scan path:                               │
│     scan → validate locally → enqueue to             │
│     attendance_queue (status: pending)               │
│     → user sees "queued for sync" badge              │
│                                                      │
│  3. Background sync trigger:                         │
│     a. `navigator.onLine` change event               │
│     b. Periodic retry (exponential backoff)          │
│     c. Service Worker `sync` event (if available)    │
│                                                      │
│  4. Drain queue:                                     │
│     for each item (oldest first):                    │
│       set status = syncing (client-only state)       │
│       POST /student/attendance/scan with X-Idempotency-Key   │
│       = "user_id:session_id:caller-supplied key" (15-min TTL) │
│       → 200: set status = synced (client-only state) │
│       → 4xx reject: set status = rejected,           │
│         last_error = error.code (not the message)    │
│       → network error: revert status = pending,      │
│         increment attempts, schedule next              │
│                                                      │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│                   Server Side                        │
│                                                      │
│  POST /student/attendance/scan:                              │
│    1. Check idempotency key → return prior result             │
│       (keyed "user_id:session_id:X-Idempotency-Key", 15-min TTL)│
│    2. Verify session exists & is active + not expired         │
│       (scanned_at > session.expires_at → "session_expired", D16)│
│    3. Resolve student & match student_number                  │
│    4. Check enrollment                                        │
│    5. Check duplicate scan                                    │
│    6. Validate geofence (Haversine) — skipped under           │
│       BENCHMARK_MODE                                          │
│    7. Validate liveness evidence — skipped under              │
│       BENCHMARK_MODE                                          │
│    8. Validate face_match_score ≥ threshold                   │
│    9. Compute status:                                         │
│       elapsed ≤ present_window → present                      │
│       elapsed ≤ present + late window → late                  │
│       else → rejected                                         │
│   10. Write attendance_records (preserving original_status)   │
│   11. Return result                                           │
│                                                      │
└─────────────────────────────────────────────────────┘
```

**Idempotency & staleness contract (server-enforced):**

- The idempotency key is `user_id:session_id:<caller-supplied key>`, TTL 900s
  (15 min), process-local, max 10,000 entries (`attendance/constants.py:33-36`,
  `service.py:205`). A reused key inside the window returns the prior result
  instead of re-writing the record.
- A queued scan is only written as `synced` when its `scanned_at` is within
  `SYNC_STALE_SECONDS = 60` of server time (`attendance/constants.py:41`,
  `service.py:595`). Older replays are dropped as stale, so a backed-off replay
  must keep a due scan younger than 60s.

### Rejection Reasons

| Reason             | When                                | Decision   |
| ------------------ | ----------------------------------- | ---------- |
| `session_expired`  | `scanned_at` after `expires_at`     | D16        |
| `outside_geofence` | GPS outside radius                  | D17, D27   |
| `liveness_failed`  | Liveness checks fail                | D31        |
| `face_mismatch`    | Cosine similarity < threshold       | D27 step 4 |
| `face_not_enrolled`| Student has no face enrollment      | D27 submit |
| `not_enrolled`     | Student not in course roster        | D27 step 2 |
| `duplicate_scan`   | Student already scanned for session | D27 step 2 |

### Exponential Backoff

```
retry_delay = min(30s * 2^retry_count, 30 minutes)
```

- First retry: 30s
- Second: 60s
- Third: 120s
- Max: 30 minutes
- `attempts` is **not** reset on a later retry — only on enqueue (a fresh queue
  row starts at 0). The counter is what trips `max_attempts` into terminal
  rejection, so resetting it on each sync would defeat the cap.

### Clock Skew

`scanned_at` is device time and is never trusted for authorization; the
server rejects a scan whose `scanned_at` is after `session.expires_at`
(`session_expired`) and computes the present/late window from it. A device
whose clock is far off can therefore be marked late or rejected on sync.
The client captures a single `scannedAt` per attempt (see
`student/scan/+page.svelte::doSubmit`) and the backend keeps the value
verbatim rather than re-stamping it, so replaying does not drift further.
Operators investigating skew-related rejections should compare
`attendance_records.timestamp` with the session window, not the sync time.

### Conflict Resolution

No client-side conflict possible — the server is the sole authority for
attendance records. Clients submit; server decides. If rejected, the queue
item stays in `rejected` state with `last_error` for user visibility.

---

## Embedding Pull-On-Login (D29)

```
┌──────────┐         ┌──────────┐
│  Student  │         │  Server  │
│  Client   │         │   API    │
└─────┬────┘         └─────┬────┘
      │                    │
      │  1. Login          │
      │───────────────────►│
      │  2. JWT            │
      │◄───────────────────│
      │                    │
      │  3. GET /student/  │
      │     me/face-       │
      │     embedding      │
      │     ?current_      │
      │     version=N      │
      │───────────────────►│
      │                    │
      │  4a. 204 No Content│  (version matches)
      │◄───────────────────│
      │                    │
      │  OR                │
      │                    │
│  4b. 200 {version, │  (newer version)
│     embedding}    │  embedding is the server's
│                    │  plaintext JSON blob
│◄───────────────────│
│                    │
│  5. Encrypt with   │
│     device key,    │
│     store          │
│     ciphertext in  │
│     IndexedDB      │
│                    │
```

**Device encryption key**: generated once per device via `crypto.subtle.generateKey`,
stored as a non-extractable `CryptoKey` in the `face_keys` IndexedDB store (not
`crypto.subtle` itself, not a secure enclave, no salt/passphrase). The server
never sees this key.

**Re-enrollment**: When admin re-enrolls a student (3 new photos), `face_embedding_version`
increments. Next student login triggers pull. Old cached embedding is superseded.

**Revocation**: If student account is archived, the server returns 404 for embedding
requests; client clears local cache.

---

## Offline Verification

When scanning offline:

1. **Face comparison** — ⚠ **Not implemented yet.** The cached embedding is stored as
   encryption ciphertext, and no decrypt-and-compare path exists today. The client-side
   embedding compare is a separate future slice (`student/face.svelte.ts:15-16` states this
   explicitly: "Client-side embedding *compare* is a separate future slice … no documented
   decrypt scheme"). Treat the steps below as the design, not the build.
2. **GPS check** runs against cached session geofence config.
   Server-side accuracy review band (>100 m → `accuracy_low`) and hard floor
   (>1000 m → 422 `gps_accuracy_too_low`) apply to synced scans too. The scan
   page also fail-fast rejects fixes above the configured hard floor
   (`VerifyGeofence.gps_hard_floor_meters`, default 1000 m) before enqueueing,
   showing `gps_accuracy_too_low` copy; a non-positive value disables the
   client fail-fast.
3. **Liveness** runs client-side (MediaPipe FaceLandmarker WASM, EAR + PnP heuristics).
4. **Status is tentative**: marked `pending` in queue. Server recomputes on sync.

The student sees: "✅ Evidence saved — will verify after sync" (offline badge variant
per wireframe 2.2d).

---

## Sequence Diagrams

### Online Scan (Happy Path)

```mermaid
sequenceDiagram
    participant S as Student Client
    participant API as Server API
    participant DB as Database

    S->>API: POST /student/sessions/verify-code {code}
    API->>DB: SELECT sessions WHERE session_code = ?
    DB-->>API: Session + course config
    API-->>S: 200 {session_id, geofence, windows, ...}

    S->>S: Confirm student number from the signed-in profile (precheck)
    S->>S: GPS geofence check (Haversine)
    S->>S: Face liveness challenge (blink→left→right)
    S->>S: Live face image captured for server-side embedding comparison

    S->>API: POST /student/attendance/scan {session_id, student_number, gps {lat, lng, accuracy}, liveness_evidence, face_match_score, scanned_at}
    API->>DB: Check idempotency key
    API->>API: Validate scanned_at vs window
    API->>API: Resolve student by token user_id; compare student_number
    API->>API: Validate geofence
    API->>API: Grade liveness evidence
    API->>API: Apply score band to the submitted face score
    API->>API: Check enrollment + duplicate
    API->>API: Compute status (present/late/rejected)
    API->>DB: INSERT attendance_records
    API-->>S: 200 {id, status}
```

### Offline Scan → Later Sync

```mermaid
sequenceDiagram
    participant S as Student Client
    participant Q as IndexedDB Queue
    participant API as Server API
    participant DB as Database

    Note over S: No network connectivity

    S->>S: Confirm student number from the signed-in profile
    S->>S: GPS geofence check (local cache)
    S->>S: Face liveness challenge
    S->>S: No embedding comparison is performed; the server grades the evidence later
    S->>Q: Enqueue {session_id, session_code, student_number, gps, liveness_evidence, scanned_at}
    Q-->>S: "Evidence saved — will verify after sync"

    Note over S: Network restored

    S->>Q: Drain queue (oldest first)
    Q->>S: Dequeue item

    S->>API: POST /student/attendance/scan + X-Idempotency-Key
    API->>DB: Check idempotency
    API->>API: Resolve student by token user_id; compare student_number
    API->>API: Validate scanned_at vs expires_at (D16)

    alt scanned_at > expires_at
        API-->>S: 410 {detail: {code: "session_expired", message: "Scan submitted after window closed"}}
        Q->>Q: status = rejected (client-only state),<br>last_error = "session_expired"
    else scanned_at within window
        API->>DB: INSERT attendance_records
        API-->>S: 200 {status: "present"|"late"}
        Q->>Q: status = synced (client-only state)
    end
```

### Embedding Pull-On-Login

```mermaid
sequenceDiagram
    participant S as Student Client
    participant IDB as IndexedDB
    participant API as Server API
    participant DB as Database

    S->>API: POST /auth/login {email, password}
    API-->>S: JWT

    S->>IDB: Get cached version
    IDB-->>S: current_version = 3

    S->>API: GET /student/me/face-embedding?current_version=3
    API->>DB: SELECT face_embedding, face_embedding_version
    DB-->>API: version = 5, embedding = "enc blob"

    API-->>S: 200 {version: 5, embedding: "plaintext blob"}

    S->>S: Encrypt with device key (encryptBlob)
    S->>IDB: Upsert {student_id, version: 5, embedding: <ciphertext>}
    IDB-->>S: Stored

    Note over S: Subsequent scans use cached v5 ciphertext —
    N.B. client-side compare is not yet implemented (see "Offline Verification")
```

---

## Client-Side Validation Summary

Checks performed locally before queuing:

| Check                   | Source                             | Offline Available           |
| ----------------------- | ---------------------------------- | --------------------------- |
| Session code validity   | Cached session config              | Yes (if previously fetched) |
| Student number format   | Profile value (3–50 chars, upper-cased; the conventional `YY-NNNN` shape is not validated) | Yes |
| GPS within geofence     | Haversine vs cached session coords | Yes                         |
| Liveness (blink, turns) | MediaPipe WASM                     | Yes                         |
| Face match score        | Server-side cosine similarity on sync (requires connectivity) | No              |
| Duplicate scan          | Deferred to the server on sync     | No                          |

Server re-validates **all** checks on sync. Client validation is UX-only
(faster feedback) — never trust-only.
