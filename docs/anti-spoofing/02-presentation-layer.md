# 02 — Presentation Layer

## Liveness UI

- `frontend/src/lib/features/liveness/components/FaceScanner.svelte` — blink +
  head-turn challenge; selfie-mirrored preview; 6-step progress indicator;
  status-tinted instruction hint.
- `frontend/src/lib/features/liveness/components/QRScanner.svelte` — session code
  scan (camera/upload).
- `frontend/src/lib/features/liveness/errors.ts` — `SCAN_ERROR_MESSAGES`,
  `toScanMessage()`.

## GPS flow

- `frontend/src/routes/student/scan/+page.svelte` runs a location check before
  face liveness: `requestBestPosition()` (watchPosition, up to 3 fixes, early
  stop at accuracy ≤ 50 m); shows accuracy, distance, radius, within/outside.
- `frontend/src/lib/shared/utils/geo.ts` — `requestBestPosition`,
  `calculateDistanceMeters`, `getAccuracyStatus`, `isLowAccuracy`.
- `Continue` disabled while locating or outside geofence; low accuracy still
  allows continuation.

## Sync queue

- `frontend/src/lib/features/sync/service.ts` — IndexedDB `attendance_queue`;
  enqueue, drain, backoff, rejected item handling.
- Backoff `min(30s * 2^retry_count, 30 min)`.

## Error display

- Backend codes map via `toScanMessage()`; network errors queue for sync.
- Rejected scan (`result.status === 'rejected'`) shows permitted-time-window
  copy, not raw backend messages.
- `.error` paragraphs styled as alert banners (`+page.svelte`).
