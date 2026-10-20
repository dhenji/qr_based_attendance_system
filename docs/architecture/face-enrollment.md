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
Server generates 128-d embedding per photo (recognition model — none installed, D28)
        │  ⚠ NOT IMPLEMENTED — no inference runs, and no face-recognition model
        │  exists in the repository. The only model the project ships is MediaPipe
        │  FaceLandmarker (`frontend/static/models/face_landmarker.task`), which
        │  produces landmarks and blendshapes, not identity embeddings. The server
        │  writes a zero-filled placeholder from `_stub_embedding_blob` ("mean" and
        │  all three angle vectors 0.0, "stub": true), matching the shape below so
        │  that swapping in the real pipeline only changes that one builder.
        ▼
Stores ONE JSON blob in students.face_embedding BYTEA (plaintext today)
        │
        ├─ Bumps face_embedding_version
        ├─ Sets face_enrolled_at = NOW()
        ├─ Overwrites any previous enrollment (supersedes old vectors)
        │
        ▼
Student can now use face verification in scan sessions
```

### 2.1 Quality Gates

⚠ **Enforcement point: nowhere, today.** These six gates are **specified but not
implemented on either side**. The admin upload UI validates file extension, non-emptiness
and a 5 MB cap (`frontend/src/lib/features/admin/schema.ts:70-77`); the server validates
`content_type`, size, and that the bytes are non-empty
(`face_enrollment/service.py:41-60`) — nothing more. There is no camera capture flow and
no biometric analysis in the browser: the photos are uploaded as files.

Consequently `no_face_detected`, `multiple_faces` and `quality_too_low` appear in
`api-contracts.md` but have **no exception class in the tree**
(`face_enrollment/exceptions.py` defines only `InvalidImageException`) and **no
implementation that could raise them**. The thresholds below are the design; implementing
them client-side (MediaPipe can supply face count, face size and centring) is the work
that is still to do.

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

A single JSON blob stored in `students.face_embedding` (BYTEA column) — **plaintext today**,
with AES-256-GCM as the D28 design (§2.2):

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

- ⚠ **No producer.** The vectors above have **no generator**: no face-recognition model
  is installed in this repository. The only model the project ships is MediaPipe
  FaceLandmarker (`frontend/static/models/face_landmarker.task`), which yields landmarks
  and blendshapes — not identity embeddings. Producing them means adding a recognition
  model (e.g. an ArcFace/InsightFace ONNX model) that can also run in the browser, so the
  offline path keeps working.
- **`mean`** (128 floats): element-wise average of the three angle vectors. Used as
  the **primary comparison target** during verification (D28).
- **`angles`** (3 × 128 floats): per-angle vectors, part of the D28 design for
  **tie-breaking** when the mean score falls in the review band (0.65–0.70).
  ⚠ **Not implemented.** The stub writes three zero vectors for shape parity, and
  nothing reads them back — there is no per-angle comparison anywhere in the
  codebase, so the tie-break re-check that §4's review band describes does not
  happen. The single `face_match_score` the client submits **is** still compared
  against the threshold to flag the review band (`attendance/service.py:519`);
  only the angle-level second opinion is missing.
- **Encryption**: ⚠ **Not implemented.** The design is AES-256-GCM with a server-side
  key, decrypted only on the server during enrollment or when serving the embedding
  to a verified student device (D29). What the server writes today is plain
  `json.dumps(...).encode("utf-8")` (`face_enrollment/service.py:38`) — no cipher,
  no key. The BYTEA column is real and holds the blob; only the encryption is missing,
  which is what T9 tracks.

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
  "embedding": "<base64-encoded blob — plaintext today, encrypted under D28>",
  "version": 42,
  "cached_at": "2026-08-25T10:30:00Z"
}
```

⚠ **Correcting §2.1's counterpart — the device key is not derived from a salt or
passphrase.** The client calls `crypto.subtle.generateKey()`, producing a non-extractable
AES-GCM `CryptoKey` that it stores directly as a `CryptoKey` in IndexedDB. There is no salt,
no user passphrase, and no keychain step. (IndexedDB can hold a non-extractable key, which is
what makes this safe without a passphrase — and the encrypt-before-cache step is real
(`encryptBlob`, a random IV per write). The gap T9 tracks is server-side, where the BYTEA column
holds plaintext.)

Decryption is client-side only; the raw embedding never touches localStorage unencrypted.

### 3.2 Re-enrollment Policy

- When an admin re-enrolls a student (new 3-photo capture), the server
  **overwrites** the existing embedding blob and increments
  `face_embedding_version`.
- The next time the student logs in, the pull-on-login handshake detects the
  version bump and re-downloads the new embedding.
- Historical attendance records retain the `face_match_score` captured at scan
  time; re-enrollment does not retroactively alter past verification scores.

### 3.3 Revocation Policy

| Trigger                                | Action                                                    |
| -------------------------------------- | --------------------------------------------------------- |
| Student archived (`is_active = false`) | `face_embedding` set to NULL **and `face_embedding_version` incremented** (`student/service.py:571-574`) |
| Admin manually revokes face data       | ⚠ **Not reachable.** `revoke_face_enrollment` exists as a service method, but no route exposes it, so no admin can trigger this today |
| Student graduates / transfers out      | Handled by archive flow above                             |

Both triggers increment the version rather than leaving it alone: that is what invalidates a
cached copy on the device. The original row claiming the version is "NOT reset" was wrong —
archive bumps it, same as the revoke path it was contrasted with.

When `face_embedding IS NULL`, the scan flow (D27) skips step 4 (face check).
⚠ **The `liveness_evidence: "face_not_enrolled"` branch below does not exist** — that string is
in no source file. The student is not blocked, but the "flagged in the liveness review queue"
outcome is likewise unverified: the review queue is read by the admin liveness dashboard from
records whose status is pending, and an unenrolled student produces no such record. Treat this
row as specified-but-unimplemented.

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

All processing is **client-side** via MediaPipe FaceLandmarker WASM. The client
generates:

```json
{
  "liveness_evidence": {
    "blink_detected": true,
    "head_turn_left": true,
    "head_turn_right": true,
    "ear_samples": [0.18, 0.31, 0.29, 0.33],
    "pnp_evidence": { "yaw": 12.5 }
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

The live embedding is generated client-side using the same recognition model
(128-d output). ⚠ **No recognition model ships today** — the browser only has
MediaPipe FaceLandmarker, which produces landmarks, not embeddings. The comparison
below therefore has nothing to run against; see §2.2 for what the server actually
stores.

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
    "lat": 10.3157,
    "lng": 123.8854,
    "accuracy": 8.2
  },
  "liveness_evidence": {
    "blink_detected": true,
    "head_turn_left": true,
    "head_turn_right": true,
    "ear_samples": [0.18, 0.31, 0.29, 0.33],
    "pnp_evidence": {
      "yaw": 12.5
    }
  },
  "face_match_score": 0.8234,
  "scanned_via": "qr_camera",
  "scanned_at": "2026-08-25T07:12:33Z"
}
```

The server stores the full bundle in `attendance_records.liveness_evidence`
(JSONB) and the numeric score in `attendance_records.face_match_score`
(NUMERIC(5,4)). Key names match the scan request contract in
[api-contracts.md](api-contracts.md).

---

## 6. API Endpoints

| Method | Path                                         | Role    | Description                                                                               |
| ------ | -------------------------------------------- | ------- | ----------------------------------------------------------------------------------------- |
| POST   | `/admin/face-enrollment/{student_id}`        | Admin   | Upload 3 images (multipart); server generates + stores embedding                          |
| GET    | `/admin/face-enrollment/{student_id}`       | Admin   | Check enrollment status, version, enrolled_at (returns `{ enrolled, face_enrolled_at?, face_embedding_version? }`) |
| GET    | `/student/me/face-embedding`                 | Student | Version-gated pull; returns embedding + version only if version > client's cached version |

`GET /student/me/face-embedding` returns **404 `face_embedding_not_found`** when the student has
no embedding. That code is defined in `features/student/exceptions.py` (not `face_enrollment`’s, which
raises only `invalid_image`) and is documented in `api-contracts.md:1205`, but was missing from
this table.

The enrollment feature raises exactly one code — `invalid_image` (§2.1); the 404 above comes
from the student slice. `no_face_detected`, `multiple_faces` and `quality_too_low` are contract
codes with no implementation anywhere.

---

## 7. Known Limitations

| Limitation         | Status                | Notes                                                                                                                                                                                                                      |
| ------------------ | --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Sibling confusion  | **Accepted** (D31)    | Siblings may have similar embeddings; treated as a known limitation per instructor guidance. Future work: PAD CNN for anti-spoofing (out of scope).                                                                        |
| Photo/video replay | Mitigated by liveness | Fixed-sequence blink + turn challenges make static-photo replay infeasible. Video replay of a live person remains a theoretical vector (acknowledged).                                                                     |
| Model staleness    | Version migration     | If the recognition model is updated (changing embedding dimensions), `FACE_EMBEDDING_VERSION` is bumped and all students must be re-enrolled. The pull-on-login handshake detects version mismatch and forces re-download. ⚠ The mismatch is detected against the **per-student** `students.face_embedding_version` column (`student/service.py:333`), not the `FACE_EMBEDDING_VERSION` env var — the env var is the format the server writes at enrollment time, and the two are compared via that column. |

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
