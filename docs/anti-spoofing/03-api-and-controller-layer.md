# 03 — API and Controller Layer

## Endpoints

- `POST /student/attendance/scan` — submit scan (online or offline replay).
- `POST /student/attendance/precheck` — enrollment + duplicate check.
- `GET /admin/attendance/liveness-review` — flagged review queue.
- `PATCH /admin/attendance/liveness-review/{id}/resolve` — approve/reject.
- `GET/POST/DELETE /admin/face-enrollment/{student_id}` — enrollment status,
  enroll (multipart), revoke.

## Deps and auth

- `_get_db` commits on success / rolls back on exception.
- `require_role(UserRole.STUDENT)` / `UserRole.ADMIN`.
- Scan rate limit: 30 calls / 60 s per IP, lifted under `BENCHMARK_MODE`
  (`attendance/router.py:45-54`).

## Idempotency

- `X-Idempotency-Key` header, max 64 chars (`constants.py:30`).
- Key scoped `user_id:session_id:key`, TTL 900 s, process-local, max 10,000
  entries (`attendance/service.py:114-254`, `constants.py:32-35`).

## Error envelopes

Backend emits AppException dict, FastAPI 422 list, plain-string 401/403;
`client.ts` normalizes all three and retries on 401.

## Error codes

`outside_geofence`, `liveness_failed`, `face_mismatch`, `face_not_enrolled`,
`student_number_mismatch`, `duplicate_scan`, `not_enrolled`, `session_expired`,
`session_not_started`, `review_not_found`, `review_not_pending`.
