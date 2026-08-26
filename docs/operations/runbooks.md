# Operations Runbooks

> Each runbook follows the format: **Preconditions** → **Steps** → **Verification**.

---

## Runbook 1: Restore from Backup

**Purpose:** Recover the database from an encrypted backup file. See [backup-strategy.md](../deployment/backup-strategy.md) §5 for the full restore procedure.

### Preconditions

- Access to the backup storage (local volume or S3 bucket)
- `BACKUP_ENCRYPTION_KEY` and `BACKUP_ENCRYPTION_KEY_VERSION` from `.env`
- `openssl` installed (ships with most systems)
- Target Postgres instance running and reachable
- Maintenance window active (no active sessions expected)

### Steps

1. **List available backups:**

   ```bash
   # Local
   ls -lh ./backups/

   # S3
   aws s3 ls s3://$BACKUP_S3_BUCKET/backups/ --recursive
   ```

2. **Download the backup file** (if S3):

   ```bash
   aws s3 cp s3://$BACKUP_S3_BUCKET/backups/<filename>.enc ./restore/
   ```

3. **Decrypt the backup:**

   ```bash
   openssl enc -aes-256-gcm -d -salt -pbkdf2 \
       -in ./restore/<filename>.enc \
       -out ./restore/<filename>.sql.gz \
       -pass env:BACKUP_ENCRYPTION_KEY
   ```

4. **Verify integrity** (if sha256 sidecar exists):

   ```bash
   sha256sum -c ./restore/<filename>.sha256
   ```

5. **Decompress:**

   ```bash
   gunzip ./restore/<filename>.sql.gz
   ```

6. **Restore to Postgres:**

   ```bash
   pg_restore --verbose --clean --no-acl --no-owner \
       -h localhost -p 5432 -U postgres -d attendance_sys \
       ./restore/<filename>.sql
   ```

7. **Verify row counts:**

   ```bash
   psql -h localhost -U postgres -d attendance_sys -c "
       SELECT schemaname, relname, n_live_tup
       FROM pg_stat_user_tables
       ORDER BY n_live_tup DESC;
   "
   ```

### Verification

- [ ] All expected tables present (`programs`, `year_levels`, `courses`, `students`, etc.)
- [ ] Row counts match pre-disaster expectations
- [ ] Application starts and `/health` returns `{"status":"ok"}`
- [ ] Spot-check: login works, recent attendance records visible

---

## Runbook 2: Migration Rollback

**Purpose:** Revert a failed or incorrect Alembic migration.

### Preconditions

- Access to the `backend/` directory
- Database backup taken before the migration (mandatory — see migration-strategy.md)
- Alembic history reviewed to identify the target revision

### Steps

1. **Check current migration state:**

   ```bash
   cd backend
   alembic current
   alembic history --verbose
   ```

2. **Roll back one step:**

   ```bash
   cd backend
   alembic downgrade -1
   ```

3. **Roll back to a specific revision:**

   ```bash
   cd backend
   alembic downgrade <revision_id>
   ```

4. **If downgrade fails** (data migration not reversible):

   ```bash
   # Restore from backup instead
   pg_restore --verbose --clean --no-acl --no-owner \
       -h localhost -p 5432 -U postgres -d attendance_sys \
       ./backups/pre_migration.dump
   ```

5. **Re-apply corrected migration:**

   ```bash
   cd backend
   # Fix the migration file, then:
   alembic upgrade head
   ```

### Verification

- [ ] `alembic current` shows the expected revision
- [ ] Affected tables/columns match the pre-migration state
- [ ] Application starts without errors
- [ ] Smoke test: create/read operations on affected features

---

## Runbook 3: Unlock Locked Accounts

**Purpose:** Unlock a user account that has been locked due to failed login attempts.

### Preconditions

- Database access (direct SQL or admin API)
- User identification (email or user ID)

### Steps

1. **Identify the locked user:**

   ```sql
   SELECT id, email, is_locked, locked_at, failed_login_attempts
   FROM users
   WHERE email = 'user@example.com';
   ```

2. **Unlock via SQL:**

   ```sql
   UPDATE users
   SET is_locked = false,
       locked_at = NULL,
       failed_login_attempts = 0
   WHERE email = 'user@example.com';
   ```

3. **Or unlock via admin API** (when implemented):

   ```bash
   curl -X PATCH http://localhost:8000/admin/users/{user_id}/unlock \
       -H "Authorization: Bearer $ADMIN_TOKEN"
   ```

4. **Notify the user** that their account has been unlocked.

### Verification

- [ ] `is_locked` is `false` for the user
- [ ] User can log in successfully
- [ ] `failed_login_attempts` is reset to `0`

---

## Runbook 4: Re-enroll Failed Faces

**Purpose:** Re-capture face embeddings for a student whose enrollment failed or whose embeddings are corrupted.

### Preconditions

- Admin access to the face enrollment section
- Student physically present (for 3-photo capture)
- Camera functional on admin device
- Student not archived (`is_active = true`)

### Steps

1. **Check current enrollment status:**

   ```sql
   SELECT s.id, s.student_id, s.first_name, s.last_name,
          s.face_embedding IS NULL as no_embedding,
          s.face_enrolled_at, s.face_embedding_version
   FROM students s
   WHERE s.student_id = '24-2111';
   ```

2. **Navigate to Face Enrollment** in the admin portal:
   - Route: `/admin/face-enrollment`
   - Search for the student by student number

3. **Capture 3 photos** (front, left, right):
   - Ensure good lighting, single face in frame
   - Quality gates auto-validate: brightness, face-size, single-face
   - System rejects blurry or multiple-face captures

4. **Server generates embeddings:**
   - 128-d embedding per photo using face-api.js-compatible ResNet
   - Stored as encrypted JSON blob in `students.face_embedding` (BYTEA)
   - `face_embedding_version` incremented
   - `face_enrolled_at` updated

5. **If re-enrollment is for a different student** (replace old embeddings):
   - New embeddings completely supersede old vectors
   - Version bump triggers re-download on next student login

### Verification

- [ ] `face_embedding` is NOT NULL and contains valid JSON
- [ ] `face_enrolled_at` reflects the new capture time
- [ ] `face_embedding_version` is incremented
- [ ] Student can complete the 5-step scan flow (face check passes)
- [ ] Student's device downloads new embedding on next login (version-gated pull)

---

## Runbook 5: Clear Stuck Sync Queue

**Purpose:** Resolve items stuck in `pending` or `processing` state in the `sync_queue` table.

### Preconditions

- Database access
- Understanding of why the sync failed (check application logs)
- Network connectivity to the server confirmed (if the issue was transient)

### Steps

1. **Inspect stuck items:**

   ```sql
   SELECT id, status, retry_count, created_at, updated_at,
          record_data->>'student_id' as student_id
   FROM sync_queue
   WHERE status IN ('pending', 'processing')
   ORDER BY created_at ASC;
   ```

2. **Check for truly stuck items** (processing for > 5 minutes):

   ```sql
   SELECT id, status, retry_count, created_at, updated_at
   FROM sync_queue
   WHERE status = 'processing'
     AND updated_at < NOW() - INTERVAL '5 minutes';
   ```

3. **Reset stuck items to pending** (for retry):

   ```sql
   UPDATE sync_queue
   SET status = 'pending', retry_count = 0
   WHERE status = 'processing'
     AND updated_at < NOW() - INTERVAL '5 minutes';
   ```

4. **Delete permanently failed items** (exceeded max retries):

   ```sql
   -- Check first
   SELECT id, retry_count, record_data
   FROM sync_queue
   WHERE status = 'failed' AND retry_count >= 5;

   -- Delete if appropriate
   DELETE FROM sync_queue
   WHERE status = 'failed' AND retry_count >= 5;
   ```

5. **If the entire queue is stuck** (server was down):

   ```sql
   -- Force-reset all pending/processing
   UPDATE sync_queue
   SET status = 'pending', retry_count = 0
   WHERE status IN ('pending', 'processing');
   ```

6. **Trigger a manual sync processing cycle** (if background worker is running):
   - Restart the sync worker, or
   - Call the sync processing endpoint if available

### Verification

- [ ] No items stuck in `processing` for > 5 minutes
- [ ] Sync worker processes items successfully (check logs)
- [ ] Attendance records created from synced scans appear in `attendance_records`
- [ ] Student devices show updated sync status (pending count decreases)

---

## Runbook 6: Rotate Backup Encryption Key

**Purpose:** Rotate the AES-256-GCM encryption key used for backup files without losing access to old backups.

### Preconditions

- Current `BACKUP_ENCRYPTION_KEY` and `BACKUP_ENCRYPTION_KEY_VERSION` from `.env`
- Access to backup storage
- `openssl` installed (ships with most systems)
- Downtime window for re-encrypting old backups (optional)

### Steps

1. **Generate a new key:**

   ```bash
   openssl rand -base64 32
   ```

2. **Update `.env` with the new key:**

   ```bash
   BACKUP_ENCRYPTION_KEY=<new_key_base64>
   BACKUP_ENCRYPTION_KEY_VERSION=<current_version + 1>
   ```

3. **Restart the application** to pick up the new env vars.

4. **Verify the new key works** by creating a test backup:

   ```bash
   # Trigger a backup via API or manually
   curl -X POST http://localhost:8000/admin/backups \
       -H "Authorization: Bearer $ADMIN_TOKEN"
   ```

5. **Re-encrypt old backups** (optional, to retire the old key):

   ```bash
   # For each old backup file
   OLD_KEY="old_key_base64"
   NEW_KEY="new_key_base64"

   # Decrypt with old key
   openssl enc -aes-256-gcm -d -salt -pbkdf2 \
       -in ./backups/old_backup.enc \
       -out /tmp/backup.sql.gz \
       -pass pass:"$OLD_KEY"

   # Re-encrypt with new key
   openssl enc -aes-256-gcm -salt -pbkdf2 \
       -in /tmp/backup.sql.gz \
       -out ./backups/old_backup_v2.enc \
       -pass pass:"$NEW_KEY"

   # Clean up
   rm /tmp/backup.sql.gz
   ```

6. **Update backup_log** if re-encrypting (optional):

   ```sql
   UPDATE backup_log
   SET encryption_key_version = <new_version>,
       filename = REPLACE(filename, '.enc', '_v2.enc')
   WHERE encryption_key_version = <old_version>;
   ```

7. **Test restore** with the new key on a staging database.

### Verification

- [ ] New backup created successfully with new key version
- [ ] New backup can be decrypted with the new key (test: `openssl enc -aes-256-gcm -d -salt -pbkdf2 -in <file>.enc -out /dev/null -pass pass:"$NEW_KEY"`)
- [ ] Old backups (if not re-encrypted) still decrypt with the old key
- [ ] `backup_log` reflects correct `encryption_key_version` for new entries
- [ ] Restore test on staging succeeds
