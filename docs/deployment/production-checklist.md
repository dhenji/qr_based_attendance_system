# Production Checklist

> Pre-launch checklist for deploying the QR Attendance System to production.
> Every item must be verified before go-live. References:
> [Deployment Workflow](deployment-workflow.md), [Backup Strategy](backup-strategy.md),
> [Security Model](../architecture/security-model.md), [Database ER](../design/database-er.md),
> [Migration Strategy](../architecture/migration-strategy.md).

---

## Table of Contents

1. [Secrets & Environment Variables](#1-secrets--environment-variables)
2. [CORS Configuration](#2-cors-configuration)
3. [Authentication & Security](#3-authentication--security)
4. [Database](#4-database)
5. [Object Storage](#5-object-storage)
6. [Backup Pipeline](#6-backup-pipeline)
7. [Email / SMTP](#7-email--smtp)
8. [Frontend Configuration](#8-frontend-configuration)
9. [First Admin Account](#9-first-admin-account)
10. [Post-Deploy Verification](#10-post-deploy-verification)

---

## 1. Secrets & Environment Variables

### Backend (Fly.io secrets or `.env`)

| Variable                         | Required | Value / Source             | Notes                                                         |
| -------------------------------- | -------- | -------------------------- | ------------------------------------------------------------- |
| `DATABASE_URL`                   | Yes      | Supabase connection string | `postgresql://postgres:PASS@db.REF.supabase.co:5432/postgres` |
| `DEBUG`                          | Yes      | `false`                    | Enables JWT_SECRET validation                                 |
| `JWT_SECRET`                     | Yes      | `openssl rand -base64 32`  | Required when DEBUG=false                                     |
| `JWT_ALGORITHM`                  | Yes      | `HS256`                    | Default                                                       |
| `ACCESS_TOKEN_EXPIRE_MINUTES`    | Yes      | `15`                       | Or per policy                                                 |
| `REFRESH_TOKEN_EXPIRE_DAYS`      | Yes      | `7`                        | Or per policy                                                 |
| `HMAC_SECRET_KEY`                | Yes      | `openssl rand -base64 32`  | For session code signing                                      |
| `CORS_ORIGINS`                   | Yes      | Vercel frontend URL        | `https://attendance-system.vercel.app`                                 |
| `TRUSTED_PROXY_CIDRS`          | If behind proxy | LB/ingress CIDRs, comma-separated | Empty = trust nothing (dev default). Behind an ingress with this empty, every IP-keyed rate limit is shared deployment-wide — see §3 |
| `BACKUP_ENCRYPTION_KEY`          | Yes      | `openssl rand -base64 32`  | AES-256-GCM key                                               |
| `BACKUP_ENCRYPTION_KEY_VERSION`  | Yes      | `1`                        | Increment on key rotation                                     |
| `BACKUP_STORAGE_TYPE`            | Yes      | `local` or `s3`            | `local` for dev, `s3` for prod                                |
| `BACKUP_LOCAL_DIR`               | If local | `./backups`                | Ignored if storage_type=s3                                    |
| `BACKUP_S3_BUCKET`               | If s3    | S3 bucket name             |                                                               |
| `BACKUP_S3_ENDPOINT`             | If s3    | S3 endpoint URL            |                                                               |
| `BACKUP_S3_PREFIX`               | If s3    | `backups/`                 |                                                               |
| `BACKUP_RETENTION_DAILY`         | Yes      | `30`                       | Default                                                       |
| `BACKUP_RETENTION_MONTHLY`       | Yes      | `12`                       | Default                                                       |
| `FACE_MATCH_THRESHOLD`           | Yes      | `0.7`                      | Cosine similarity threshold                                   |
| `FACE_REVIEW_BAND_LOW`           | Yes      | `0.65`                     | Score band for manual review                                  |
| `FACE_EMBEDDING_VERSION`         | Yes      | `1`                        | Increment on model change                                     |
| `DEFAULT_PRESENT_WINDOW_MINUTES` | Yes      | `5`                        | Course default                                                |
| `DEFAULT_LATE_WINDOW_MINUTES`    | Yes      | `10`                       | Course default                                                |
| `RISK_ABSENCE_RATE_HIGH`         | Yes      | `0.30`                     | D35                                                           |
| `RISK_ABSENCE_RATE_MEDIUM`       | Yes      | `0.15`                     | D35                                                           |
| `RISK_STREAK_GAPS_HIGH`          | Yes      | `3`                        | D35                                                           |
| `RISK_SYNC_LAG_HIGH`             | Yes      | `5`                        | D35                                                           |
| `RISK_TREND_NEGATIVE`            | Yes      | `-0.05`                    | D35                                                           |
| `RISK_BATCH_CRON`                | Yes      | `0 2 * * *`                | Nightly 2 AM                                                  |
| `BACKUP_CRON`                    | Yes      | `0 3 * * *`                | Nightly 3 AM. An hour after `RISK_BATCH_CRON`, so the two heavy jobs never overlap |
| `SCHEDULER_ENABLED`              | No       | `true`                     | Set `false` to run the API with no cron jobs at all            |
| `SCHEDULER_TIMEZONE`             | No       | `UTC`                      | zoneinfo name. An unknown one logs a warning and falls back to UTC |
| `SCHEDULER_MISFIRE_GRACE_SECONDS`| No       | `300`                      | How late a missed run may still start                          |
| `ATTACHMENTS_STORAGE_TYPE`       | Yes      | `local` or `s3`            | Same as backup storage                                        |
| `ATTACHMENTS_MAX_BYTES`          | Yes      | `5242880`                  | 5 MiB                                                         |

### Frontend (Vercel env vars)

| Variable         | Required | Value          | Notes                                   |
| ---------------- | -------- | -------------- | --------------------------------------- |
| `PUBLIC_API_URL` | Yes      | Fly.io API URL | `https://attendance-system-api.fly.dev` |

### Verification

```bash
# Backend: check all env vars are set (no empty required vars)
fly secrets list --app attendance-system-api

# Frontend: check PUBLIC_API_URL is correct
# Vercel dashboard → Settings → Environment Variables
```

---

## 2. CORS Configuration

| Item                | Value                                             | Notes                                    |
| ------------------- | ------------------------------------------------- | ---------------------------------------- |
| `CORS_ORIGINS`      | `https://attendance-system.vercel.app`                     | Must match Vercel deployment URL exactly |
| `allow_credentials` | `true`                                            | Required for JWT in cookies              |
| `allow_methods`     | `["GET","POST","PUT","PATCH","DELETE","OPTIONS"]` |                                          |
| `allow_headers`     | `["*"]`                                           | Or restrict to known headers             |

### Verification

```bash
# From browser dev tools, check for CORS errors on API calls
# Or test with curl:
curl -I -X OPTIONS https://attendance-system-api.fly.dev/health \
    -H "Origin: https://attendance-system.vercel.app" \
    -H "Access-Control-Request-Method: GET"
# Expected: Access-Control-Allow-Origin header present
```

---

## 3. Authentication & Security

### JWT Configuration

| Item                          | Check                                                     |
| ----------------------------- | --------------------------------------------------------- |
| `JWT_SECRET`                  | Set and non-empty (validated at startup when DEBUG=false) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Set to reasonable value (15 min)                        |
| `REFRESH_TOKEN_EXPIRE_DAYS`   | Set to reasonable value (7–30 days)                       |

### HMAC Session Codes

| Item              | Check                                             |
| ----------------- | ------------------------------------------------- |
| `HMAC_SECRET_KEY` | Set, random, never committed to git               |
| Session codes     | Verify a test session generates a valid HMAC code |

### Account Security

| Item                 | Check                                         |
| -------------------- | --------------------------------------------- |
| Failed login lockout | Verify account locks after N failed attempts  |
| MFA                  | TOTP setup works for admin/professor accounts |
| Password policy      | Enforced minimum length/complexity            |
| OTP expiry           | OTP codes expire after configured duration    |

### Bot Protection — Turnstile (Optional)

Turnstile is **key-gated** (ADR-053): while `TURNSTILE_SECRET_KEY` is empty the
server-side check is a pass-through no-op, so the captcha is turned on and off
purely via env. When enabled it gates `POST /auth/login` and
`POST /auth/forgot-password` (step 1) — registration/claim is **not** gated.
When disabled, rate limiting and account lockout (D25) are the bot protection.

| Variable                    | Where    | Value                      |
| --------------------------- | -------- | -------------------------- |
| `PUBLIC_TURNSTILE_SITE_KEY` | Frontend | Cloudflare widget site key |
| `TURNSTILE_SECRET_KEY`      | Backend  | Cloudflare widget secret   |

> **Set both keys or neither.** The site key alone is safe — the widget renders
> and the backend skips verification. The secret alone is **not**: the widget
> stays hidden, no token is ever sent, and every login / forgot-password step 1
> returns `400 invalid_captcha`.

#### How to Enable

1. **Create the widget** — Cloudflare dashboard → Turnstile → *Add site*, and
   list every hostname the frontend is served from (e.g.
   `attendance-system.vercel.app`); a widget only accepts challenges from its
   listed hostnames.
2. **Set the frontend site key** — `PUBLIC_TURNSTILE_SITE_KEY` in the Vercel
   project env. `PUBLIC_*` vars are inlined at build time, so **redeploy the
   frontend** afterwards; an existing deployment will not pick it up.
3. **Set the backend secret** — `TURNSTILE_SECRET_KEY` in the backend env
   (`fly secrets set TURNSTILE_SECRET_KEY="YOUR_TURNSTILE_SECRET"`, which
   restarts the API).
4. **Verify** — using the commands below, on the deployed frontend.

Steps 2 → 3 is the safe order: the widget can ship before enforcement, not the
other way around.

#### Verification

```bash
# With TURNSTILE_SECRET_KEY set, a tokenless login must be rejected:
curl -i -X POST https://attendance-system-api.fly.dev/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@example.com","password":"whatever"}'
# Expected: 400 invalid_captcha
# Anything else means TURNSTILE_SECRET_KEY is still empty (captcha not enabled).

# Then load https://attendance-system.vercel.app/auth/login — the Turnstile
# widget must render, and login must succeed once it is solved.
```

Cloudflare's dummy always-pass pair — site key `1x00000000000000000000AA`,
secret `1x0000000000000000000000000000000AA` — exercises the wiring without a
real challenge; swap in the real pair before go-live.

#### Rollback

Unset `TURNSTILE_SECRET_KEY` (backend) and `PUBLIC_TURNSTILE_SITE_KEY`
(frontend), then restart/redeploy: the API reverts to pass-through and the
widget disappears. Rate limiting and account lockout (D25) remain in force.

### Reverse Proxy / Client IP

| Item                  | Check                                                                                              |
| --------------------- | -------------------------------------------------------------------------------------------------- |
| `TRUSTED_PROXY_CIDRS` | Set to the ingress/LB CIDRs when behind a proxy; empty otherwise                                   |
| Rate-limit keying     | IP-keyed buckets (`/auth/login*`, scan, risk-refresh) resolve per client, not per proxy            |

All rate limits and Turnstile `remoteip` resolve through `client_ip()`: the direct
peer by default, or the leftmost `X-Forwarded-For` entry **only** when the peer
itself is inside `TRUSTED_PROXY_CIDRS`. An untrusted peer's header is always
ignored, so a client cannot pick its own bucket. With the setting empty behind a
balancer, every IP-keyed bucket collapses onto the balancer's address — 20
logins/min and 15 OTP failures/5 min **deployment-wide**. The per-email caps
(`423`) stay correct regardless of proxying.

### Face Embedding Security

| Item                   | Check                                                        |
| ---------------------- | ------------------------------------------------------------ |
| `FACE_MATCH_THRESHOLD` | Set to `0.7` (default)                                       |
| Embedding encryption   | Verify `face_embedding` column stores encrypted data (BYTEA) |
| Version gating         | Student device downloads embedding only when version changes |

### Verification

```bash
# Test JWT validation
curl http://localhost:8000/health  # Should work without auth

# Test invalid token rejection
curl -H "Authorization: Bearer invalid_token" \
    http://localhost:8000/admin/students
# Expected: 401 Unauthorized
```

---

## 4. Database

### Schema Verification

```bash
# Connect to production DB and verify all tables exist
psql "$DATABASE_URL" -c "\dt"

# Expected tables:
# users, otp_codes, students, professors, courses, course_offerings,
# programs, year_levels, course_professors, enrollments, sessions,
# attendance_records, excuse_requests, student_risk_scores,
# backup_log, sync_queue
```

### Migration Status

```bash
cd backend
DATABASE_URL="$DATABASE_URL" alembic current
# Should show the latest migration revision
```

### Indexes

```sql
-- Verify critical indexes exist
SELECT indexname, tablename
FROM pg_indexes
WHERE schemaname = 'public'
  AND indexname LIKE 'ix_%'
ORDER BY tablename, indexname;
```

### Constraints

```sql
-- Verify CHECK constraints
SELECT conname, contype, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid IN (
    SELECT oid FROM pg_class WHERE relname IN ('sessions', 'attendance_records')
)
AND contype = 'c';
```

---

## 5. Object Storage

### Backup Storage

| Item                  | Check                                          |
| --------------------- | ---------------------------------------------- |
| `BACKUP_STORAGE_TYPE` | Set to `s3` for production                     |
| `BACKUP_S3_BUCKET`    | Bucket exists and is accessible                |
| `BACKUP_S3_ENDPOINT`  | Correct S3-compatible endpoint                 |
| `BACKUP_S3_PREFIX`    | Set (e.g., `backups/`)                         |
| Bucket permissions    | Write access from API, read access for restore |

### Attachment Storage

| Item                       | Check                                     |
| -------------------------- | ----------------------------------------- |
| `ATTACHMENTS_STORAGE_TYPE` | Set to same as backup storage             |
| Presigned URL generation   | Test uploading an excuse attachment       |
| Max file size              | `ATTACHMENTS_MAX_BYTES` set appropriately |

### Verification

```bash
# Test S3 write
aws s3 ls s3://$BACKUP_S3_BUCKET/ --recursive | head -5

# Test presigned URL (after API is running)
curl -X POST http://localhost:8000/admin/face-enrollment/test-student \
    -F "photo=@test.jpg" \
    -H "Authorization: Bearer $ADMIN_TOKEN"
```

---

## 6. Backup Pipeline

### Pre-Launch Backup Test

```bash
# Trigger a backup via API
curl -X POST http://localhost:8000/admin/backups \
    -H "Authorization: Bearer $ADMIN_TOKEN"

# Verify in backup_log
psql "$DATABASE_URL" -c \
    "SELECT * FROM backup_log ORDER BY id DESC LIMIT 3;"
```

### Cron Schedule

| Item                    | Check                                                   |
| ----------------------- | ------------------------------------------------------- |
| Backup cron configured  | `BACKUP_CRON="0 3 * * *"` (an hour after the 02:00 risk batch) |
| Cron owner              | Crons run **in the API process**. `SCHEDULER_ENABLED=false` hands them to an external scheduler instead |
| Retention pruning       | Runs after backup (30 daily, 12 monthly)                |
| Encryption key rotation | Documented procedure in runbook 6                       |
| `pg_dump` present       | The image needs `postgresql-client`, or the nightly backup fails with `backup_failed` |

> **Open defect:** the sample production `Dockerfile` in
> `deployment-workflow.md` installs no system packages, so it has neither
> `postgresql-client` nor `openssl`. On that image the nightly backup cannot
> succeed. Fix belongs with the image, not with the scheduler.

### Verification

```bash
# Check backup_log for recent completed backup
psql "$DATABASE_URL" -c \
    "SELECT filename, status, size_bytes, started_at, finished_at
     FROM backup_log WHERE kind='full' AND status='completed'
     ORDER BY finished_at DESC LIMIT 1;"
```

---

## 7. Email / SMTP

### Required For

- OTP codes (claim registration, password reset)
- Excuse notifications (request submitted, approved, rejected, bulk)

### Configuration

| Variable              | Check                                                                                                              |
| --------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `SMTP_HOST`           | Relay hostname. **Leave empty to disable email entirely** — messages are logged instead of sent, and no endpoint fails |
| `SMTP_PORT`           | `587` (STARTTLS) or `465` (implicit SSL)                                                                            |
| `SMTP_USER`           | Set, unless the relay takes no credentials                                                                           |
| `SMTP_PASSWORD`       | Set (not in git)                                                                                                     |
| `SMTP_FROM`           | `noreply@yourdomain.com` or similar. Falls back to `SMTP_USER`, then to `noreply@localhost`                          |
| `SMTP_START_TLS`      | `true` on port 587. Ignored when `SMTP_USE_SSL=true` — set it to `false` there or the handshake is attempted twice |
| `SMTP_USE_SSL`        | `true` for port 465 only                                                                                             |
| `SMTP_TIMEOUT_SECONDS`| `10` is fine for most relays                                                                                         |

Delivery is best-effort by design: `shared/email.py` logs and returns on any
SMTP error rather than raising, and notifications are sent off the request
thread, so a dead relay costs a log line and never a 5xx. A relay that silently
rejects everything looks exactly like a working one, so verify rather than
assume.

### Verification

```bash
# Test OTP email delivery
# (Register a test user and verify OTP arrives)
```

```bash
# Confirm a notification was handed to a relay: with SMTP_HOST set, submit an
# excuse request and look for "Email sent to=" in the API logs.
docker compose -f docker-compose.dev.yml logs api | grep "Email sent to="
```

---

## 8. Frontend Configuration

### Vercel Environment

| Item                        | Check                                      |
| --------------------------- | ------------------------------------------ |
| `PUBLIC_API_URL`            | Points to Fly.io API URL                   |
| `PUBLIC_TURNSTILE_SITE_KEY` | Site key when the captcha is enabled (§3)  |
| Framework preset            | SvelteKit (auto-detected)                  |
| Build command               | Default (`npm run build`)                  |
| Node version                | Matches `engines` in package.json (if set) |

### Type Checking

```bash
cd frontend
npm run check
# Must pass with zero errors
```

### PWA (if enabled)

| Item                        | Check                                          |
| --------------------------- | ---------------------------------------------- |
| `vite-plugin-pwa` installed | `npm list vite-plugin-pwa`                     |
| `manifest.json` present     | In `static/`                                   |
| Service worker registered   | Check browser DevTools                         |
| Icons                       | 192x192 and 512x512 present in `static/icons/` |

### Verification

```bash
# Deploy and check
curl -sf https://attendance-system.vercel.app/ | head -20
# Should return HTML

# Check for CORS errors in browser console
# Check API calls work from frontend
```

---

## 9. First Admin Account

### Seeding the Initial Admin

```sql
-- Connect to production DB
psql "$DATABASE_URL"

-- Create admin user (password should be Argon2id-hashed)
INSERT INTO users (role, email, password_hash, is_active)
VALUES (
    'admin',
    'admin@yourdomain.com',
    '$argon2id$v=19$m=65536,t=3,p=4$<salt>$<hash>',  -- generate with argon2
    true
);

-- Or use the claim registration flow if implemented:
-- 1. Insert user with email only
-- 2. Trigger OTP
-- 3. Complete claim flow via API
```

### Verification

```bash
# Login as admin
curl -X POST http://localhost:8000/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@yourdomain.com","password":"your_password"}'
# Should return JWT tokens

# Access admin endpoint
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
    http://localhost:8000/admin/students
# Should return student list (empty initially)
```

---

## 10. Post-Deploy Verification

### Smoke Tests (All Must Pass)

| #   | Test           | Command                             | Expected                        |
| --- | -------------- | ----------------------------------- | ------------------------------- |
| 1   | API health     | `curl https://attendance-system-api.fly.dev/health`   | `{"status":"ok"}`               |
| 2   | Swagger docs   | Open `https://attendance-system-api.fly.dev/docs`     | Swagger UI loads                |
| 3   | Frontend loads | Open `https://attendance-system.vercel.app`  | Page renders                    |
| 4   | CORS           | Browser console on frontend         | No CORS errors                  |
| 5   | Admin login    | POST `/auth/login` with admin creds | JWT returned                    |
| 6   | Student list   | GET `/admin/students`               | 200 OK                          |
| 7   | Create student | POST `/admin/students`              | 201 Created                     |
| 8   | Create course template | POST `/admin/courses`       | 201 Created                     |
| 9   | Create offering       | POST `/admin/offerings`     | 201 Created                     |
| 10  | Open session          | POST `/professor/sessions`  | 201 + session code              |
| 11  | Student scan          | POST `/student/attendance/scan` | 200 + status                |
| 12  | Backup trigger        | POST `/admin/backups`       | 202 Accepted                    |
| 13  | Backup log            | Query `backup_log`          | New entry with `status=completed` |
| 14  | Flood gate live       | 21 rapid `POST /auth/login/verify` | Twenty `400`s, then `429` |
| 15  | Proxy header ignored  | Same burst with forged `X-Forwarded-For` from an untrusted network | Same `429` at the same count |

```bash
# 14 — the verify flood gate fires (garbage grants return 400 fast, but the
# dependency budget is still consumed, so the 21st request trips the gate):
for i in $(seq 1 21); do
  curl -s -o /dev/null -w "%{http_code} " -X POST \
    https://attendance-system-api.fly.dev/auth/login/verify \
    -H "Content-Type: application/json" \
    -d '{"otp_token":"x","code":"000000"}'
done; echo
# Expected: twenty 400s, then a 429

# 15 — a forged header from outside the trusted CIDRs must not dodge it:
for i in $(seq 1 21); do
  curl -s -o /dev/null -w "%{http_code} " -X POST \
    https://attendance-system-api.fly.dev/auth/login/verify \
    -H "Content-Type: application/json" \
    -H "X-Forwarded-For: 1.2.3.4" \
    -d '{"otp_token":"x","code":"000000"}'
done; echo
# Expected: identical — the 429 lands at the same count, keyed on your IP.
# (Run this from a network OUTSIDE TRUSTED_PROXY_CIDRS; from inside, the
# header is legitimately honoured.)
```

### Performance Baseline

```bash
# Check API response times
curl -w "@curl-timing.txt" -o /dev/null -s https://attendance-system-api.fly.dev/health

# curl-timing.txt format:
# time_total: %{time_total}s
# time_connect: %{time_connect}s
```

---

## Sign-Off

| Role           | Name | Date | Verified |
| -------------- | ---- | ---- | -------- |
| Lead Developer |      |      | [ ]      |
| DevOps         |      |      | [ ]      |
| Project Owner  |      |      | [ ]      |

---

## Related Documents

- [Deployment Workflow](deployment-workflow.md) — step-by-step deployment guide
- [Backup Strategy](backup-strategy.md) — backup pipeline details
- [Runbooks](../operations/runbooks.md) — operational procedures
- [Monitoring](../operations/monitoring.md) — post-deploy monitoring setup
- [Incident Response](../operations/incident-response.md) — incident playbooks
- [Security Model](../architecture/security-model.md) — threat mitigations
