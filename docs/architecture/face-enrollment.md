# Face Enrollment & Verification Architecture

> Layered, code-grounded anti-spoofing docs:
> [`docs/architecture/anti-spoofing.md`](anti-spoofing.md). This file keeps the
> enrollment architecture; that file holds the consolidated per-layer audit.

> **Decisions covered:** D27–D31, D43

## 1. Overview

Face enrollment is an admin-captured flow. The server now generates a real
512-d embedding (MobileFaceNet, with a landmark-based fallback) from the
uploaded photos and compares it against the live embedding during a scan
(`attendance/service.py::submit_scan`). The biometric step remains a
spoof-mitigation signal, not the primary authentication method: student
identity comes from the authenticated account.
Key properties:

- **Admin-enrolled, not self-enrolled** (D28): only administrators may upload face
  photos. Students cannot upload their own face data. Embeddings are generated
  server-side with MobileFaceNet ONNX when available (landmark fallback otherwise).- **3-photo enrollment** (D43): front, left, right — chosen over 1 (too brittle) and
  5 (diminishing returns).
- **Pull-on-login distribution** (D29): devices fetch the latest embedding on login
  by comparing a version integer; no push/WebSocket infrastructure required.
- **Offline-capable** (D30): the queue stores liveness evidence; the live
  embedding is generated server-side from the submitted image, so only evidence
  and the image sync to the server.
---

## 2. Enrollment Flow (Admin)

```
Admin picks student → Student Management → Enroll face modal
        │
        ▼
┌─────────────────────────────────┐
│  Capture 3 images (file or cam) │
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
Server generates a 512-d embedding (MobileFaceNet, landmark fallback
        │  otherwise), averages front/left/right, and stores a FACEEMB1 blob
        │  (shared/face_embeddings.serialize_embedding).        ▼
Stores ONE JSON blob in students.face_embedding BYTEA (plaintext today)
        │
        ├─ Bumps face_embedding_version
        ├─ Sets face_enrolled_at = NOW()
        ├─ Overwrites any previous enrollment (supersedes old vectors)
        │
        ▼
Enrollment is recorded; the scan still runs liveness only (no face match)
```

### 2.1 Quality Gates — Implemented

The six biometric gates now run on both sides. The server is authoritative:
`shared/face_quality.py::assess_image_bytes` decodes the upload and runs detection
then brightness, face-size, centering, sharpness, and eyes-open checks, returning
`FaceQualityResult`. The service raises `InvalidImageException` (400),
`NoFaceDetectedException` (400), `MultipleFacesException` (400), or
`QualityTooLowException` (422) accordingly. The client mirrors the thresholds for
usability (`FaceEnrollmentCamera.svelte`, `features/admin/enrollment/quality.ts`)
but the backend re-validates every upload.

**Error handling note:** the detail passed to each exception names the offending
photo (e.g. `front photo: No face detected`), so the API response and the UI
can point at the specific photo/gate that failed. `NoFaceDetectedException` is
imported at module level in `service.py`; do **not** re-import it locally inside
the `except FaceEmbeddingGenerationError` block — Python would then treat the
name as function-local and raise `UnboundLocalError` before the
`no_face_detected` gate branch could run (the cause of the former generic 500
on camera captures). An unexpected server-side failure surfaces as
`500 internal_error`, which the UI maps to an actionable fallback message.

The frontend validates file extension/size via `facePhotoSchema` and now also runs
canvas-based brightness/sharpness/dimension checks before upload; the live camera
flow only auto-captures when all gates pass.

Both camera previews in the app (admin `FaceEnrollmentCamera.svelte` and the
student liveness scanner `FaceScanner.svelte`) mirror the live video + canvas
with `transform: scaleX(-1)` selfie-style; detection still runs on the original
frames, so landmark coordinates and captured images stay unmirrored.

| Gate          | Condition                                                        | Error Message                                                |
| ------------- | ---------------------------------------------------------------- | ------------------------------------------------------------ |
| Brightness    | Mean pixel luminance in [40, 220] (0–255)                        | "Image too dark / too bright — move to better lighting"      |
| Face size     | Detected face bounding box ≥ 15% of image area                   | "Face too small — move closer to the camera"                 |
| Single face   | Exactly 1 face detected in frame                                 | "Multiple faces detected — ensure only your face is visible" |
| Face centered | Face centroid within 30% of image center (horizontal + vertical) | "Face not centered — look directly at the camera"            |
| Sharpness     | Laplacian variance ≥ 50                                          | "Image blurry — hold steady and retry"                       |
| Eyes open     | Eye aspect ratio (EAR) > 0.2 for both eyes                       | "Please keep your eyes open"                                 |

### 2.2 Storage Format

The shipped blob is a real `FACEEMB1` binary embedding
(`shared/face_embeddings.serialize_embedding`), generated server-side during
enrollment (MobileFaceNet ONNX, landmark fallback). It is **plaintext today**;
AES-256-GCM encryption at rest remains unimplemented (D28/T9).

- **`students.face_embedding`** (BYTEA NULL): serialized 512-d embedding
  (`FACEEMB1`), generated from the front/left/right photos.
- **`students.face_embedding_algorithm`** (TEXT): `mobilefacenet-v1` or
  `mediapipe-v1` (landmark fallback).
- **`students.face_embedding_version`** (INT): monotonic; bumped on every write.
- **Encryption**: ⚠ **Not implemented.** The design is AES-256-GCM with a
  server-side key. The BYTEA column holds the plaintext blob today.

Enrollment persists the derived embedding only — the source photos are not
stored or retrievable (privacy, D28). The earlier 128-float `mean`/`angles` JSON design is superseded; verification
compares the enrolled embedding against a server-generated live embedding via
cosine similarity (see §4 / security-model.md).

### 2.3 Supporting Columns

| Column                            | Type             | Purpose                                       |
| --------------------------------- | ---------------- | --------------------------------------------- |
| `students.face_embedding`         | BYTEA NULL       | Real 512-d embedding (encryption not implemented) |
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
    │                 Server returns { embedding: <base64 FACEEMB1 blob>, version: N }
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
| Admin manually revokes face data       | **Reachable** via `DELETE /admin/face-enrollment/{student_id}` (clears blob, bumps version) |
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
Step 4: Face liveness challenge; server computes face match from submitted image
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
grading checks the submitted heuristic signals (three booleans, the EAR mean,
and non-empty PnP evidence); it does not observe the user. See
[security-model.md](security-model.md) *Client-Asserted Biometrics*.

### 4.2 Embedding Comparison — Implemented

Enrollment stores a real `FACEEMB1` embedding blob. During a scan the server
resolves the student from the token, deserializes `students.face_embedding`
and the client-supplied `live_face_embedding`, and computes
`cosine_similarity(ref_emb, live_emb)`. The resulting score drives the bands in
§4.3. The live embedding is derived from MediaPipe landmarks captured during
the liveness challenge; the server cannot verify that provenance.

### 4.3 Score Bands & Outcomes

These bands apply to the **server-computed** similarity between the enrolled and
live embeddings (no longer a client-submitted score):

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
2. `liveness_evidence` and `live_face_embedding` are stored in the local sync
   queue.
3. On sync, the server resolves the student from the token, grades the
   evidence, and computes cosine similarity between the enrolled and live
   embeddings.
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
  "live_face_embedding": "<base64 FACEEMB1 blob>",
  "scanned_via": "qr_camera",
  "scanned_at": "2026-08-25T07:12:33Z"
}
```

`student_number` is a confirmation check only — the server resolves the student
from the bearer token. `scanned_via` defaults to `qr_camera` because the SPA does
not send it today. `live_face_embedding` is derived from landmarks captured
during the liveness challenge; the server compares it to the enrolled template.

The server stores the full bundle in `attendance_records.liveness_evidence`
(JSONB) and the numeric score in `attendance_records.face_match_score`
(NUMERIC(5,4)). Key names match the scan request contract in
[api-contracts.md](api-contracts.md).

---

## 6. API Endpoints

| Method | Path                                         | Role    | Description                                                                               |
| ------ | -------------------------------------------- | ------- | ----------------------------------------------------------------------------------------- |
| POST   | `/admin/face-enrollment/{student_id}`        | Admin   | Upload 3 images (multipart); server validates quality gates and stores a `FACEEMB1` embedding (MobileFaceNet, landmark fallback) |
| GET    | `/admin/face-enrollment/{student_id}`       | Admin   | Check enrollment status, version, enrolled_at (returns `{ enrolled, face_enrolled_at?, face_embedding_version? }`) |
| DELETE | `/admin/face-enrollment/{student_id}`       | Admin   | Revoke enrollment: clears the blob, nulls `face_enrolled_at`, bumps `face_embedding_version` (204) |
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
| Server-side face matching | **Implemented** | The live embedding is generated server-side (MobileFaceNet, with landmark fallback) from the submitted image, then compared via cosine similarity against the stored enrolled embedding; thresholds `FACE_MATCH_THRESHOLD` (0.70) / `FACE_REVIEW_BAND_LOW` (0.65). Provenance remains client-asserted. || Sibling confusion  | **Partially mitigated** | Server-side matching now runs, but no PAD CNN; twin separation remains an accepted risk (D31). |
| Photo/video replay | Partially mitigated   | The fixed blink + turn challenge raises the cost of casual replay, but the evidence is client-asserted; a modified client can forge it. Video replay remains a theoretical vector (acknowledged).                          |
| Model staleness    | Implemented           | Enrollment now generates a real 512-d embedding (MobileFaceNet ONNX, landmark fallback). If the model or algorithm changes, bump `FACE_EMBEDDING_VERSION` and re-enroll the roster. |

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
