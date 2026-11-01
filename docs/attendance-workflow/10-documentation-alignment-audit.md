# 10 — Documentation Alignment Audit

## Discrepancy table

| Doc + section | Documented | Actual | Evidence | Why | Fix |
|---|---|---|---|---|---|
| `data-flow.md §1` Step 4 | `face_match_score = placeholder 1.0 (no embedding comparison)` | Server generates embedding from `live_face_image` (MobileFaceNet) and runs `cosine_similarity`; client sends image. Threshold 0.70, review band 0.65 | `attendance/service.py:414-435`, `shared/face_embedding_generator.py`, `core/config.py:47-48` | Stale claim predates server-side embedding | Corrected |
| `data-flow.md §1` merge-conflict block | Two step orders (duplicate/geofence/liveness/score) | Face enrollment gate → duplicate → geofence → liveness → score band | `attendance/service.py:405-442` | Unresolved merge conflict | Resolved to actual order |
| `data-flow.md §1` status compute | elapsed since `session.created_at` | `max(created_at, scheduled_start_time)` anchor | `attendance/service.py:625-643` | Future-opened sessions must not penalise early scans | Corrected |
| `data-flow.md §1` identity note | `face_match_score` client-supplied; server never compares | Server compares embeddings; client supplies image | `attendance/service.py:414-435` | ADR-068 superseded by server-side gen | Corrected |
| `data-flow.md §1` geofence | (implicit always) | Only when `geofence_enabled` and classroom coords present; missing GPS → outside | `attendance/service.py:591-611` | Explicit flag + missing-fix handling | Documented |
| `offline-first.md` staleness | 60 s staleness | `SYNC_STALE_SECONDS = 60` | `attendance/constants.py:41`, `attendance/service.py:698` | Verified | OK |
| `offline-first.md` idempotency TTL | 15 min | `IDEMPOTENCY_TTL_SECONDS = 900` | `attendance/constants.py:35` | Verified | OK |
| `offline-first.md` process-local caveat | process-local | `_IDEMPOTENCY_STORE` dict, max 10,000 | `attendance/service.py:114-120` | Verified | OK |
| `offline-first.md` replay | `allow_expired` | `allow_expired=idempotency_key is not None` | `attendance/service.py:407` | Verified | OK |
| `project-structure.md` | router counts | 23 routers / 15 mounts; attendance spans two routers | `attendance/router.py:37`, `attendance/admin_router.py:38`, `api/router.py` | Verified | OK |
| `security-model.md` / `frontend-architecture.md` | mock flag location | Only `client.ts` reads `PUBLIC_MOCK_MODE` | `frontend/src/lib/api/client.ts` | Verified | OK |
| `api-contracts.md` | scan `student_number` | comparison-only, resolves by `user_id` | `attendance/service.py:517-550` | Verified | OK |

## Known gaps / not implemented

- Client-side face embedding compare (offline) — not implemented; cached
  embedding stored as ciphertext with no decrypt-and-compare path
  (`offline-first.md` §Offline Verification).
- Service Worker Background Sync is a relay only; drain runs in-page.
- Idempotency store is process-local; multi-instance needs a shared store.
- `face_match_score` client placeholder copy in some older docs superseded.
- In-app notification table — unimplemented by design.
