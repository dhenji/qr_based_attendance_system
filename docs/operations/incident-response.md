# Incident Response Playbooks

> Response procedures for security and operational incidents. Each playbook covers
> detection, containment, investigation, remediation, and post-incident review.
> Complements [runbooks.md](runbooks.md) (operational) and [monitoring.md](monitoring.md) (detection).

---

## Table of Contents

1. [Spoof-Attempt Spike](#1-spoof-attempt-spike)
2. [Database Outage During Class Hours](#2-database-outage-during-class-hours)
3. [Sync Backlog Flood](#3-sync-backlog-flood)
4. [Backup-Restore Drill](#4-backup-restore-drill)

---

## 1. Spoof-Attempt Spike

**Trigger:** Monitoring detects elevated rejection rates for liveness (`liveness_failed`), face mismatch (`face_mismatch`), or duplicate scan attempts within a short window.

### Severity Assessment

| Indicator | Low | Medium | High |
|-----------|-----|--------|------|
| Rejection rate vs baseline | < 2x | 2–5x | > 5x |
| Affected sessions | 1 | 2–5 | > 5 or same student repeated |
| Geographic pattern | Scattered | Same course | Same classroom |
| Time pattern | Random | Class hours | Concentrated burst |

### Detection

```sql
-- Rejection spike query (last hour vs same hour last week)
SELECT
    DATE_TRUNC('hour', created_at) as hour,
    validation_status,
    COUNT(*) as cnt
FROM attendance_records
WHERE created_at >= NOW() - INTERVAL '1 hour'
GROUP BY hour, validation_status
ORDER BY hour DESC;
```

### Containment (Immediate)

1. **No system shutdown.** The system is designed to reject invalid scans (D25/D26).
2. If a specific session shows coordinated spoof attempts:
   - Close the session early (`POST /professor/sessions/{id}/close`)
   - Notify the professor via direct message
3. If a specific student is repeatedly rejected:
   - Flag for manual review in the liveness review queue (`/admin/liveness-review`)
   - Do NOT lock the account automatically (let admin investigate)

### Investigation

1. Query rejection patterns:
   ```sql
   SELECT
       student_id,
       session_id,
       rejection_reason,
       liveness_evidence->>'face_match_score' as score,
       created_at
   FROM attendance_records
   WHERE validation_status = 'rejected'
     AND created_at >= NOW() - INTERVAL '24 hours'
   ORDER BY created_at DESC;
   ```
2. Check for same device fingerprints or GPS coordinates across rejections.
3. Cross-reference with enrollment records — are rejected students actually enrolled?
4. Review face embedding version — stale embeddings cause false mismatches.

### Remediation

- **Buddy punching (student A scans for student B):** Evidence in liveness challenge failures (blink/turn not detected). Report to academic integrity office.
- **Photo/video replay:** Liveness challenge defeats static images. If liveness is bypassed, escalate to security review.
- **Face mismatch from stale embeddings:** Re-enroll student via admin face enrollment (runbook 4).
- **Legitimate false rejections:** Check FACE_MATCH_THRESHOLD (default 0.7). Consider adjusting if threshold is too aggressive for the student population.

### Post-Incident

- Document incident with timestamps, affected students, rejection patterns.
- If threshold adjustment needed: update `FACE_MATCH_THRESHOLD` env var and restart.
- If systematic spoof attempt: consider adding rate limiting per student per session.
  Note: D25 prohibits any "mark all present" override; D26 keeps liveness mandatory
  for remote sessions. Rate limiting must not weaken these invariants.

---

## 2. Database Outage During Class Hours

**Trigger:** API health check fails, or Supabase dashboard shows connection issues, during active class sessions (typically 7:00 AM – 6:00 PM).

### Severity: Critical

Active sessions are affected. Students cannot scan. Offline scans will queue and sync when DB recovers.

### Containment (Immediate — within 5 minutes)

1. **Verify outage scope:**
   ```bash
   curl -sf http://localhost:8000/health && echo "API: OK" || echo "API: DOWN"
   pg_isready -h <host> -p 5432 && echo "DB: OK" || echo "DB: DOWN"
   ```

2. **If API is up but DB is down** (partial outage):
   - The app should already have failed at startup (lifespan `SELECT 1`). If it's running, the DB was recently connected.
   - Check Supabase dashboard for connection pool status.

3. **If both API and DB are down:**
   - Check Fly.io status for the backend VM.
   - Check Supabase status page (status.supabase.com).

4. **Notify affected users:**
   - Send message to professors with active sessions: "Attendance system is temporarily unavailable. Students should continue class — offline scans will sync when the system recovers."
   - Post announcement on admin dashboard if possible.

### Investigation

1. Check Supabase dashboard → Logs → Postgres for connection满, deadlocks.
2. Check Fly.io logs for the API container.
3. Determine if it's a network issue, resource exhaustion, or Supabase-side problem.

### Remediation

- **Supabase outage:** Wait for Supabase recovery. No action needed — offline scans will sync.
- **Connection pool exhaustion:** Restart the API container (`fly scale count 1 --app attendance-system-api`).
- **Resource limits hit:** Check Supabase free tier limits (500MB DB, 2GB bandwidth).
- **Data corruption:** Follow migration rollback runbook (runbook 2) if caused by bad migration.

### Post-Outage Recovery

1. Verify API health returns 200.
2. Monitor sync backlog for offline scans queuing in (runbook 5 if stuck).
3. Check that active sessions can resume scanning.
4. Document root cause and duration.

### Prevention

- Monitor DB connection pool utilization (alert at 80%).
- Ensure Fly.io VM has sufficient resources.
- Consider Supabase Pro plan if outages become frequent.

---

## 3. Sync Backlog Flood

**Trigger:** `sync_queue` item count exceeds 100 pending items for more than 10 minutes, or sync worker reports errors.

### Severity: High

Students with offline scans cannot have their attendance confirmed. Risk of `session_expired` rejections when backlog clears (D16).

### Detection

```sql
SELECT
    status,
    COUNT(*),
    MIN(created_at) as oldest_item,
    MAX(created_at) as newest_item
FROM sync_queue
WHERE status IN ('pending', 'processing', 'failed')
GROUP BY status;
```

### Containment (Immediate)

1. **Check sync worker status:**
   ```bash
   # If using a background worker
   docker logs <sync-worker-container> --tail 50
   ```

2. **If worker is crashed/stuck:** Restart it.
   ```bash
   docker restart <sync-worker-container>
   ```

3. **If the server was recently down:** The backlog is expected — items will process as the server recovers.

### Investigation

1. **Why did the backlog build?**
   - Server was down → items queued while offline → server recovered but processing is slow
   - Too many concurrent offline scans → processing can't keep up
   - Sync worker bug → items stuck in `processing` state

2. **Check for stuck items:**
   ```sql
   SELECT id, status, retry_count, created_at,
          updated_at,
          NOW() - updated_at as stuck_duration
   FROM sync_queue
   WHERE status = 'processing'
     AND updated_at < NOW() - INTERVAL '5 minutes';
   ```

3. **Check for rejected items:**
   ```sql
   SELECT id, record_data->>'student_id' as student,
          record_data->>'session_id' as session,
          retry_count
   FROM sync_queue
   WHERE status = 'failed'
   ORDER BY created_at DESC;
   ```

### Remediation

- **Stuck processing items:** Reset to pending (runbook 5, step 3).
- **Failed items (max retries):** Log for manual review, then delete (runbook 5, step 4).
- **Too many concurrent syncs:** Throttle sync processing, or increase worker concurrency.
- **Session expired during sync:** Items with `scanned_at` past `expires_at` will be `rejected (session_expired)` — this is expected behavior (D16). Inform affected students.

### Post-Incident

- Monitor backlog until it reaches 0.
- Check that all synced attendance records appear correctly in `attendance_records`.
- If sync worker has a bug, file an issue and deploy a fix.
- Consider implementing sync rate limiting per student.

---

## 4. Backup-Restore Drill

**Trigger:** Scheduled quarterly drill, or after a security incident requiring data recovery.

### Purpose

Verify that backups are valid, restorable, and meet recovery time objectives (RTO).

### Preconditions

- Production database access (read-only is fine for drill)
- Staging database for restore testing
- `BACKUP_ENCRYPTION_KEY` accessible
- Backup storage accessible (local or S3)
- 30-minute maintenance window

### Drill Steps

#### Step 1: Verify Backup Freshness

```sql
SELECT filename, kind, size_bytes, sha256, status,
       started_at, finished_at,
       NOW() - finished_at as age
FROM backup_log
WHERE kind = 'full' AND status = 'success'
ORDER BY finished_at DESC
LIMIT 3;
```

**Expected:** Last full backup within 25 hours.

#### Step 2: Download Most Recent Backup

```bash
# Local
LATEST=$(ls -t ./backups/*.enc 2>/dev/null | head -1)
echo "Latest backup: $LATEST"

# S3
aws s3 ls s3://$BACKUP_S3_BUCKET/backups/ --recursive | sort | tail -5
```

#### Step 3: Verify Integrity

```bash
# Check sha256 sidecar
sha256sum -c ${LATEST%.enc}.sha256
# Expected: backup_*.sql.gz.enc: OK
```

#### Step 4: Decrypt

```bash
openssl enc -aes-256-gcm -d -salt -pbkdf2 \
    -in "$LATEST" \
    -out /tmp/drill_backup.sql.gz \
    -pass env:BACKUP_ENCRYPTION_KEY

echo "Decrypted successfully"
```

#### Step 5: Decompress

```bash
gunzip /tmp/drill_backup.sql.gz
echo "Decompressed: $(ls -lh /tmp/drill_backup.sql)"
```

#### Step 6: Restore to Staging

```bash
pg_restore --verbose --clean --no-acl --no-owner \
    -h <staging_host> -p 5432 -U postgres -d attendance_sys_drill \
    /tmp/drill_backup.sql
```

**Expected:** Clean restore with no errors.

#### Step 7: Verify Staging Data

```sql
-- Row counts
SELECT schemaname, relname, n_live_tup
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY n_live_tup DESC;

-- Critical data integrity
SELECT
    (SELECT COUNT(*) FROM users) as users,
    (SELECT COUNT(*) FROM students) as students,
    (SELECT COUNT(*) FROM sessions) as sessions,
    (SELECT COUNT(*) FROM attendance_records) as attendance,
    (SELECT COUNT(*) FROM programs) as programs,
    (SELECT COUNT(*) FROM backup_log) as backups;
```

#### Step 8: Smoke Test

- Login to staging with a test account
- Verify recent attendance records are visible
- Check that API health returns OK on staging

#### Step 9: Cleanup

```bash
# Drop staging database
dropdb <staging_host> attendance_sys_drill

# Clean up temp files
rm /tmp/drill_backup.sql
```

### Drill Checklist

- [ ] Backup freshness verified (< 25 hours)
- [ ] Integrity check passed (sha256)
- [ ] Decryption succeeded
- [ ] Decompression succeeded
- [ ] Restore to staging completed without errors
- [ ] Row counts match production expectations
- [ ] Smoke test passed (login, data visible)
- [ ] Staging database cleaned up
- [ ] Drill logged in `backup_log` with kind `analytics` (or separate log)

### Recovery Time Objective (RTO)

| DB Size | Expected Restore Time | Acceptable |
|---------|----------------------|------------|
| < 100 MB | < 5 minutes | Yes |
| 100–500 MB | 5–15 minutes | Yes |
| > 500 MB | 15–30 minutes | Investigate |

### Post-Drill

- Document any issues found during the drill.
- If restore failed: investigate and fix before next drill.
- Update this playbook if procedures have changed.
- Schedule next drill (quarterly).

---

## Escalation Matrix

| Incident | First Responder | Escalation | External |
|----------|----------------|------------|----------|
| Spoof spike | Admin | Project lead | Academic integrity office |
| DB outage | DevOps | Supabase support | Supabase status page |
| Sync flood | Developer | DevOps | — |
| Backup failure | DevOps | Project lead | — |
| Data breach | Project lead | Security advisor | Legal, affected users |

---

## Communication Templates

### Active Incident (Internal)

```
[INCIDENT] {severity} - {title}
Status: Investigating / Contained / Resolved
Impact: {description of affected users/features}
Timeline: Started {time}, detected {time}
Next update: {time}
```

### User-Facing (If Needed)

```
The attendance system is temporarily experiencing issues.
Students with pending offline scans: your records are safe and
will sync when the system recovers. No action needed.
Estimated resolution: {timeframe}.
```

### Post-Incident

```
[POST-INCIDENT] {title}
Date: {date}
Duration: {start} – {end} ({total})
Root cause: {description}
Impact: {affected users, data loss if any}
Resolution: {what was done}
Prevention: {what changes were made}
```
