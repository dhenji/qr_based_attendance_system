# Frontend Shared Components

Shared Svelte components live in `frontend/src/lib/components/`. Feature-specific
components live under their slice's `components/` directory.

## Shared components

| Component | Purpose |
|---|---|
| `AcademicYearPicker` | Native-select academic-year picker (`YYYY-YYYY`) |
| `AppIcon` | Icon wrapper |
| `ArchiveRosterPage` | Shared archived student/professor roster (restore/delete, compact pagination) |
| `ClassroomMapPicker` | Leaflet map picker with radius/GPS controls |
| `ConfirmExportDialog` | Export confirmation dialog |
| `CsvImportPage` | Reusable CSV import page |
| `EmptyState` | Empty-state placeholder |
| `ErrorBoundary` | Error boundary wrapper |
| `FilterRail` | Presentational analytics filter shell (scope/advanced snippets, date presets) |
| `InstallPrompt` | PWA install prompt |
| `LoadingSpinner` | Loading spinner |
| `MfaSettings` | MFA setup/disable UI |
| `Modal` | Modal dialog |
| `NotificationBell` | Notification bell |
| `OtpCodeRow` | OTP code row |
| `OtpCountdown` | OTP countdown timer |
| `OtpInput` | OTP input |
| `Pagination` | Shared pager (`full` numbered / `compact` prev-next) |
| `PasswordRecoveryWizard` | Password recovery flow UI |
| `RadiusSelector` | Radius preset selector |
| `Skeleton` / `SkeletonCards` / `SkeletonDetail` / `SkeletonTable` | Loading skeletons |
| `TempPasswordModal` | Temporary password modal |
| `Toast` | Toast notifications |
| `Turnstile` | Cloudflare Turnstile widget |

Tests are co-located (`*.test.ts`) next to the component where present.

## Shared support modules

| Module | Purpose |
|---|---|
| `archive-roster.ts` | Types/config for `ArchiveRosterPage` (`ArchiveRosterItem`, `ArchiveRosterState`, `ArchiveRosterConfig`, `archiveRosterFullName`) |
| `filter-rail.ts` | Date preset ids/labels (`DATE_PRESETS`), `DatePresetId`/`PresetId`, and `presetDateRange()` local-date range math |
| `../shared/requestToken.ts` | `createRequestTokenGuard()` monotonic guard for overlapping list loads |

`Pagination` is used with `variant="full"` by analytics, professor attendance,
student history, and excuse requests; the archive pages use `variant="compact"`.
`FilterRail` is controlled: the parent owns filter values, course search,
advanced-open state, and fetching, and passes entity-specific controls through
the `scope` and `advanced` snippets.
