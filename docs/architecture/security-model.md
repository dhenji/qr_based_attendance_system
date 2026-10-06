# Security Model

> Threat model, mitigations, and security posture for the QR-Based Attendance
> System. Every mitigation cites the governing decision from the
> [decision log](../project/decision-log.md).

---

## Threat Model

| #   | Threat                                                     | Severity | Mitigation                                                                                                                                                                                                                          | Decision                                 |
| --- | ---------------------------------------------------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------- |
| T1  | **Buddy punching** — student scans for absent friend       | High     | Sequential 5-step scan: session code → student-ID QR → GPS geofence → face liveness → face match. Steps 1–3 are verified server-side; **steps 4–5 are client-asserted** and the server only range-checks them — see *Client-Asserted Biometrics*. No shortcut through steps 1–3.                                                                             | D27, D31                                 |
| T2  | **Photo/video replay** — student shows phone photo of face | High     | Liveness challenge (blink → turn left → turn right) with MediaPipe Face Mesh WASM in the client. The server grades the *submitted* evidence, not a measurement — see *Client-Asserted Biometrics*. This stops an honest client from being tricked, not a determined one. | D31                                      |
| T3  | **QR relay** — student sends session QR to off-site friend | Medium   | GPS geofence (Haversine) validates student device location against course/session coordinates. Offline scans validated on sync; `session_expired` rejection for late submissions.                                                   | D12, D16, D27                            |
| T4  | **Sibling confusion** — twin/brother scans                 | Low      | **Not implemented.** No embedding comparison exists: there is no cosine-similarity code in the backend, and `face_enrollment` stores a zero-filled placeholder blob (`_stub_embedding_blob`), so there is nothing to compare against. The 0.70 threshold in `core/config.py` is applied to the score the *client* submits. Acknowledged by instructor as accepted risk; no PAD CNN in scope. | D31, ADR-068                      |
| T5  | **GPS spoof** — fake GPS coordinates                       | Medium   | Client-side GPS validation is UX-only; server re-validates on sync. Device integrity attestation (future). Known gap: spoofed GPS passes server check if `scanned_at` is valid. Accepted for MVP.                                   | — (no formal decision; MVP-accepted gap) |
| T6  | **Token theft** — JWT stolen                               | High     | Short-lived JWTs (15 min access, 7 day refresh). MFA available via TOTP, revocable by the user. Argon2id for password hashing. Account lockout after failed attempts. A stolen 7-day refresh token outlives an MFA disable — see *Password & Account Security*. | D32                                      |
| T7  | **Session code brute-force**                               | Medium   | HMAC-derived 8-char codes from a server-only secret. 62^8 ≈ 2.18 × 10^14 possibilities. The verify endpoint is rate-limited at 10 attempts/min per IP (`VERIFY_CODE_RATE_LIMIT_*`, `student/router.py`). Codes expire with the session. | D18 |
| T8  | **Offline scan manipulation** — modify `scanned_at`        | Medium   | Server compares `scanned_at` against `session.expires_at`. Expired → `rejected` with reason `session_expired`. Client timestamp is untrusted input.                                                                                 | D16                                      |
| T9  | **Embedding theft from device**                            | Medium   | Client cache encrypted at rest in IndexedDB via WebCrypto AES-GCM with a device-generated non-extractable key. Server stores plaintext JSON today — AES-256-GCM is the D28 design, not implemented.                                                                                                                                       | D28                                      |
| T10 | **Excuse abuse** — student fabricates excuse               | Low      | Excuse requests require professor approval. Prof-initiated excuses have audit trail (`excused_by`, `excused_at`). Evidence attachments stored immutably in S3-compatible storage.                                                   | D20, D21, D24                            |
| T11 | **Man-in-the-middle**                                      | Medium   | HTTPS everywhere (production). CORS restricts frontend origin. Session QR payloads are **unsigned JSON** — the HMAC derives the *code*, not the payload, so a payload is tamperable by anyone who can read it (D18).                                                                                                                | D18                                      |
| T12 | **DB dump exfiltration**                                   | High     | Backups encrypted AES-256-GCM with key from env (`BACKUP_ENCRYPTION_KEY`). Key rotation tracked via `encryption_key_version`.                                                                                                       | D39                                      |

---

## HMAC Session Code Scheme (D18)

```
secret (from env, server-only)
   │
   ▼
HMAC-SHA256(secret, session_id)
   │
   ▼
Base62-truncate to the first 8 chars → session code
   │
   ▼
Stored in sessions.session_code (unique, indexed)
   │
   ▼
QR payload = unsigned JSON {v, code, offering, radius, pw, lw}
   │          (the HMAC above produced `code`; the payload is not signed)
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
2. User visits `/auth/register` → enters email → receives 6-digit OTP via email, then supplies the answer to the security question it returns. Registration is **two** calls (`POST /auth/otp/request`, then `POST /auth/register`) and `security_question` + `security_answer` are mandatory.
3. OTP verified → user sets password → account activated
4. One-time use; OTP expires after 5 minutes

### JWT Structure

```json
{
  "sub": "user_id",
  "role": "student|professor|admin|super_admin",
  "exp": 1724592000,
  "iat": 1724591100
}
```

- Access token: 15-minute expiry
- Refresh token: 7-day expiry, returned in `TokenResponse` body (D51); httpOnly cookie form deferred to Phase 10 (same-origin HTTPS)
- MFA login gating (D51): if `user.mfa_enabled`, `POST /auth/login` returns `{mfa_pending: true, preauth_token}` (5-min JWT `type="preauth"`, grants no access); `POST /auth/mfa/verify` exchanges `{preauth_token, code}` for full token pair
- Forgot-password (ADR-052, supersedes D51's OTP-only deferral): mandatory 4-step — email → security question (Argon2id-hashed answer, 3-attempt cap then lock) → OTP via `OtpPurpose.FORGET_PASSWORD` → new password. Turnstile on step 1 was deferred in ADR-052; it is now implemented as key-gated siteverify (ADR-053).
- Recovery-flow hardening (ADR-056):
  - **Step 1 does not leak account existence.** Unknown emails receive a *deterministic* decoy question (HMAC of the normalized email over `SECURITY_QUESTION_POOL`) and `set: true`, so a given address always returns the same question and the response shape matches the known-email case. This mitigates enumeration rather than eliminating it — the decoy text differs from a real question. Emailing the question instead of returning it would close the gap; deferred.
  - **Steps 3–4 are gated by a signed grant.** Step 2 returns a 5-minute `type="recovery"` JWT. `forget_password` OTP issuance requires it; otherwise `400 invalid_credentials` with a generic message. The grant is rejected by the access-token dependency, so it cannot be replayed for API access.
  - **Only the answer is hashed.** `users.security_question_hash` is readable plaintext under a legacy column name, because step 1 must display the question. The question is non-secret by design (drawn from a small preset pool); the answer is the secret.
- Role-based access: `Depends(require_role(Role.admin))` in FastAPI

### Role Hierarchy

| Role          | Access                                                      |
| ------------- | ----------------------------------------------------------- |
| `super_admin` | All admin access + platform/system-level management         |
| `admin`       | System settings, backup, analytics, users, and the `/admin/*` CRUD trees. Not a wildcard — `require_role` matches the exact role, and `super_admin` is the only superset (`api/deps.py`) |
| `professor`   | `/professor/*` — assigned courses, sessions, attendance, reports |
| `student`     | `/student/*` — own scan, history, schedule, excuse requests |

---

## Password & Account Security

| Control                | Implementation                        |
| ---------------------- | ------------------------------------- |
| Hashing                | Argon2id (memory=64MB, time=3, parallelism=4) |
| Lockout                | 5 failed attempts → 15-minute lockout |
| MFA                    | TOTP (RFC 6238) via authenticator app; user-revocable via `POST /auth/mfa/disable` (password-verified), which also clears the TOTP secret and invalidates every unconsumed backup code |
| Password policy        | Min 8 chars, mixed case + number + symbol (wireframes.md:1903) |
| `must_change_password` | Set by admin **account creation and admin reset only**. There is no first-login trigger |
| Security question      | Answer Argon2id-hashed; question stored readable (see ADR-056) |

Disabling MFA requires the current password, not a fresh TOTP code: reaching the
route at all required completing the MFA challenge at login, so the bearer token
in hand is already proof of the second factor.

**What disabling does not do:** it cannot revoke credentials that already exist.
Tokens are stateless JWTs and there is no revocation list (D32/D51), so a refresh
token minted while MFA was on stays usable until it expires on its own 7-day
life. Someone who logged in before the disable can keep refreshing. Evicting
them needs a per-user `tokens_valid_from` / session-version column checked at
refresh — not built. Until then, disabling MFA reduces the *next* login's
exposure; it is not a way to kick an existing session out.

---

## Biometric Security

### Face Embedding Encryption (D28)

> **Status: designed, not implemented.** What the server stores today is a
> zero-filled placeholder from `_stub_embedding_blob` — a plain JSON blob with
> `"mean"` and all three angle vectors set to `0.0` and `"stub": true`. There is
> no ResNet inference, no AES-GCM step and no encryption code in the feature. The
> pipeline below is the design D28 records. The blob's *shape* is already the
> documented one so swapping the builder is the only change a real pipeline
> needs. The audit-trail exclusion in `_face_snapshot` is implemented and holds
> regardless.

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

The last line — *use for offline face comparison* — has no server-side counterpart
either: no comparison is performed on either side today. See *Client-Asserted
Biometrics*.

**Thresholds:**

- ≥ 0.70: Pass (high confidence match)
- 0.65–0.70: Review flag → routed to liveness review queue
- < 0.65: Fail

### Liveness Protocol (D31)

Fixed sequence: **blink → turn left → turn right**

| Check      | Client-side method                     | Evidence submitted   | Server-side check |
| ---------- | -------------------------------------- | -------------------- | ----------------- |
| Blink      | EAR (Eye Aspect Ratio) per frame       | `ear_samples` array  | mean within `EAR_MEAN_MIN..EAR_MEAN_MAX` (0.05..0.5), ≥ 1 sample |
| Turn left  | PnP head pose yaw < -15°               | `pnp_evidence.yaw`   | `head_turn_left` true, `pnp_evidence` non-empty |
| Turn right | PnP head pose yaw > +15°               | `pnp_evidence.yaw`   | `head_turn_right` true, `pnp_evidence` non-empty |

The thresholds in the left column are what the *client* is expected to apply; the
right column is all the server enforces. An earlier version of this table claimed
"EAR < 0.25 for >= 3 frames" as a server-side rule, which the code has never
enforced — see *Client-Asserted Biometrics* below.

All processing client-side (MediaPipe Face Mesh WASM). Only scores/evidence
sync to server for audit. Server re-validates evidence plausibility.

### Client-Asserted Biometrics

"Re-validates evidence plausibility" above is the whole of it, and it is worth
being precise about what that means, because the threat table (T1, T4) reads as
though the server verifies biometrics. It does not.

| Input | Who computes it | What the server checks |
| --- | --- | --- |
| `liveness_evidence` | client (MediaPipe WASM) | three booleans true; `ear_samples` non-empty; their **mean** within `EAR_MEAN_MIN..EAR_MEAN_MAX` (0.05..0.5); `pnp_evidence` non-empty |
| `face_match_score` | client | within `face_review_band_low` (0.65) and `face_match_threshold` (0.70), both applied to the submitted number |

Both are body fields on `POST /student/attendance/scan`. The server's checks are
arithmetic and truthiness over values the client sent — no measurement, no
image, no embedding comparison. Two specifics worth stating plainly:

- `EAR_SAMPLES_MIN_COUNT` is **1**, so the three-step challenge is satisfiable
  with a single asserted sample per position.
- A client submitting `face_match_score=0.99` always passes and is never routed
  to the liveness review queue. The review band only catches scores a client
  volunteers.

There is also no face *enrollment* pipeline yet: `face_enrollment` stores a
zero-filled placeholder from `_stub_embedding_blob`, so there is no stored vector
to compare against even in principle. That placeholder is why
`api-contracts.md` lists `no_face_detected`, `multiple_faces` and
`quality_too_low` as documented but never raised. (`invalid_image` **is**
raised — it is the one of the four that exists, as
`InvalidImageException`.)

**What this does and does not protect.** Steps 1-3 of the scan — session code,
student-ID QR, GPS geofence — are genuinely server-enforced, which is why T3, T5
and T8 remain accurate: those inputs are re-validated on sync. Steps 4-5 stop an
honest client from being tricked with a photo or coerced into a lazy blink. They
are an integrity signal recorded in the trail, **not an access control** against
a modified client. Recorded as an accepted MVP gap in ADR-068 rather than left
as an apparent oversight; treating `face_match_score` as a measurement is the
mistake that section exists to prevent.

One consequence worth stating for anyone reasoning about the scan pipeline: the
geofence check (`outside_geofence`) is the only *biometric-adjacent* step that can
be bypassed by not participating in it, because `BENCHMARK_MODE` skips it
alongside the liveness check. That is deliberate for load runs and off by default,
but it means a benchmark deployment has no geofence enforcement at all — not a
weakened one, none.

---

## Rate Limits

`shared/rate_limit.py` is a fixed-window limiter keyed on `request.url.path` plus either the
client IP or the normalized email in the JSON body. Exhausting a window raises 429
`rate_limited`. `X-Forwarded-For` is deliberately **not** trusted, so a deployment behind a proxy
rates by the proxy's address unless the limiter is given `key="email"`.

| Route | Key | Limit | Window | Note |
| --- | --- | --- | --- | --- |
| `POST /auth/otp/request` | email | 5 | 60s | OTP send |
| `POST /auth/otp/verify` | email | 5 | 300s | Deliberately the longest window: verification is the brute-forceable step |
| `POST /auth/forgot-password` | email | 5 | 60s | |
| `POST /auth/forgot-password/verify` | email | 5 | 300s | Answer brute-force |
| `POST /auth/login` | **ip + email** | 20 + 5 | 60s | Two limiters on one route: 20/IP alongside the email-keyed 5 |
| `POST /admin/analytics/refresh-risk` | ip | 1 | 60s | Manual trigger, per-IP |
| `POST /student/sessions/verify-code` | ip | 10 | 60s | T7 — brute-force guard on the only unauthenticated-code probe (closes #191) |
| `POST /student/attendance/scan` | ip | 30 | 60s | `SCAN_RATE_LIMIT_MAX_CALLS` / `_WINDOW_SECONDS`; skipped under `BENCHMARK_MODE` |

One endpoint is conspicuously absent, and it is not an oversight worth assuming:

- **`POST /auth/refresh`** — token rotation has no limiter. Rotation is authenticated by the
  refresh token itself, which is high-entropy and already rate-limits its own usefulness (a stolen
  token is usable until it expires, per T6/D32); a limiter would primarily blunt the legitimate
  case of a client retrying with an expired token.

The other one that used to be missing is now throttled:

- **`POST /student/sessions/verify-code`** — limited per IP at 10 attempts/min
  (`VERIFY_CODE_RATE_LIMIT_MAX_CALLS=10`, `..._WINDOW_SECONDS=60`,
  `student/constants.py`). This closes the T7 gap: a code is still 8 base62 chars
  (~2.2 × 10¹⁴ possibilities, which is why T7 stayed Medium rather than High), and now an
  automated probe is additionally throttled.

> **Captcha.** `POST /auth/login` and `POST /auth/forgot-password` call
> `verify_turnstile_token(...)` when a token is supplied, so Turnstile is enforced on those two.

> **HMAC secret.** `_resolve_hmac_secret` prefers `HMAC_SECRET_KEY` and falls back to
> `JWT_SECRET`, raising if neither is set — so code generation works on a deployment configured
> only for JWTs.

> **Recovery lockout.** Too many wrong security answers returns 423 `recovery_locked`
> (`RecoveryLockedException`), distinct from the 423 `account_locked`
> (`AccountLockedException`) that failed logins raise.

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

| Action                                           | Logged | Trail row                                        |
| ------------------------------------------------ | ------ | ------------------------------------------------ |
| Student enrollment/unenrollment                  | Yes    | `enroll` / `enrollment`                         |
| Professor assignment changes                     | Yes    | `assign` / `unassign` on `course_professor`     |
| Excuse create/approve/revoke                     | Yes    | `create` / `approve` / `reject` / `revoke` on `excuse`, plus the `attendance_records` each one restatus |
| Session open/close                               | Yes    | `open` / `close` on `session`                   |
| Face enrollment/re-enrollment                    | Yes    | `update` on `face_enrollment`. `revoke` exists as a service method but **no route exposes it**, so the row it would write is unreachable |
| Backup create/restore                            | Yes    | `create` on `backup`. **Restore is not implemented** — only download |
| Academic structure changes (program/year/course) | Yes    | `create` / `update` / `archive` / `delete`      |
| System settings changes                          | Yes    | `update` on `app_setting`, with the previous value |
| Admin account creation                           | Yes    | `create` on `user`, with the role granted       |
| Account lockout/unlock                           | Yes    | `lock` / `unlock` on `user`. **There is no standalone admin unlock** — an admin clears a lockout by resetting the password, which is audited as `password_reset` |
| Failed login attempts                            | Yes    | `login_failed` on `user`, `performed_by` null    |
| Password reset                                   | Yes    | `password_reset` on `user`, self-service (`performed_by` = the account) or admin-initiated (`performed_by` = the admin) |
| MFA disable                                      | Yes    | `update` on `user` (`mfa_enabled` only)          |
| Liveness review resolve                          | Yes    | `approve` / `reject` on `attendance_record`     |

An admin-initiated reset (`POST /admin/{users,students,professors}/{id}/reset-password`)
issues a temporary password, returns it once, forces `must_change_password`, and
clears the lockout — the counter, `is_locked` and `locked_at` — because an admin
rescuing a locked-out account would otherwise hand over a password that still
could not be used. It deliberately does **not** clear MFA: that would remove a
second factor as a side effect of a password reset, and `POST /auth/mfa/disable`
is the path for that, password-verified. None of these snapshots carries the
password, the hash or the TOTP secret — `_account_snapshot` omits all three by
design, and the audit assertions pin that.

Read the trail through `GET /admin/audit-logs` (admin-only, filterable by
`entity_type` / `action` / `performed_by` / date range).
`GET /admin/system/academic-structure` reads the same table scoped to the four
structural entity types.

One row above is marked unimplemented because the surface does not exist yet:
there is no admin account unlock route. See ADR-064.

Admin password reset **is** implemented, at `POST /admin/{users,students,professors}/{id}/reset-password`.
All three routes resolve to the same `AuthService.admin_reset_password`; the student and
professor routers look their roster row up to a `users.id` first (409 `*_account_unlinked`
when there is none), then call it. It clears `failed_login_attempts`/`is_locked`/`locked_at`
as well as the password, and records `performed_by` — but it does not touch MFA, which is
`disable_mfa`'s job and is password-verified.

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
| D18      | Session code derivation — HMAC-SHA256 over `session_id`, 8 base62 chars; QR payload is versioned (`v: 1`) but unsigned |
| D25      | Never security-disabled sessions                    |
| D26      | Liveness mandatory even for remote classes          |
| D27      | 5-step sequential scan flow                         |
| D28      | Face embedding encryption at rest                   |
| D29      | Embedding pull-on-login (version-gated)             |
| D30      | Offline verification uses cached embedding          |
| D31      | Liveness protocol (fixed sequence, EAR + PnP)       |
| D32      | Profile read-only (identity admin-managed)          |
| D39      | Backup encryption (AES-256-GCM)                     |
