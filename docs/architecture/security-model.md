# Security Model

> Threat model, mitigations, and security posture for the QR-Based Attendance
> System. Every mitigation cites the governing decision from §2 of the
> DOCS_REFACTOR_PLAN.md.

---

## Threat Model

| #   | Threat                                                     | Severity | Mitigation                                                                                                                                                                                                                          | Decision                                 |
| --- | ---------------------------------------------------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------- |
| T1  | **Buddy punching** — student scans for absent friend       | High     | Sequential 5-step scan: session code → student-ID QR → GPS geofence → face liveness → face match. All steps must pass server-side. No shortcut allowed.                                                                             | D27, D31                                 |
| T2  | **Photo/video replay** — student shows phone photo of face | High     | Liveness challenge (blink → turn left → turn right) with MediaPipe Face Mesh WASM. EAR (Eye Aspect Ratio) detects blink; PnP (Perspective-n-Point) detects head rotation. Fixed sequence, not random — prevents pre-recorded video. | D31                                      |
| T3  | **QR relay** — student sends session QR to off-site friend | Medium   | GPS geofence (Haversine) validates student device location against course/session coordinates. Offline scans validated on sync; `session_expired` rejection for late submissions.                                                   | D12, D16, D27                            |
| T4  | **Sibling confusion** — twin/brother scans                 | Low      | Face embedding comparison (cosine similarity ≥ 0.7 threshold). Known limitation: acknowledged by instructor as accepted risk. No PAD CNN (class-level face anti-spoofing) in scope.                                                 | D31                                      |
| T5  | **GPS spoof** — fake GPS coordinates                       | Medium   | Client-side GPS validation is UX-only; server re-validates on sync. Device integrity attestation (future). Known gap: spoofed GPS passes server check if `scanned_at` is valid. Accepted for MVP.                                   | — (no formal decision; MVP-accepted gap) |
| T6  | **Token theft** — JWT stolen                               | High     | Short-lived JWTs (15 min access, 7 day refresh). MFA available via TOTP. bcrypt for password hashing. Account lockout after failed attempts.                                                                                        | D32                                      |
| T7  | **Session code brute-force**                               | Medium   | HMAC-derived 6–8 char codes from random secret. 62^8 ≈ 2.18 × 10^14 possibilities. Rate-limited verification endpoint. Codes expire with session.                                                                                   | D18                                      |
| T8  | **Offline scan manipulation** — modify `scanned_at`        | Medium   | Server compares `scanned_at` against `session.expires_at`. Expired → `rejected` with reason `session_expired`. Client timestamp is untrusted input.                                                                                 | D16                                      |
| T9  | **Embedding theft from device**                            | Medium   | Embeddings encrypted at rest in IndexedDB via WebCrypto AES-GCM with device-unique non-extractable key. Server never stores plaintext embeddings.                                                                                   | D28                                      |
| T10 | **Excuse abuse** — student fabricates excuse               | Low      | Excuse requests require professor approval. Prof-initiated excuses have audit trail (`excused_by`, `excused_at`). Evidence attachments stored immutably in S3-compatible storage.                                                   | D20, D21, D24                            |
| T11 | **Man-in-the-middle**                                      | Medium   | HTTPS everywhere (production). CORS restricts frontend origin. Session QR payloads are HMAC-signed (tamper-evident).                                                                                                                | D18                                      |
| T12 | **DB dump exfiltration**                                   | High     | Backups encrypted AES-256-GCM with key from env (`BACKUP_ENCRYPTION_KEY`). Key rotation tracked via `encryption_key_version`.                                                                                                       | D39                                      |

---

## HMAC Session Code Scheme (D18)

```
secret (from env, server-only)
   │
   ▼
HMAC-SHA256(secret, session_id + timestamp)
   │
   ▼
Base62-truncate to 6–8 chars → session code
   │
   ▼
Stored in sessions.code (unique, indexed)
   │
   ▼
QR payload includes code + HMAC signature
   │
   ▼
Student scans QR or types code → server verifies
```

**Properties:**

- Codes are non-sequential, non-guessable
- Same session always produces same code (deterministic HMAC)
- Different sessions produce different codes (session_id input)
- Codes are invalidated when session expires (server rejects)

---

## Authentication & Authorization

### Claim-Based Registration (OTP)

1. Admin imports student/professor record with email
2. User visits `/auth/register` → enters email → receives 6-digit OTP via email
3. OTP verified → user sets password → account activated
4. One-time use; OTP expires after 10 minutes

### JWT Structure

```json
{
  "sub": "user_id",
  "role": "student|professor|admin",
  "exp": 1724592000,
  "iat": 1724591100
}
```

- Access token: 15-minute expiry
- Refresh token: 7-day expiry (httpOnly cookie)
- Role-based access: `Depends(require_role(Role.admin))` in FastAPI

### Role Hierarchy

| Role        | Access                                                      |
| ----------- | ----------------------------------------------------------- |
| `admin`     | All endpoints + system settings + backup + analytics        |
| `professor` | `/professor/*` — own courses, sessions, attendance, reports |
| `student`   | `/student/*` — own scan, history, schedule, excuse requests |

---

## Password & Account Security

| Control                | Implementation                        |
| ---------------------- | ------------------------------------- |
| Hashing                | bcrypt (12 rounds)                    |
| Lockout                | 5 failed attempts → 15-minute lockout |
| MFA                    | TOTP (RFC 6238) via authenticator app |
| Password policy        | Min 8 chars, mixed case + number      |
| `must_change_password` | Flag on first login / admin reset     |
| Security question      | Stored hashed, used for recovery      |

---

## Biometric Security

### Face Embedding Encryption (D28)

```
Server:
  3 photos → face-api.js ResNet → 128-d vectors per angle
  → JSON blob: {"mean":[128f], "angles":{"front":[128f],"left":[128f],"right":[128f]}}
  → AES-256-GCM encrypt with server key
  → Store BYTEA in students.face_embedding

Client:
  Pull encrypted blob on login (version-gated)
  → Decrypt with device key (WebCrypto, non-extractable)
  → Cache in IndexedDB (encrypted at rest)
  → Use for offline face comparison
```

**Thresholds:**

- ≥ 0.75: Pass (high confidence match)
- 0.65–0.75: Review flag → routed to liveness review queue
- < 0.65: Fail

### Liveness Protocol (D31)

Fixed sequence: **blink → turn left → turn right**

| Check      | Method                                       | Evidence            |
| ---------- | -------------------------------------------- | ------------------- |
| Blink      | EAR (Eye Aspect Ratio) < 0.25 for ≥ 3 frames | `ear_samples` array |
| Turn left  | PnP head pose yaw < -15°                     | `pnp_evidence.yaw`  |
| Turn right | PnP head pose yaw > +15°                     | `pnp_evidence.yaw`  |

All processing client-side (MediaPipe Face Mesh WASM). Only scores/evidence
sync to server for audit. Server re-validates evidence plausibility.

---

## Evidence Bundle Immutability

Excuse evidence attachments (photos, documents) are:

1. Uploaded to S3-compatible storage (Supabase Storage / R2 / S3)
2. Stored with content-addressable key (SHA-256 of file)
3. DB stores URL reference only — no re-upload, no overwrite
4. Same storage backend as backups (`ATTACHMENTS_STORAGE_TYPE`)

---

## Audit Log Coverage

All sensitive operations are logged in the audit trail:

| Action                                           | Logged |
| ------------------------------------------------ | ------ |
| Student enrollment/unenrollment                  | Yes    |
| Professor assignment changes                     | Yes    |
| Excuse create/approve/revoke                     | Yes    |
| Session open/close                               | Yes    |
| Face enrollment/re-enrollment                    | Yes    |
| Backup create/restore                            | Yes    |
| Academic structure changes (program/year/course) | Yes    |
| System settings changes                          | Yes    |
| Account lockout/unlock                           | Yes    |
| Failed login attempts                            | Yes    |

---

## Non-Goals

These are **explicitly out of scope** for this system:

| Non-Goal                                    | Rationale                                                                                                              |
| ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| **PAD CNN** (Presentation Attack Detection) | Class-level face anti-spoofing not required for MVP. Liveness challenge is sufficient per instructor guidance.         |
| **Sibling confusion resolution**            | Acknowledged as known limitation (D31). Instructor accepted; treated as future assignment.                             |
| **Security-disabled sessions**              | NEVER implement "mark all present" or sessions with security bypass (D25). Cancelled class = no session or Excuse All. |
| **Remote/online relaxation of liveness**    | Remote classes may use larger geofence, but liveness remains mandatory (D26).                                          |

---

## Decision ID Reference

| Decision | Security Relevance                                  |
| -------- | --------------------------------------------------- |
| D12      | Session duration expiry — scan window boundaries    |
| D16      | Offline `scanned_at` validation — anti-backdate     |
| D17      | Classroom override — geofence source selection      |
| D18      | Session QR payload — HMAC signing, versioned schema |
| D25      | Never security-disabled sessions                    |
| D26      | Liveness mandatory even for remote classes          |
| D27      | 5-step sequential scan flow                         |
| D28      | Face embedding encryption at rest                   |
| D29      | Embedding pull-on-login (version-gated)             |
| D30      | Offline verification uses cached embedding          |
| D31      | Liveness protocol (fixed sequence, EAR + PnP)       |
| D32      | Profile read-only (identity admin-managed)          |
| D39      | Backup encryption (AES-256-GCM)                     |
