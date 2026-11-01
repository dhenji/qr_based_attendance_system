# 09 — Dependencies and Data Flow

## Dependency graph (simplified)

```
scan page (Svelte)
  ├─ liveness/service.ts ──► /student/attendance/scan
  │                              │
  │                              ▼
  │                     attendance/router.py
  │                              │
  │                              ▼
  │                     AttendanceService.submit_scan
  │                       ├─ _get_active_session (session/model)
  │                       ├─ _get_active_student (student/model, identity compare)
  │                       ├─ _require_enrollment (enrollment/model)
  │                       ├─ _require_face_enrollment (student.face_embedding)
  │                       ├─ generate_embedding_from_image (face_embedding_generator)
  │                       ├─ cosine_similarity (shared/face_embeddings)
  │                       ├─ _validate_geofence / _validate_liveness
  │                       ├─ _decide_scan_outcome / _compute_status
  │                       ├─ _write_attendance (attendance/model)
  │                       └─ _maybe_record_sync (sync/model)
  └─ FaceEnrollmentService (admin) ──► assess_image_bytes + generate_embedding_from_images
```

## Transformations

- Client `live_face_image` (base64) → bytes → 512-d embedding (MobileFaceNet)
  → cosine similarity vs enrolled → `face_match_score` Decimal(5,4).
- Liveness evidence JSON stored verbatim in `liveness_evidence`.
- GPS accuracy preserved without rounding on client; server stores lat/lng.
- `scanned_at` preserved verbatim; status computed from
  `max(created_at, scheduled_start_time)`.

## Error paths

- 403 `student_number_mismatch`, `outside_geofence`, `liveness_failed`,
  `face_mismatch`, `face_not_enrolled`.
- 404 `student_not_found`, `session_not_found`, `review_not_found`.
- 409 `duplicate_scan`, `review_not_pending`.
- 422 `session_expired`, `session_not_started`.
- Client maps codes via `toScanMessage()`; network errors queue for sync.
