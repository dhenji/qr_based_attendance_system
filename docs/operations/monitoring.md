# Monitoring & Observability

> Health endpoints, log taxonomy, and actionable metrics with thresholds.

---

## Health Endpoints

### `GET /health`

Returns basic liveness check:

```json
{ "status": "ok" }
```

- **200**: API is running and database connection succeeded (verified at startup via `SELECT 1`)
- **Unreachable** (no response — neither 500 nor 503): if the DB is down the lifespan
  fails and the process exits, so `/health` never answers. Use the container/health-probe
  status + DB connectivity checks below to detect this.

### Database connectivity

The app validates DB connection at startup (lifespan). If Postgres is unreachable, the container exits immediately.

Check from outside:

```bash
curl -f http://localhost:8000/health || echo "API is down"
```

Check Postgres directly:

```bash
pg_isready -h localhost -p 5432 -U postgres -d attendance_sys
```

---

## Log Taxonomy

### Application logs

| Level      | When                  | Example                                                             |
| ---------- | --------------------- | ------------------------------------------------------------------- |
| `INFO`     | Normal operations     | Server started, migration applied, backup completed                 |
| `WARNING`  | Recoverable issues    | Sync retry, rate-limit approached, account lockout triggered        |
| `ERROR`    | Failed operations     | Migration failure, backup encryption error, scan validation failure |
| `CRITICAL` | System-level failures | Database unreachable, backup key missing, JWT secret not set        |

### Structured logging (recommended)

Add structured JSON logging in production:

```python
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
```

### Key log sources

| Source          | Location                              | What to watch                                       |
| --------------- | ------------------------------------- | --------------------------------------------------- |
| FastAPI/Uvicorn | stdout                                | Request errors (5xx), startup failures              |
| Alembic         | stderr                                | Migration failures, connection errors               |
| PostgreSQL      | `/var/log/postgresql/` or Docker logs | Connection pool exhaustion, deadlocks, slow queries |
| Sync worker     | stdout                                | Stuck items, retry storms                           |
| Risk batch      | stdout                                | Batch duration, skipped enrollments                 |
| Backup pipeline | stdout/`backup_log` table             | Encryption failures, upload errors                  |

---

## Metrics & Thresholds

### 1. Scan Success Rate

**Definition:** Percentage of attendance scans that result in `present` or `late` (not `rejected`).

```sql
SELECT
    DATE(created_at) as day,
    COUNT(*) FILTER (WHERE validation_status IN ('present', 'late')) * 100.0
        / NULLIF(COUNT(*), 0) as scan_success_pct
FROM attendance_records
WHERE created_at >= NOW() - INTERVAL '7 days'
GROUP BY day ORDER BY day;
```

| Threshold | Status   | Action                                                                    |
| --------- | -------- | ------------------------------------------------------------------------- |
| ≥ 95%     | Healthy  | —                                                                         |
| 85–94%    | Warning  | Check for common rejection reasons                                        |
| < 85%     | Critical | Investigate: geofence too tight? liveness failures? sync backlog?        |

### 2. Sync Backlog Depth

**Definition:** Number of items in `sync_queue` with status `pending` or `processing`.

```sql
SELECT status, COUNT(*)
FROM sync_queue
WHERE status IN ('pending', 'processing')
GROUP BY status;
```

| Threshold          | Status    | Action                                                        |
| ------------------ | --------- | ------------------------------------------------------------- |
| < 10               | Healthy   | —                                                             |
| 10–50              | Warning   | Check sync worker logs, may need restart                      |
| > 50               | Critical  | Sync worker likely stuck — runbook 5 (clear stuck sync queue) |
| > 100 for > 10 min | Emergency | Server may have been down — check DB, restart services        |

### 3. Risk Batch Duration

**Definition:** Time taken for the nightly at-risk prediction batch to complete.

```sql
SELECT
    DATE(computed_at) as day,
    MAX(computed_at) - MIN(computed_at) as duration
FROM student_risk_scores
WHERE computed_at >= NOW() - INTERVAL '7 days'
GROUP BY day;
```

Or from application logs:

```
INFO: Risk batch started at 02:00:01
INFO: Risk batch completed: 247 students scored in 12.3s
```

| Threshold       | Status    | Action                                                   |
| --------------- | --------- | -------------------------------------------------------- |
| < 30s           | Healthy   | —                                                        |
| 30s–120s        | Warning   | Check DB query performance, index usage                  |
| > 120s          | Critical  | Batch may timeout — optimize queries or increase timeout |
| Failed to start | Emergency | Check scheduler (celery/apscheduler), cron config        |

### 4. Backup Freshness SLO

**Definition:** Time since the last completed full backup (`backup_log.status ∈ started / completed / failed` per D47; a `failed` run counts as no completed backup for this SLO).

```sql
SELECT
    finished_at,
    EXTRACT(EPOCH FROM (NOW() - finished_at)) / 3600 as hours_since
FROM backup_log
WHERE kind = 'full' AND status = 'completed'
ORDER BY finished_at DESC
LIMIT 1;
```

| Threshold   | Status    | Action                                             |
| ----------- | --------- | -------------------------------------------------- |
| < 25 hours  | Healthy   | Daily backup on schedule                           |
| 25–48 hours | Warning   | Check backup scheduler, disk space, encryption key |
| > 48 hours  | Critical  | Manual backup needed — run backup pipeline         |
| > 72 hours  | Emergency | Data at risk — investigate immediately             |

### 5. Active Sessions (real-time)

```sql
SELECT COUNT(*) as active_sessions
FROM sessions
WHERE expires_at > NOW();
```

| Threshold | Status           | Action                                           |
| --------- | ---------------- | ------------------------------------------------ |
| 0–50      | Normal           | —                                                |
| 50–200    | High load        | Monitor DB connections, API response times       |
| > 200     | Capacity concern | Consider scaling; check connection pool settings |

### 6. API Response Time

Monitor via Uvicorn access logs or add middleware:

```python
import time
from fastapi import Request

@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    response.headers["X-Response-Time"] = f"{duration:.3f}s"
    return response
```

| Threshold     | Status   | Action                         |
| ------------- | -------- | ------------------------------ |
| < 200ms p95   | Healthy  | —                              |
| 200–500ms p95 | Warning  | Check slow queries, N+1 issues |
| > 500ms p95   | Critical | Profile endpoints, add indexes |

---

## Dashboard Quick Check

Run these commands for a 30-second system health check:

```bash
# API alive?
curl -sf http://localhost:8000/health && echo "API: OK" || echo "API: DOWN"

# Postgres alive?
pg_isready -h localhost -p 5432 && echo "DB: OK" || echo "DB: DOWN"

# Sync backlog?
psql -h localhost -U postgres -d attendance_sys -t -c \
    "SELECT COUNT(*) FROM sync_queue WHERE status IN ('pending','processing');"

# Last backup age?
psql -h localhost -U postgres -d attendance_sys -t -c \
    "SELECT EXTRACT(EPOCH FROM (NOW() - finished_at))/3600::int
     FROM backup_log WHERE kind='full' AND status='completed'
     ORDER BY finished_at DESC LIMIT 1;"

# Active sessions?
psql -h localhost -U postgres -d attendance_sys -t -c \
    "SELECT COUNT(*) FROM sessions WHERE expires_at > NOW();"
```

---

## Alerting Rules (production)

| Metric          | Condition                     | Severity | Channel     |
| --------------- | ----------------------------- | -------- | ----------- |
| API health      | HTTP 5xx for > 2 min          | Critical | Pager/Slack |
| Sync backlog    | > 50 items for > 5 min        | Warning  | Slack       |
| Sync backlog    | > 100 items for > 10 min      | Critical | Pager       |
| Backup age      | > 48 hours since last completed backup | Critical | Slack       |
| Risk batch      | Failed to complete            | Warning  | Slack       |
| DB connections  | > 80% pool utilization        | Warning  | Slack       |
| API p95 latency | > 1s for > 5 min              | Warning  | Slack       |
