# 07 — Integrations and Background Processing

## MediaPipe quality gates

`shared/face_quality.py::assess_image_bytes` decodes bytes and runs detection,
single face, brightness, face size, centering, sharpness, eyes-open gates.
Thresholds: `BRIGHTNESS_MIN/MAX`, `FACE_SIZE_MIN_RATIO`,
`CENTERING_MAX_OFFSET`, `SHARPNESS_MIN_VARIANCE`, `EAR_MIN`.

## Face embedding generation

- `shared/face_embedding_generator.py::generate_embedding_from_image` —
  MobileFaceNet ONNX (512-d) with landmark fallback.
- `shared/face_embeddings.py` — `cosine_similarity`, `serialize_embedding`/
  `deserialize_embedding` (`FACEEMB1`, dims 128/512), `is_stub_embedding`.
- Enrollment uses `generate_embedding_from_images` (front/left/right).

## Benchmark mode

`BENCHMARK_MODE=true` skips geofence + liveness (`attendance/service.py:436`)
and the per-IP scan rate gate (`attendance/router.py:49-53`). Face enrollment
and face match still run.

## Admin review audit

`resolve_review` writes an audit row (`AuditAction.APPROVE/REJECT`,
`AuditEntity.ATTENDANCE_RECORD`) with old/new validation status and note
(`attendance/service.py:1241`).

## Email

Not used in scan anti-spoofing; `shared/email.py` is the single delivery path.
