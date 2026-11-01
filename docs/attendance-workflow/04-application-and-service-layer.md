# 04 — Application and Service Layer

## AttendanceService

`backend/src/features/attendance/service.py` (`AttendanceService`, class, DI via
`AttendanceServiceDep`). Methods:

- `submit_scan(payload, user_id, idempotency_key)` — full scan pipeline.
- `precheck_scan(session_id, user_id, student_number)` — read-only enrollment +
  duplicate check.
- `get_history(...)` / `export_history_csv(...)` — student history.
- `get_overview(...)` / `export_overview_csv(...)` — admin per-course overview.
- `get_recent_scans(limit)` — latest scans feed.
- `list_liveness_review(status, page, size)` — review queue.
- `resolve_review(record_id, decision, actor_id, note)` — approve/reject.

Key internal helpers: `_resolve_scan_parties`, `_decide_scan_outcome`,
`_persist_scan`, `_write_attendance`, `_maybe_record_sync`,
`_get_active_session`, `_get_active_student`, `_require_*`,
`_validate_geofence`, `_validate_liveness`, `_is_review_band`,
`_compute_status`, `_build_evidence`.

## SessionService

`backend/src/features/session/service.py` (`SessionService`). Lifecycle:

- `create_session(professor_id, payload, actor_id, now)` — opens a session,
  inherits offering plan (D93), stamps `expires_at = min(created_at + duration,
  scheduled_end_time)` (D49/D94), records audit `OPEN`.
- `get_active_session(session_id)` — returns session + scanned student tiles.
- `close_session(session_id)` — stamps `expires_at = now`.
- Status derived `_session_status(expires_at, scheduled_start_time, now)` →
  `scheduled`/`active`/`closed` (`session/service.py:148`).

## Sync model

- `features/sync/model.py::SyncQueue` — `record_data` JSON, `status`
  (`QueueStatus`), `retry_count`.
- Written by `_maybe_record_sync` when `(now - scanned_at) > SYNC_STALE_SECONDS`
  (60 s) (`attendance/service.py:689`).
- Replay passes `allow_expired=True` so a queued scan survives past
  `expires_at` (`attendance/service.py:407`).

## Transactions

Services only `flush()`; `_get_db` commits on success / rolls back on
exception.
