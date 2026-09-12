# Backup Strategy

> **Decisions covered:** D39

## 1. Overview

Backups are **full database dumps of every table** — nothing excluded by default
(D39). The pipeline produces compressed, encrypted backups with full audit logging
and automated retention pruning.

Key properties:

- Format: `pg_dump` custom format (`-Fc`), gzip-compressed, AES-256-GCM encrypted.
- Storage: local volume (dev) / S3-compatible (prod) via `BACKUP_STORAGE_TYPE`.
- Retention: last **30 daily** + **12 monthly** backups.
- All backups logged in `backup_log` table.
- Encryption key managed via environment variable with key-version tracking.

---

## 2. Scope

### 2.1 Included Tables (Default)

**Every table** in the database is included:

| Schema     | Tables                                                    |
| ---------- | --------------------------------------------------------- |
| auth       | `users`, `otp_codes`                                      |
| student    | `students`                                                |
| course     | `courses`, `course_offerings`, `year_levels`, `programs`, `course_professors` |
| enrollment | `enrollments`                                             |
| session    | `sessions`                                                |
| attendance | `attendance_records`                                      |
| excuse     | `excuse_requests`                                         |
| analytics  | `student_risk_scores`                                     |
| sync       | `sync_queue`                                              |
| system     | `backup_log`                                              |

### 2.2 Optional Exclusion

An opt-in flag may skip the ephemeral `otp_codes` table (OTP codes are
short-lived and non-critical for restore). This is NOT the default — operators
must explicitly enable it:

```bash
BACKUP_EXCLUDE_OTP_CODES=true   # default: false (include everything)
```

---

## 3. Pipeline

### 3.1 Steps

```
1. pg_dump -Fc → gzip → AES-256-GCM encrypt
2. Upload to storage backend (local / S3)
3. Insert record into backup_log
4. Prune old backups per retention policy
```

### 3.2 Detailed Flow

```
Trigger (scheduled or manual)
    │
    ▼
┌──────────────────────────────────────────────────────┐
│ Step 1: Dump & Compress                               │
│                                                       │
│   pg_dump -Fc --no-owner --no-privileges             │
│     -d $DATABASE_URL                                 │
│     [--exclude-table-data=otp_codes]  (if opt-in)    │
│     | gzip > /tmp/backup_${TIMESTAMP}.sql.gz         │
│                                                       │
│   Output: backup_20260825_020000.sql.gz              │
└────────────────────┬─────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────┐
│ Step 2: Encrypt                                      │
│                                                       │
│   openssl enc -aes-256-gcm -salt -pbkdf2            │
│     -in  /tmp/backup_${TIMESTAMP}.sql.gz             │
│     -out /tmp/backup_${TIMESTAMP}.sql.gz.enc         │
│     -pass env:BACKUP_ENCRYPTION_KEY                  │
│                                                       │
│   Output: backup_20260825_020000.sql.gz.enc          │
└────────────────────┬─────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────┐
│ Step 3: Compute Integrity Hash                       │
│                                                       │
│   sha256sum /tmp/backup_${TIMESTAMP}.sql.gz.enc      │
│     > /tmp/backup_${TIMESTAMP}.sha256                │
│                                                       │
│   Sidecar file: backup_20260825_020000.sha256        │
└────────────────────┬─────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────┐
│ Step 4: Upload                                       │
│                                                       │
│   IF BACKUP_STORAGE_TYPE = 'local':                  │
│     cp .enc + .sha256 → $BACKUP_LOCAL_DIR/           │
│                                                       │
│   IF BACKUP_STORAGE_TYPE = 's3':                     │
│     aws s3 cp .enc s3://$BACKUP_S3_BUCKET/           │
│       $BACKUP_S3_PREFIX/${TIMESTAMP}/                │
│     aws s3 cp .sha256 s3://... (same prefix)         │
│                                                       │
│   Object key: ${BACKUP_S3_PREFIX}${TIMESTAMP}/       │
│     backup.sql.gz.enc                                │
│     backup.sha256                                    │
└────────────────────┬─────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────┐
│ Step 5: Audit Log                                    │
│                                                       │
│   INSERT INTO backup_log (                           │
│     filename, kind, size_bytes, sha256,              │
│     storage_backend, encryption_key_version,         │
│     started_at, finished_at, status                  │
│   ) VALUES (...)                                     │
│                                                       │
│   kind = 'full' (default) | 'analytics'              │
│   status = 'success' | 'failed'                      │
└────────────────────┬─────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────┐
│ Step 6: Retention Prune                              │
│                                                       │
│   Delete backups older than:                         │
│     - 30 days for daily backups                      │
│     - 12 months for monthly backups                  │
│                                                       │
│   Monthly backup = first backup of each month        │
│   (retained for 12 months regardless of daily count) │
│                                                       │
│   Prune logic:                                       │
│     1. Delete all daily backups > 30 days old        │
│     2. Keep first-of-month backups for 12 months     │
│     3. Delete monthly backups > 12 months old        │
│     4. NEVER delete if total remaining < 2           │
│                                                       │
│   Local: rm files                                    │
│   S3: aws s3 rm (with --recursive for prefix)        │
└──────────────────────────────────────────────────────┘
```

### 3.3 Environment Variables

All variables from **Section 8 of the plan** (DOCS_REFACTOR_PLAN.md):

```bash
# Storage
BACKUP_STORAGE_TYPE=local          # local | s3
BACKUP_LOCAL_DIR=./backups

# S3 (only if BACKUP_STORAGE_TYPE=s3)
BACKUP_S3_BUCKET=
BACKUP_S3_ENDPOINT=
BACKUP_S3_PREFIX=backups/

# Encryption
BACKUP_ENCRYPTION_KEY=             # openssl rand -base64 32
BACKUP_ENCRYPTION_KEY_VERSION=1

# Retention
BACKUP_RETENTION_DAILY=30
BACKUP_RETENTION_MONTHLY=12

# Optional exclusion
BACKUP_EXCLUDE_OTP_CODES=false     # set true to skip otp_codes table
```

---

## 4. Backup Log Schema

```sql
CREATE TABLE backup_log (
    id                   SERIAL PRIMARY KEY,
    filename             VARCHAR NOT NULL,
    kind                 VARCHAR NOT NULL CHECK (kind IN ('full', 'analytics')),
    size_bytes           BIGINT NOT NULL,
    sha256               VARCHAR NOT NULL,
    storage_backend      VARCHAR NOT NULL CHECK (storage_backend IN ('local', 's3')),
    encryption_key_version INT NOT NULL,
    started_at           TIMESTAMPTZ NOT NULL,
    finished_at          TIMESTAMPTZ NOT NULL,
    status               VARCHAR NOT NULL CHECK (status IN ('success', 'failed')),
    error                TEXT NULL
);
```

---

## 5. Restore Runbook

### 5.1 Prerequisites

- Access to the encryption key (`BACKUP_ENCRYPTION_KEY`).
- Access to the storage backend (local filesystem or S3 credentials).
- A running PostgreSQL instance (restore is **destructive** — use a fresh or
  staging database).
- `pg_restore` installed (same major version as target DB).

### 5.2 Restore Steps

```
1. DOWNLOAD backup from storage
   Local: copy from $BACKUP_LOCAL_DIR/
   S3: aws s3 cp s3://$BACKUP_S3_BUCKET/$BACKUP_S3_PREFIX/${TIMESTAMP}/backup.sql.gz.enc .

2. VERIFY integrity (optional but recommended)
   sha256sum -c backup.sha256
   Expected: backup.sql.gz.enc: OK

3. DECRYPT
   openssl enc -aes-256-gcm -d -salt -pbkdf2 \
     -in  backup.sql.gz.enc \
     -out backup.sql.gz \
     -pass env:BACKUP_ENCRYPTION_KEY

4. DECOMPRESS
   gunzip backup.sql.gz
   Output: backup.sql

5. RESTORE (staging-first rule)
   pg_restore -d $DATABASE_URL \
     --no-owner --no-privileges \
     --clean --if-exists \
     backup.sql

   WARNING: --clean drops objects before recreating. For production:
     - Restore to a STAGING database first
     - Verify data integrity
     - Then promote to production (swap connection strings or pg_dump/restore again)

6. VERIFY
   - Check row counts for critical tables
   - Run application health check
   - Verify no orphaned FKs:
     SELECT COUNT(*) FROM pg_constraint WHERE NOT convalidated;
```

### 5.3 Staging-First Rule

**Never restore directly to production.** The recommended flow:

```
Production DB ──backup──▶ Encrypted Backup
                              │
                              ▼
                     Staging DB (restore here)
                              │
                              ▼
                     Verify (row counts, app health, FK integrity)
                              │
                              ▼
                     If OK → promote to production
                     If NOT → investigate, do NOT promote
```

---

## 6. Analytics Export

A separate, lighter-weight export for non-disaster-recovery purposes:

```
POST /admin/analytics/export
Body: {
  "format": "csv" | "pdf",
  "filters": {
    "program_id": 1,
    "year_level": 2,
    "semester": "1st_sem",
    "course_ids": [7, 12],
    "date_from": "2026-01-01",
    "date_to": "2026-08-25"
  }
}
```

| Property  | Value                                                      |
| --------- | ---------------------------------------------------------- |
| Content   | Aggregated attendance data (no raw PII beyond student IDs) |
| Format    | CSV (tabular) or PDF (formatted report)                    |
| Storage   | Same backend as backups (`ATTACHMENTS_STORAGE_TYPE`)       |
| Logged    | Yes — `backup_log.kind = 'analytics'`                      |
| Retention | Same as backups (30D daily, 12M monthly)                   |

---

## 7. Security Considerations

| Concern        | Mitigation                                                                                                                                         |
| -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| Key compromise | `BACKUP_ENCRYPTION_KEY_VERSION` tracks key rotation; old backups remain decryptable with old keys if key is rotated. Store previous keys securely. |
| Key in env     | Key is loaded from environment variable, never hardcoded. In prod, use a secrets manager (Vault, AWS Secrets Manager, etc.).                       |
| Transport      | S3 transfers use HTTPS. Local files stay on encrypted volumes.                                                                                     |
| Access control | Backup files should have `600` permissions (owner-only). S3 bucket policy restricts to admin IAM roles.                                            |
| Integrity      | SHA-256 sidecar file verifies the encrypted blob hasn't been tampered with. Check on download before decrypt.                                      |

---

## 8. Monitoring

| Metric              | Alert Threshold                  | Action                          |
| ------------------- | -------------------------------- | ------------------------------- |
| Backup freshness    | No successful backup in 25 hours | Investigate cron job / pipeline |
| Backup size delta   | > 50% change from previous day   | Verify data or schema change    |
| Backup duration     | > 10 minutes for < 1 GB DB       | Investigate I/O or DB locks     |
| Prune failures      | Any delete error                 | Manual cleanup required         |
| Encryption failures | Any openssl error                | Key rotation may be needed      |

---

## 9. Cross-References

| Topic                 | Document                                         |
| --------------------- | ------------------------------------------------ |
| Database schema       | [migration-strategy.md](migration-strategy.md)   |
| Security model        | [security-model.md](security-model.md)           |
| Wireframes: backup UI | `docs/design/wireframes.md` (section 4.10)       |
| API: backup endpoints | [api-contracts.md](api-contracts.md)             |
| Environment variables | `backend/.env.example`                           |
| Deployment workflow   | [deployment-workflow.md](deployment-workflow.md) |
| Operations runbooks   | `docs/operations/runbooks.md`                    |
