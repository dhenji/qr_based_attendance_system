# Face Enrollment & Verification Architecture

> **Decisions covered:** D27–D31, D43

## 1. Overview

Face enrollment is an admin-captured flow; the scan currently runs a liveness
challenge and accepts a client-asserted match score. **Server-side embedding
comparison is not implemented** — see §4.2 and §7. It is **not** the primary
authentication method: student identity comes from the authenticated account,
and the biometric step is a spoof-mitigation signal layered on top of the
session code, ID confirmation, and geofence checks.

Key properties:

- **Admin-enrolled, not self-enrolled** (D28): only administrators may upload face
  photos. Students cannot upload their own face data. Real embedding generation
  is not implemented; enrollment stores a placeholder.
- **3-photo enrollment** (D43): front, left, right — chosen over 1 (too brittle) and
  5 (diminishing returns).
- **Pull-on-login distribution** (D29): devices fetch the latest embedding on login
  by comparing a version integer; no push/WebSocket infrastructure required.
- **Offline-capable** (D30): the queue stores liveness evidence; no embedding
  comparison is implemented on either side, so only evidence and the submitted
  score sync to the server.

---

## 2. Enrollment Flow (Admin)

```
Admin picks student → Student Management → Enroll face modal
        │
        ▼
┌─────────────────────────────────┐
│  Select 3 image files           │
│  1. Front                       │
│  2. Left profile                │
│  3. Right profile               │
└────────────┬────────────────────┘
             │
             ▼
    Server validates non-empty, size, image/*
        │
        ├─ FAIL → 400 invalid_image, show reason
        │
        ▼
    All 3 valid
        │
        ▼
Design: server generates 128-d embedding per photo (face-api.js ResNet, D28)
        │  ⚠ NOT IMPLEMENTED — no inference runs. The server writes a zero-filled
        │  placeholder from `_stub_embedding_blob` ("mean" and all three angle
        │  vectors 0.0, "stub": true), matching the shape below so that swapping
        │  in the real pipeline only changes that one builder.
        ▼
Stores ONE JSON blob in students.face_embedding BYTEA (plaintext today)
        │
        ├─ Bumps face_embedding_version
        ├─ Sets face_enrolled_at = NOW()
        ├─ Overwrites any previous enrollment (supersedes old vectors)
        │
        ▼
Enrollment is recorded; the scan still runs liveness only (no face match)
```

### 2.1 Quality Gates — Not Implemented

⚠ **Design only.** The shipped admin UI uploads three selected files; neither the
browser nor the server runs brightness, face-size, single-face, centering,
sharpness, or eyes-open checks. The server validates `content_type`, size, and
non-empty bytes (`face_enrollment/service.py:41-60`); the UI filters by extension
and 5 MB (`frontend/src/lib/features/admin/schema.ts`).

Consequently `no_face_detected`, `multiple_faces` and `quality_too_low` appear in
`api-contracts.md` but have **no exception class in the tree**
(`face_enrollment/exceptions.py` defines only `InvalidImageException`), and the
server never raises them. The table below is the design specification, not the
build:

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
with AES-256-GCM as the D28 design (see §5). The values below are illustrative; the
shipped blob is zero-filled.

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

- **`mean`** (128 floats): shape-only placeholder; in the D28 design it would be
  the **primary comparison target** during verification. No comparison exists in
  the current build.
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
| `students.face_embedding`         | BYTEA NULL       | Placeholder blob (encryption not implemented) |
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
    │                 Server returns { embedding: <base64 placeholder>, version: N }
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
  "embedding": "<base64 iv+ciphertext; server blob is plaintext>",
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

- When an admin re-enrolls a student (new 3-photo upload), the server
  **overwrites** the existing embedding blob and increments
  `face_embedding_version`.
- The next time the student logs in, the pull-on-login handshake detects the
  version bump and re-downloads the new embedding.
- Historical attendance records retain the `face_match_score` submitted at scan
  time; re-enrollment does not retroactively alter past scores.

### 3.3 Revocation Policy

| Trigger                                | Action                                                    |
| -------------------------------------- | --------------------------------------------------------- |
| Student archived (`is_active = false`) | `face_embedding` set to NULL **and `face_embedding_version` incremented** (`student/service.py:571-574`) |
| Admin manually revokes face data       | ⚠ **Not reachable.** `revoke_face_enrollment` exists as a service method, but no route exposes it, so no admin can trigger this today |
| Student graduates / transfers out      | Handled by archive flow above                             |

Both triggers increment the version rather than leaving it alone: that is what invalidates a
cached copy on the device. The original row claiming the version is "NOT reset" was wrong —
archive bumps it, same as the revoke path it was contrasted with.

When `face_embedding IS NULL`, the scan flow does not check it at all — there is
no face-match gate to skip, and step 4 (liveness) runs regardless.
⚠ **The `liveness_evidence: "face_not_enrolled"` branch below does not exist** — that string is
in no source file. The student is not blocked, but the "flagged in the liveness review queue"
outcome is likewise unverified: the review queue is read by the admin liveness dashboard from
records whose status is pending, and an unenrolled student produces no such record. Treat this
row as specified-but-unimplemented.

---

## 4. Verification Flow (During Scan)

The current scan integration is D27 step 4 as amended by ADR-083:

```
Step 1: Verify session code → session config fetched
Step 2: Confirm student ID → resolved from the authenticated account (no QR)
Step 3: GPS geofence validation (client pre-check; server re-validates)
Step 4: Face liveness challenge; client submits evidence + placeholder score
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
    "head_turn_left": true,
    "head_turn_right": true,
    "ear_samples": [0.18, 0.31, 0.29, 0.33],
    "pnp_evidence": { "yaw": 12.5 }
  }
}
```

This evidence bundle is sent to the server with the scan request. Server-side
grading checks the submitted heuristic signals (three booleans, the EAR mean,
and non-empty PnP evidence); it does not observe the user. See
[security-model.md](security-model.md) *Client-Asserted Biometrics*.

### 4.2 Embedding Comparison — Not Implemented

No embedding comparison exists. The enrollment path stores a zero-filled
placeholder blob (`_stub_embedding_blob`), and the scan path never reads the
stored embedding. The client sends `face_match_score`; the shipped client sends
the placeholder `1.0`. The server only applies the thresholds below to that
number. A future implementation must generate real embeddings and move the
comparison server-side.

### 4.3 Score Bands & Outcomes

These bands apply to the **submitted** `face_match_score`, not to a measured
similarity:

| Score Range                            | Outcome         | Action                                                                                                                                                                                                                          |
| -------------------------------------- | --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ≥ `FACE_MATCH_THRESHOLD` (0.70)        | **Pass**        | Proceed to step 5; record `face_match_score`                                                                                                                                                                                    |
| `FACE_REVIEW_BAND_LOW` (0.65) – 0.70 | **Review flag** | Proceed to step 5 (record saved) and route the record to the admin liveness review queue. There is no per-angle re-check. |
| < `FACE_REVIEW_BAND_LOW` (0.65)        | **Fail**        | Scan **rejected** with `403 face_mismatch`; no attendance row is written; student may retry. |

Thresholds are configurable via environment variables:

| Variable                 | Default | Description                                            |
| ------------------------ | ------- | ------------------------------------------------------ |
| `FACE_MATCH_THRESHOLD`   | `0.70`  | Score at or above which the submitted value auto-passes |
| `FACE_REVIEW_BAND_LOW`   | `0.65`  | Lower bound of the review band                         |
| `FACE_EMBEDDING_VERSION` | `1`     | Embedding format version (for future model migrations) |

### 4.4 Offline Verification (D30)

When the device is offline:

1. The client performs the liveness challenge; no embedding comparison is
   performed.
2. `liveness_evidence` is stored in the local sync queue. The replay path
   supplies the same placeholder `face_match_score`.
3. On sync, the server resolves the student from the token and grades the
   evidence (re-checks the submitted EAR/PnP signals). It does **not** re-run an
   embedding comparison.
4. There is no enrolled-embedding version check in the scan path today; a future
   implementation must add one before claiming offline biometric verification.

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
  "face_match_score": 1.0,
  "scanned_via": "qr_camera",
  "scanned_at": "2026-08-25T07:12:33Z"
}
```

`student_number` is a confirmation check only — the server resolves the student
from the bearer token. `scanned_via` defaults to `qr_camera` because the SPA does
not send it today. `face_match_score` is the client placeholder, not a measured
similarity.

The server stores the full bundle in `attendance_records.liveness_evidence`
(JSONB) and the numeric score in `attendance_records.face_match_score`
(NUMERIC(5,4)). Key names match the scan request contract in
[api-contracts.md](api-contracts.md).

---

## 6. API Endpoints

| Method | Path                                         | Role    | Description                                                                               |
| ------ | -------------------------------------------- | ------- | ----------------------------------------------------------------------------------------- |
| POST   | `/admin/face-enrollment/{student_id}`        | Admin   | Upload 3 images (multipart); server stores a placeholder embedding (no generation)         |
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
| Server-side face matching | **Not implemented** | No embedding comparison exists anywhere. The stored embedding is a zero-filled placeholder (`_stub_embedding_blob`), the scan never reads it, and `face_match_score` is a client-supplied value. The shipped client sends `1.0`. |
| Sibling confusion  | **Not applicable today** | Siblings may have similar embeddings, but no comparison exists, so the risk is not currently exercised. Future work: server-side matching + PAD CNN (out of scope).                                                    |
| Photo/video replay | Partially mitigated   | The fixed blink + turn challenge raises the cost of casual replay, but the evidence is client-asserted; a modified client can forge it. Video replay remains a theoretical vector (acknowledged).                          |
| Model staleness    | Design only           | The current enrollment path writes a stub, so there is no model-generated embedding to migrate. If a real face-api.js/MediaPipe pipeline is added, bump `FACE_EMBEDDING_VERSION` and re-enroll the roster.                  |

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
