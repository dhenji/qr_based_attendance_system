# Frontend Shared Components

Shared Svelte components live in `frontend/src/lib/components/`. Feature-specific
components live under their slice's `components/` directory.

## Shared components

| Component | Purpose |
|---|---|
| `AppIcon` | Icon wrapper |
| `ClassroomMapPicker` | Leaflet map picker with radius/GPS controls |
| `ConfirmExportDialog` | Export confirmation dialog |
| `CsvImportPage` | Reusable CSV import page |
| `EmptyState` | Empty-state placeholder |
| `ErrorBoundary` | Error boundary wrapper |
| `InstallPrompt` | PWA install prompt |
| `LoadingSpinner` | Loading spinner |
| `MfaSettings` | MFA setup/disable UI |
| `Modal` | Modal dialog |
| `NotificationBell` | Notification bell |
| `OtpCodeRow` | OTP code row |
| `OtpCountdown` | OTP countdown timer |
| `OtpInput` | OTP input |
| `PasswordRecoveryWizard` | Password recovery flow UI |
| `RadiusSelector` | Radius preset selector |
| `Skeleton` / `SkeletonCards` / `SkeletonDetail` / `SkeletonTable` | Loading skeletons |
| `TempPasswordModal` | Temporary password modal |
| `Toast` | Toast notifications |
| `Turnstile` | Cloudflare Turnstile widget |

Tests are co-located (`*.test.ts`) next to the component where present.