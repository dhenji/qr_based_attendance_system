# 06 — Data Access and Persistence Layer

## Models

- `features/attendance/model.py::Attendance` → `attendance_records`
  (`validation_status`, `original_status`, `liveness_evidence` JSONB,
  `face_match_score` Numeric(5,4), `sync_status`, `scanned_via`).
- `features/session/model.py::Session` → `sessions` (`geofence_enabled`,
  `is_remote`, classroom coords, `expires_at`).
- `features/student/model.py::Student` → `students` (`face_embedding`
  LargeBinary, algorithm, version, enrolled_at).
- Review queue filter: `cast(liveness_evidence["review"], Boolean) == True`
  (`attendance/service.py:283`).

## Transactions

Services only `flush()`; `_get_db` commits/rolls back. Audit rows are
flush-only and roll back with the mutation.

## SQLite shims (tests)

JSONB→JSON, BigInteger→INTEGER, aware-UTC DateTime, `PRAGMA foreign_keys=ON`.
