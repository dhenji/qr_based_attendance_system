# 02 — Presentation Layer

## Scan page steps

`frontend/src/routes/student/scan/+page.svelte` drives a 4-step state machine:
`entry` → `confirm` → `location` (only when geofence required) → `liveness`.

- Entry: QR camera (`QRScanner.svelte`) or manual code; `verifyCode()`
  calls `verifySessionCode()` and caches session config (`cacheSession`).
- Confirm: prefill `idNumber` from profile; `checkId()` calls
  `precheckScan()` (enrollment + duplicate gate). Offline skips the gate.
- Location: `requestGps()` uses `requestBestPosition()` (watchPosition, up to
  3 fixes, early stop at accuracy ≤ 50 m); shows accuracy, distance, radius,
  within/outside. `Continue` disabled while locating or outside geofence.
- Liveness: `FaceScanner.svelte` runs MediaPipe FaceLandmarker WASM; on
  completion `handleLivenessComplete()` → `doSubmit()`.

## Liveness components

- `frontend/src/lib/features/liveness/components/FaceScanner.svelte` — blink +
  head-turn challenge; selfie-mirrored preview; 6-step progress indicator.
- `frontend/src/lib/features/liveness/components/QRScanner.svelte` — session code
  scan (camera/upload).
- `frontend/src/lib/features/liveness/service.ts` — `verifySessionCode`,
  `precheckScan`, `submitAttendanceScan`, `validateGPS`.
- `frontend/src/lib/features/liveness/errors.ts` — `SCAN_ERROR_MESSAGES`,
  `toScanMessage()` (centralized error copy).

## Sync queue

- `frontend/src/lib/features/sync/service.ts` — IndexedDB `attendance_queue`;
  `enqueue`, `flushQueue`, `getPendingCount`, `getRejected`, `retryDelayMs`.
- Backoff: `min(30s * 2^retry_count, 30 min)` (`retryDelayMs`).
- `registerOutboxSync()` relays Service Worker `FLUSH_OUTBOX` messages.

## GPS utilities

- `frontend/src/lib/shared/utils/geo.ts` — `requestBestPosition`,
  `calculateDistanceMeters`, `clamp`, `getAccuracyStatus`, `isLowAccuracy`.

## Error display

- `scanError` shows only when `step !== 'confirm'`; `.error` styled as alert
  banner (`+page.svelte` CSS). Backend codes map via `toScanMessage()`.
- Rejected scan (`result.status === 'rejected'`) shows the permitted-time-window
  copy, never a raw backend message.
- `session_not_started` copy: "Please wait until the scheduled start time."
