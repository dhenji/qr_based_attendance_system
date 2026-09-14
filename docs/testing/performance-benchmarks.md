# Performance Benchmarks — QR Attendance System

> **Purpose:** Define performance targets, measurement methods, and acceptance
> criteria for critical system paths. Used during development to validate
> non-functional requirements and in production for SLO monitoring.

---

## Table of Contents

1. [Scan-Step Latencies](#1-scan-step-latencies)
2. [Concurrent Session Sync](#2-concurrent-session-sync)
3. [Risk Batch Processing](#3-risk-batch-processing)
4. [Backup Size & Time Scaling](#4-backup-size--time-scaling)
5. [API Response Targets](#5-api-response-targets)
6. [Frontend Rendering](#6-frontend-rendering)
7. [Measurement Infrastructure](#7-measurement-infrastructure)

---

## 1. Scan-Step Latencies

The student scan flow is the most latency-sensitive path. Each step has a target
latency measured from client action to next-screen-ready.

| Step                       | Description                                     | Target (p50) | Target (p95) | Target (p99) | Measurement Method                                                                                            |
| -------------------------- | ----------------------------------------------- | ------------ | ------------ | ------------ | ------------------------------------------------------------------------------------------------------------- |
| 1a                         | Session code verify (manual entry)              | <200ms       | <500ms       | <800ms       | Client performance.mark/measure; API `POST /student/sessions/verify-code` duration logged server-side         |
| 1b                         | Session QR scan → decode → verify               | <300ms       | <600ms       | <1000ms      | Client-side camera decode time + API verify-code latency                                                      |
| 2                          | Student-ID QR scan → resolve → fetch record     | <300ms       | <600ms       | <1000ms      | API `POST /student/attendance/scan` (student_id resolution + enrollment check + duplicate check)              |
| 3                          | GPS geofence validation                         | <50ms        | <100ms       | <150ms       | Haversine computation is local; GPS position fix time excluded (hardware-dependent)                           |
| 4a                         | Face liveness challenge (client-side MediaPipe) | <5000ms      | <8000ms      | <12000ms     | Client-side: start challenge to all 3 steps confirmed. Includes blink detection + turn detection              |
| 4b                         | Face embedding comparison (server)              | <100ms       | <200ms       | <300ms       | Cosine similarity computation; embedding fetched from cache/DB                                                |
| 5                          | Attendance record write + response              | <100ms       | <250ms       | <500ms       | DB insert + response delivery                                                                                 |
| **Full scan (happy path)** | **Steps 1a→5 end-to-end**                       | **<6s**      | **<10s**     | **<15s**     | **Client-to-client measurement (excludes GPS fix time and liveness challenge time which are user-dependent)** |

> **Note on "Full scan" targets:** The p50/p95/p99 targets above measure
> server-side API latency only (steps 1a + 2 + 4b + 5). Steps 3 (GPS fix)
> and 4a (liveness challenge) are hardware/user-dependent and excluded from
> this aggregate. For inclusive end-to-end client timing, sum the individual
> step targets for your device class.

### Offline Scan → Sync Latency

| Metric                               | Target | Measurement                                                     |
| ------------------------------------ | ------ | --------------------------------------------------------------- |
| Queue item sync (single)             | <500ms | Time from sync trigger to server response for one queued record |
| Batch sync (10 items)                | <3s    | Time from batch push to all items processed                     |
| Sync after long offline (100 queued) | <30s   | Full queue drain with exponential backoff                       |

---

## 2. Concurrent Session Sync

Simulates 30 students scanning simultaneously during an active session.

### Test Scenario

| Parameter           | Value                                                   |
| ------------------- | ------------------------------------------------------- |
| Concurrent students | 30                                                      |
| Session             | GE101, 30 students enrolled                             |
| Device mix          | 15 online, 10 with 1–3 queued offline, 5 with 5+ queued |
| Scan pattern        | Poisson distribution over 5-minute window (λ = 6/min)   |
| Network             | Simulated 3G (1.5 Mbps down, 768 Kbps up, 100ms RTT)    |

### Targets

| Metric                               | Target                              | Acceptance                               |
| ------------------------------------ | ----------------------------------- | ---------------------------------------- |
| Server throughput (requests/sec)     | ≥10 req/s sustained                 | All 30 scans processed within 5 minutes  |
| Server response time (p95)           | <1s per scan submission             | Under concurrent load                    |
| Server response time (p99)           | <2s per scan submission             | Under concurrent load                    |
| Concurrent connection limit          | ≥30 simultaneous                    | No connection refused errors             |
| Queue drain time (all offline syncs) | <60s after last device comes online | All pending records processed            |
| Conflict rate (duplicate scan)       | 0% false duplicates                 | No legitimate scan rejected as duplicate |
| Attendance accuracy                  | 100% correct present/late/absent    | All 30 records match expected status     |

### Measurement Method

1. Use `locust` or `k6` with 30 virtual users, each simulating one student's scan flow.
2. Server-side: log `time.perf_counter()` around each endpoint handler; aggregate with `statistics.mean()`, `statistics.quantiles()`.
3. Client-side: `performance.mark()` at each step; `performance.measure()` at completion; report via `navigator.sendBeacon()` to analytics endpoint.
4. Database: `EXPLAIN ANALYZE` on attendance record insert under concurrent load.

---

## 3. Risk Batch Processing

Nightly batch job computing at-risk scores for all active enrollments.

### Test Scenario

| Parameter                      | Value                                                   |
| ------------------------------ | ------------------------------------------------------- |
| Total students                 | 10,000                                                  |
| Active enrollments             | 25,000 (avg 2.5 courses per student)                    |
| Historical sessions per course | 32 (16 weeks × 2/week)                                  |
| Historical attendance records  | ~800,000                                                |
| Risk features computed         | absence_rate, max_streak, sync_lag_pending, trend_slope |

### Targets

| Metric                         | Target                      | Acceptance                             |
| ------------------------------ | --------------------------- | -------------------------------------- |
| Batch job total runtime        | <5 minutes                  | All 25,000 enrollment scores computed  |
| DB query time (per enrollment) | <10ms                       | Index-backed; no full table scans      |
| DB write throughput (upserts)  | ≥500 writes/sec             | Batch upserts to student_risk_scores   |
| Memory usage                   | <512MB RSS                  | No memory leaks; streaming computation |
| CPU utilization                | <80% single-core            | During batch window                    |
| Score accuracy                 | ±0.01 vs manual calculation | Spot-check 20 random students          |

### Expected Sessions Formula (D35)

```
expected_sessions = semester_weeks × sessions_per_week
e.g., GE101: 16 × 2 = 32 expected sessions
e.g., CS101: 16 × 3 = 48 expected sessions
```

### Heuristic Thresholds (D35)

| Feature                     | Threshold    | Risk Level |
| --------------------------- | ------------ | ---------- |
| absence_rate                | > 0.30       | high       |
| absence_rate                | > 0.15       | medium     |
| streak (consecutive misses) | >= 3         | high       |
| sync_lag (pending records)  | >= 5         | medium     |
| trend_slope (4-week linear) | < -0.05/week | medium     |

### Measurement Method

1. Seed 10k students + 25k enrollments + 800k attendance records via `test_seed_data.py --scale 10k`.
2. Run batch job with `time` command; record wall-clock time.
3. Profile with `cProfile` or `py-spy` to identify bottlenecks.
4. Spot-check: manually compute 20 random students' scores in SQL and compare with batch output.
5. Verify index usage: `EXPLAIN ANALYZE` on the main batch query.

---

## 4. Backup Size & Time Scaling

### Test Scenario

| Data Volume     | Students | Sessions | Attendance Records | Expected DB Size |
| --------------- | -------- | -------- | ------------------ | ---------------- |
| Small (dev)     | 50       | 50       | 2,000              | ~5 MB            |
| Medium (pilot)  | 500      | 500      | 20,000             | ~50 MB           |
| Large (full)    | 10,000   | 5,000    | 200,000            | ~500 MB          |
| XL (multi-year) | 50,000   | 25,000   | 1,000,000          | ~2.5 GB          |

### Targets

| Metric                                  | Small | Medium | Large   | XL      | Acceptance               |
| --------------------------------------- | ----- | ------ | ------- | ------- | ------------------------ |
| pg_dump time                            | <2s   | <10s   | <60s    | <5min   | Compressed custom format |
| Encryption time (AES-256-GCM)           | <1s   | <3s    | <15s    | <60s    | Per backup               |
| Total backup time (dump+encrypt+upload) | <5s   | <15s   | <90s    | <8min   | End-to-end               |
| Compressed backup size                  | <2 MB | <15 MB | <150 MB | <800 MB | ~30% of raw              |
| Backup verification (sha256 check)      | <1s   | <2s    | <5s     | <15s    | Sidecar file             |
| Restore time (decrypt+pg_restore)       | <3s   | <15s   | <90s    | <8min   | Full restore             |
| Retention prune (30 daily + 12 monthly) | <1s   | <2s    | <5s     | <10s    | Only old backups removed |

### Measurement Method

1. Generate test data at each volume using `test_seed_data.py --scale {small|medium|large|xl}`.
2. Run backup pipeline: `pg_dump -Fc | gzip | openssl enc -aes-256-gcm`; measure each stage with `time` and `pv`.
3. Verify restored data matches source: `pg_dump | pg_restore | pg_dump` round-trip comparison.
4. Monitor disk I/O with `iostat` during backup.
5. Verify `backup_log` entry has correct sha256, size_bytes, duration.

---

## 5. API Response Targets

General API endpoint performance under normal load (not peak).

| Endpoint Category                  | Target (p50) | Target (p95) | Notes                          |
| ---------------------------------- | ------------ | ------------ | ------------------------------ |
| Auth (login, OTP)                  | <300ms       | <1s          | Includes Argon2id verification |
| CRUD (programs, courses, students) | <100ms       | <300ms       | Standard ORM operations        |
| Session creation                   | <200ms       | <500ms       | Includes HMAC generation       |
| Attendance submit (online)         | <300ms       | <800ms       | Includes face score validation |
| Attendance submit (offline sync)   | <200ms       | <500ms       | Per-item in batch              |
| Analytics queries                  | <500ms       | <2s          | Aggregation over filtered data |
| Report generation (CSV/PDF)        | <2s          | <5s          | Depends on data volume         |
| Backup trigger                     | <5s          | <30s         | Async; returns job ID          |

---

## 6. Frontend Rendering

| Metric                               | Target | Measurement                                             |
| ------------------------------------ | ------ | ------------------------------------------------------- |
| First Contentful Paint (FCP)         | <1.5s  | Lighthouse CI                                           |
| Largest Contentful Paint (LCP)       | <2.5s  | Lighthouse CI                                           |
| Time to Interactive (TTI)            | <3.0s  | Lighthouse CI                                           |
| Cumulative Layout Shift (CLS)        | <0.1   | Lighthouse CI                                           |
| Camera initialization (scanner page) | <2s    | `performance.mark('camera-start')` to first frame       |
| IndexedDB read (cached embedding)    | <50ms  | `performance.measure()` around DB transaction           |
| Chart.js render (analytics page)     | <500ms | `performance.measure()` from data fetch to canvas paint |

---

## 7. Measurement Infrastructure

### Tooling

| Tool                          | Purpose                            | When to Run            |
| ----------------------------- | ---------------------------------- | ---------------------- |
| `pytest-benchmark`            | Python API endpoint benchmarks     | CI pipeline (nightly)  |
| `k6` or `locust`              | Load testing (concurrent sessions) | Pre-release validation |
| `Lighthouse CI`               | Frontend performance               | CI pipeline (per PR)   |
| `cProfile` / `py-spy`         | Python profiling (batch jobs)      | During optimization    |
| `EXPLAIN ANALYZE`             | Query plan analysis                | During development     |
| `pgBadger`                    | Postgres query log analysis        | Production monitoring  |
| `prometheus-client` + Grafana | Runtime metrics dashboard          | Production             |

### Environment Variables for Benchmarking

```bash
# Disable face verification in benchmarks (isolates API performance)
FACE_MATCH_THRESHOLD=0.0          # accept all scores in bench mode
BENCHMARK_MODE=true               # skip geofence, liveness checks

# Risk batch tuning
RISK_BATCH_CHUNK_SIZE=1000        # upsert batch size
RISK_BATCH_WORKERS=4              # parallel workers

# Backup benchmark
BACKUP_COMPRESSION_LEVEL=6        # gzip level (1=fast, 9=best)
```

### Reporting Template

```markdown
## Benchmark Run — {date}

| Metric                      | Target | Actual | Status    |
| --------------------------- | ------ | ------ | --------- |
| Scan full happy path (p50)  | <6s    | Xs     | PASS/FAIL |
| 30-student concurrent (p95) | <1s    | Xs     | PASS/FAIL |
| Risk batch (10k students)   | <5min  | Xmin   | PASS/FAIL |
| Backup (large, 500MB)       | <90s   | Xs     | PASS/FAIL |
```
