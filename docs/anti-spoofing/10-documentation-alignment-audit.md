# 10 — Documentation Alignment Audit

## Discrepancy table

| Doc + section | Documented | Actual | Evidence | Why | Fix |
|---|---|---|---|---|---|
| `face-enrollment.md §2` | Server stores placeholder embedding; no generation | Server generates real `FACEEMB1` embedding via MobileFaceNet (landmark fallback) | `face_enrollment/service.py:117-131`, `shared/face_embedding_generator.py` | Docs predate real pipeline | Correct docs |
| `face-enrollment.md §2.1` | Quality gates described as implemented | `assess_image_bytes` runs 6 gates; service raises typed exceptions | `shared/face_quality.py`, `face_enrollment/service.py:104-114` | Verified | OK |
| `face-enrollment.md §2.2` | Blob plaintext; encryption not implemented | `serialize_embedding` writes `FACEEMB1` header; still plaintext at rest | `shared/face_embeddings.py:54-68`, `face_enrollment/service.py:133` | Partially implemented | Clarify |
| `security-model.md T4` | Sibling confusion partially mitigated | Server-side cosine similarity runs; no PAD CNN | `attendance/service.py:427-430`, `shared/face_embeddings.py:28` | Verified | OK |
| `security-model.md T9` | Server stores plaintext JSON today | Server stores `FACEEMB1` blob; still plaintext at rest | `face_enrollment/service.py:133`, `shared/face_embeddings.py:54` | Verified | OK |
| `data-flow.md §1` | Merge conflict resolved; score band updated | Face enrollment gate → duplicate → geofence → liveness → score band | `attendance/service.py:405-442` | Resolved | OK |
| `offline-first.md` | Staleness 60 s, idempotency TTL 900 s, process-local | `SYNC_STALE_SECONDS=60`, `IDEMPOTENCY_TTL_SECONDS=900` | `attendance/constants.py:35,41` | Verified | OK |
| `api-contracts.md` | Scan `student_number` comparison-only | Resolves by `user_id`; 403 on mismatch | `attendance/service.py:517-550` | Verified | OK |

## Known gaps / not implemented

- Liveness evidence is client-asserted; server grades submitted heuristics only.
- Benchmark mode skips geofence and liveness, but not enrollment or face match.
- Offline client performs no embedding comparison; server handles on sync.
- GPS spoofing accepted for MVP; geofence skipped when coords missing or disabled.
- Idempotency and rate limiter are process-local.
- Face enrollment blob is plaintext at rest (encryption pending).
- Review band stores computed status in `validation_status` while `evidence.review == true`.
- No per-angle re-check in review band (tie-break not implemented).
- Per-angle vectors documented in `face-enrollment.md` are not compared.
