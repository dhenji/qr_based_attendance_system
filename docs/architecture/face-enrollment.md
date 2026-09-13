# Face Enrollment & Verification Architecture

> **Decisions covered:** D27–D31, D43

## 1. Overview

Face verification is an admin-enrolled, client-verified biometric layer that ensures
the student physically present during a scan session matches the enrolled identity.
It is **not** the primary authentication method — it is a spoof-mitigation factor
(D27 step 4) layered on top of session-code + student-ID-QR + geofence checks.

Key properties:

- **Admin-enrolled, not self-enrolled** (D28): only administrators may capture face
  photos and generate embeddings. Students cannot upload their own face data.
- **3-photo enrollment** (D43): front, left, right — chosen over 1 (too brittle) and
  5 (diminishing returns).
- **Pull-on-login distribution** (D29): devices fetch the latest embedding on login
  by comparing a version integer; no push/WebSocket infrastructure required.
- **Offline-capable** (D30): cached embeddings enable client-side cosine comparison
  when the device is offline. Only scores and evidence sync to the server.

---

## 2. Enrollment Flow (Admin)

```
Admin picks student → Face Enrollment Modal opens
        │
        ▼
┌─────────────────────────────────┐
│  Capture 3 photos sequentially  │
│  1. Front (facing camera)       │
│  2. Left profile                │
│  3. Right profile               │
└────────────┬────────────────────┘
             │
             ▼
    Quality gates (per photo)
        │
        ├─ FAIL → reject, show reason, retry same angle
        │
        ▼
    All 3 pass
        │
        ▼
Server generates 128-d embedding per photo (face-api.js ResNet, D28)
        │
        ▼
Stores ONE encrypted JSON blob in students.face_embedding BYTEA
        │
        ├─ Bumps face_embedding_version
        ├─ Sets face_enrolled_at = NOW()
        ├─ Overwrites any previous enrollment (supersedes old vectors)
        │
        ▼
Student can now use face verification in scan sessions
```

### 2.1 Quality Gates

Each captured photo must pass **all** of the following before the next angle is
accepted:

| Gate          | Condition                                                        | Error Message                                                |
| ------------- | ---------------------------------------------------------------- | ------------------------------------------------------------ |
| Brightness    | Mean pixel luminance in [40, 220] (0–255)                        | "Image too dark / too bright — move to better lighting"      |
| Face size     | Detected face bounding box ≥ 15% of image area                   | "Face too small — move closer to the camera"                 |
| Single face   | Exactly 1 face detected in frame                                 | "Multiple faces detected — ensure only your face is visible" |
| Face centered | Face centroid within 30% of image center (horizontal + vertical) | "Face not centered — look directly at the camera"            |
| Sharpness     | Laplacian variance ≥ 50                                          | "Image blurry — hold steady and retry"                       |
| Eyes open     | Eye aspect ratio (EAR) > 0.2 for both eyes                       | "Please keep your eyes open"                                 |

### 2.2 Storage Format

A single encrypted JSON blob stored in `students.face_embedding` (BYTEA column):

```json
{
  "mean": [0.0231, -0.0412, ..., 0.0891],
  "angles": {
    "front": [0.0250, -0.0398, ..., 0.0912],
    "left":  [0.0198, -0.0445, ..., 0.0867],
    "right": [0.0244, -0.0401, ..., 0.0895]
  }
}
```

- **`mean`** (128 floats): element-wise average of the three angle vectors. Used as
  the **primary comparison target** during verification (D28).
- **`angles`** (3 × 128 floats): per-angle vectors retained for **tie-breaking**
  when the mean score falls in the review band (0.65–0.70). The system re-checks
  cosine similarity against each individual angle; if any angle passes ≥
  `FACE_MATCH_THRESHOLD` (0.70), the scan is auto-approved.
- **Encryption**: the JSON is encrypted with AES-256-GCM using a server-side key
  before writing to BYTEA. Decryption happens only on the server during enrollment
  or when serving the embedding to a verified student device (D29).

### 2.3 Supporting Columns

| Column                            | Type             | Purpose                                       |
| --------------------------------- | ---------------- | --------------------------------------------- |
| `students.face_embedding`         | BYTEA NULL       | Encrypted embedding blob                      |
| `students.face_enrolled_at`       | TIMESTAMPTZ NULL | Timestamp of last enrollment                  |
| `students.face_embedding_version` | INT DEFAULT 0    | Monotonic version; incremented on every write |

---

## 3. Distribution: Pull-on-Login (D29)

Embeddings are **never pushed** to student devices. Instead:

```
Student logs in
    │
    ▼
Client checks cached version (IndexedDB)
    │
    ├─ Cache miss → GET /student/me/face-embedding
    │                 Server returns { embedding: <encrypted>, version: N }
    │                 Client stores in IndexedDB, encrypted with device WebCrypto key
    │
    ├─ Cache hit, version == N → no-op
    │
    └─ Cache hit, version < N → GET /student/me/face-embedding
                                  Re-download, overwrite local cache
```

### 3.1 Device Cache Format

Stored in IndexedDB (encrypted at rest via WebCrypto device key):

```json
{
  "embedding": "<base64-encoded encrypted blob>",
  "version": 42,
  "cached_at": "2026-08-25T10:30:00Z"
}
```

The device key is derived from a device-unique salt + user passphrase (or
device-bound keychain entry). Decryption is client-side only; the raw embedding
never touches localStorage unencrypted.

### 3.2 Re-enrollment Policy

- When an admin re-enrolls a student (new 3-photo capture), the server
  **overwrites** the existing embedding blob and increments
  `face_embedding_version`.
- The next time the student logs in, the pull-on-login handshake detects the
  version bump and re-downloads the new embedding.
- Historical attendance records retain the `face_match_score` captured at scan
  time; re-enrollment does not retroactively alter past verification scores.

### 3.3 Revocation Policy

| Trigger                                | Action                                                                       |
| -------------------------------------- | ---------------------------------------------------------------------------- |
| Student archived (`is_active = false`) | `face_embedding` set to NULL, version NOT reset (prevents stale cache reuse) |
| Admin manually revokes face data       | Same as above: NULL + version bump                                           |
| Student graduates / transfers out      | Handled by archive flow above                                                |

When `face_embedding IS NULL`, the scan flow (D27) skips step 4 (face check)
and records the attendance record with `liveness_evidence` noting
`"face_not_enrolled"`. The student is NOT blocked from attendance but is
flagged in the liveness review queue for admin follow-up.

---

## 4. Verification Flow (During Scan)

Per D27, face verification is step 4 of the 5-step scan sequence:

```
Step 1: Verify session code → session config fetched
Step 2: Scan student-ID QR → student record fetched (incl. face_embedding)
Step 3: GPS geofence validation (parallel)
Step 4: Face liveness challenge + embedding comparison
Step 5: Write attendance record
```

### 4.1 Liveness Challenge (D31)

A **fixed sequence** — no randomization:

1. **Blink** — user closes and opens eyes; EAR drops below threshold then recovers
2. **Turn left** — user rotates head ~30° left; detected via face mesh landmark shift
3. **Turn right** — user rotates head ~30° right

All processing is **client-side** via MediaPipe Face Mesh WASM. The client
generates:

```json
{
  "liveness_evidence": {
    "blink_detected": true,
    "left_turn_detected": true,
    "right_turn_detected": true,
    "timestamps_ms": [1200, 3400, 5100],
    "ear_values": [0.18, 0.31, 0.29, 0.33],
    "pnp_vectors": [[...], [...], [...]]
  }
}
```

This evidence bundle is sent to the server with the scan request. Server-side
grading validates the heuristic signals (EAR thresholds, PnP rotation angles)
to confirm the liveness proof is genuine.

### 4.2 Embedding Comparison

After liveness passes, the client compares the live camera frame's embedding
against the cached enrolled embedding using **cosine similarity**:

```
score = cosine_similarity(live_embedding, enrolled_embedding)
```

The live embedding is generated client-side using the same face-api.js ResNet
model (128-d output).

### 4.3 Score Bands & Outcomes

| Score Range                            | Outcome         | Action                                                                                                                                                                                                                          |
| -------------------------------------- | --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ≥ `FACE_MATCH_THRESHOLD` (0.70)        | **Pass**        | Proceed to step 5; record `face_match_score`                                                                                                                                                                                    |
| `FACE_REVIEW_BAND_LOW` (0.65) – 0.70 | **Review flag** | Proceed to step 5 (record saved), but the attendance record is flagged in `liveness_review` for admin manual review. Tie-break: re-check against individual angle vectors; if any angle ≥ `FACE_MATCH_THRESHOLD`, auto-approve. |
| < `FACE_REVIEW_BAND_LOW` (0.65)        | **Fail**        | Scan **rejected**; `rejection_reason = 'face_mismatch'` is recorded inside the `liveness_evidence` JSONB bundle (not a dedicated column); student may retry. |

Thresholds are configurable via environment variables:

| Variable                 | Default | Description                                            |
| ------------------------ | ------- | ------------------------------------------------------ |
| `FACE_MATCH_THRESHOLD`   | `0.70`  | Minimum cosine similarity for auto-pass                |
| `FACE_REVIEW_BAND_LOW`   | `0.65`  | Lower bound of review-flag band                        |
| `FACE_EMBEDDING_VERSION` | `1`     | Embedding format version (for future model migrations) |

### 4.4 Offline Verification (D30)

When the device is offline:

1. The client performs liveness challenge + embedding comparison locally using the
   cached embedding from IndexedDB.
2. The computed `face_match_score` and `liveness_evidence` are stored in the local
   sync queue.
3. On sync, the server validates the evidence bundle (re-checks EAR/PnP heuristics
   server-side) and records the score. The server does **not** re-run the embedding
   comparison — it trusts the client's score but validates the liveness proof.
4. If the enrolled embedding was revoked/updated between the offline scan and sync,
   the server marks the record with a `liveness_review` flag for manual inspection.

---

## 5. Evidence Bundle Schema

Submitted with every scan request (online or queued offline):

```json
{
  "student_number": "24-2111",
  "session_id": 582,
  "gps": {
    "latitude": 10.3157,
    "longitude": 123.8854,
    "accuracy_meters": 8.2
  },
  "liveness": {
    "blink_detected": true,
    "left_turn_detected": true,
    "right_turn_detected": true,
    "timestamps_ms": [1200, 3400, 5100],
    "ear_values": [0.18, 0.31, 0.29, 0.33],
    "pnp_vectors": [
      [0.01, 0.02, 0.99],
      [0.15, 0.03, 0.98],
      [-0.14, 0.02, 0.98]
    ]
  },
  "face_match_score": 0.8234,
  "scanned_via": "qr_camera",
  "scanned_at": "2026-08-25T07:12:33Z"
}
```

The server stores the full bundle in `attendance_records.liveness_evidence`
(JSONB) and the numeric score in `attendance_records.face_match_score`
(NUMERIC(5,4)).

---

## 6. API Endpoints

| Method | Path                                         | Role    | Description                                                                               |
| ------ | -------------------------------------------- | ------- | ----------------------------------------------------------------------------------------- |
| POST   | `/admin/face-enrollment/{student_id}`        | Admin   | Upload 3 images (multipart); server generates + stores embedding                          |
| GET    | `/admin/face-enrollment/{student_id}/status` | Admin   | Check enrollment status, version, enrolled_at                                             |
| GET    | `/student/me/face-embedding`                 | Student | Version-gated pull; returns embedding + version only if version > client's cached version |

---

## 7. Known Limitations

| Limitation         | Status                | Notes                                                                                                                                                                                                                      |
| ------------------ | --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Sibling confusion  | **Accepted** (D31)    | Siblings may have similar embeddings; treated as a known limitation per instructor guidance. Future work: PAD CNN for anti-spoofing (out of scope).                                                                        |
| Photo/video replay | Mitigated by liveness | Fixed-sequence blink + turn challenges make static-photo replay infeasible. Video replay of a live person remains a theoretical vector (acknowledged).                                                                     |
| Model staleness    | Version migration     | If the face-api.js model is updated (changing embedding dimensions), `FACE_EMBEDDING_VERSION` is bumped and all students must be re-enrolled. The pull-on-login handshake detects version mismatch and forces re-download. |

---

## 8. Cross-References

| Topic                       | Document                                       |
| --------------------------- | ---------------------------------------------- |
| Scan flow integration       | [offline-first.md](offline-first.md)           |
| Security threat model       | [security-model.md](security-model.md)         |
| Database schema             | [migration-strategy.md](migration-strategy.md) |
| Data flow diagrams          | [data-flow.md](data-flow.md)                   |
| Student manual (scan steps) | `docs/guides/student-manual.md`                |
| Admin manual (enrollment)   | `docs/guides/admin-manual.md`                  |
| Face enrollment guide       | `docs/guides/face-enrollment-guide.md`         |
