# 03 — API and Controller Layer

## Routers

Attendance spans two mount points (`api/router.py`):

- `backend/src/features/attendance/router.py` → prefix `/student`
  (scan, precheck, history, history/export).
- `backend/src/features/attendance/admin_router.py` → prefix `/admin/attendance`
  (overview, recent-scans, liveness-review, resolve).

Other student-facing endpoints sharing `/student` live in `features/student/router.py`,
`features/attendance/router.py` (this), `features/excuse/student_router.py`,
`features/dashboard/student_router.py` — inner paths must not collide.

## Deps and auth

- `_get_db` commits on success, rolls back on any exception
  (`api/deps.py`).
- `require_role(UserRole.STUDENT)` / `UserRole.ADMIN` (admin + super_admin pass
  admin checks) (`api/deps.py`).
- Scan rate limit: 30 calls / 60 s per IP, lifted under `BENCHMARK_MODE`
  (`attendance/router.py:45-54`).

## Idempotency

- `X-Idempotency-Key` header, max 64 chars (`constants.py:30`).
- Key scoped `user_id:session_id:key`, TTL 900 s, process-local, max 10,000
  entries (`attendance/service.py:114-120`, `constants.py:32-35`).

## Error envelopes

Backend emits `AppException` dict, FastAPI 422 list, plain-string 401/403;
`client.ts` normalizes all three and retries on 401.

## Endpoint table

| Method | Path | Purpose |
|---|---|---|
| POST | `/student/attendance/scan` | Submit scan (online or offline replay) |
| POST | `/student/attendance/precheck` | Enrollment + duplicate check |
| GET | `/student/attendance/history` | Paginated history + summary |
| GET | `/student/attendance/history/export` | CSV export |
| GET | `/admin/attendance/overview` | Per-course overview |
| GET | `/admin/attendance/overview/export` | CSV export |
| GET | `/admin/attendance/recent-scans` | Latest scans |
| GET | `/admin/attendance/liveness-review` | Flagged review queue |
| PATCH | `/admin/attendance/liveness-review/{id}/resolve` | Approve/reject review |
