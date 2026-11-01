# 06 — Data Access and Persistence Layer

## Models

- `features/attendance/model.py::Attendance` → table `attendance_records`
  (`id`, `student_id`, `session_id`, `timestamp`, `gps_lat`, `gps_lng`,
  `validation_status`, `sync_status`, `liveness_evidence` JSONB,
  `face_match_score` Numeric(5,4), `scanned_via`, `original_status`,
  `excuse_*`, `excuse_request_id`).
  Index `ix_attendance_records_student_id_timestamp`.
- `features/session/model.py::Session` → `sessions` (windows, scheduled start/end,
  `expires_at`, classroom coords, `geofence_enabled`, `is_remote`,
  `session_type`, override columns).
- `features/student/model.py::Student` → `students` (unique `user_id`,
  `face_embedding` LargeBinary, algorithm/version).
- `features/sync/model.py::SyncQueue` → `sync_queue` (`record_data` JSON,
  `status`, `retry_count`).

FKs use `ondelete=RESTRICT`; deletes need has-records guards (409).

## Queries

- Duplicate check: `Attendance` where session_id + student_id
  (`attendance/service.py:567`).
- History base joins Session → CourseOffering → Course, filtered by student
  (`attendance/service.py:848`).
- Review queue filters on
  `cast(liveness_evidence["review"], Boolean) == True`
  (`attendance/service.py:283`).

## SQLite shims (tests only)

`conftest.py` shims: JSONB→JSON, BigInteger→INTEGER, aware-UTC DateTime,
`PRAGMA foreign_keys=ON`. Inert on Postgres.

## Transactions

`_get_db` commits on success / rolls back on exception. Services only `flush()`.
Lockout bookkeeping is the exception (commits on its own session).
