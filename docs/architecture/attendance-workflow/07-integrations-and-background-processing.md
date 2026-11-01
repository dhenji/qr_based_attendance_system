# 07 — Integrations and Background Processing

## Face embedding generation

- `shared/face_embedding_generator.py::generate_embedding_from_image(content)` —
  MobileFaceNet ONNX (512-d) when available, landmark fallback.
- `shared/face_embeddings.py` — `cosine_similarity`, `serialize_embedding`/
  `deserialize_embedding` (header `FACEEMB1`, dims 128/512),
  `embedding_from_base64`, `is_stub_embedding`.
- Enrollment gate: `student.face_embedding is None` → 403 `face_not_enrolled`
  (`attendance/service.py:582`); stub embeddings raise
  `StubEmbeddingException`.

## MediaPipe quality gates

- `shared/face_quality.py::assess_image_bytes` — 6 gates: decode, detection,
  single face, brightness, face size, centering, sharpness, eyes open.
  Thresholds: `BRIGHTNESS_MIN/MAX`, `FACE_SIZE_MIN_RATIO`, `CENTERING_MAX_OFFSET`,
  `SHARPNESS_MIN_VARIANCE`, `EAR_MIN`. Used by face enrollment.

## Email

- `shared/email.py` — stdlib `smtplib`, never raises; empty `SMTP_HOST` skips.
- Excuse notifications use `features/excuse/notifications.py` builders +
  `ExcuseService` dispatch (not attendance scan).

## Cron risk batch

- `core/scheduler.py` owns APScheduler; job body
  `analytics/batch.py::run_scheduled_risk_batch` (02:00) commits its own tx.
- `RISK_BATCH_WORKERS` shards scoring (`analytics/batch.py`).

## Sync replay

- Client drains `attendance_queue`; POST with `X-Idempotency-Key`; server
  `_get_active_session(..., allow_expired=True)` when key present
  (`attendance/service.py:407`).
- Stale gate: `_maybe_record_sync` queues only when
  `(now - scanned_at) > SYNC_STALE_SECONDS` (60 s).
- Idempotency TTL 900 s, process-local.
