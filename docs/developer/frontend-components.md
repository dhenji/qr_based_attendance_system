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

## Feature components

Feature-specific components live under their slice's `components/` directory.
The admin offering detail page
(`frontend/src/routes/admin/offerings/[id]/+page.svelte`) is composed of these,
with the parent owning tab routing, page-level loads, the overview, and the
roster table. Inactive tabs are kept mounted behind `hidden` so inline form
drafts survive a tab switch, so their component instances (including the CSV
file input and `ClassroomMapPicker`) persist across tabs.

### `features/admin/offerings/components/`

| Component | Responsibility |
|---|---|
| `OfferingSettingsCard.svelte` | Offering settings form (present/late windows, geofence radius, classroom GPS) with Zod validation and inline field errors |
| `OfferingDangerZone.svelte` | Archive / reactivate / permanent-delete flows with their confirmation dialogs |
| `OfferingMeetingsCard.svelte` | Class-meeting (component) CRUD: add/edit/remove rows and the weekly-hours projection against course units |
| `OfferingAssignmentsCard.svelte` | Professor assignments with effective dating and all seven confirmation flows |
| `BulkEnrollCard.svelte` | CSV bulk enrollment of existing students |
| `AddStudentModal.svelte` | Add-student wizard (search cohort, multi-select, submit via the bulk-CSV path) |
| `UnenrollStudentDialog.svelte` | Unenroll confirmation |
| `DayPicker.svelte` / `MeetingRowsEditor.svelte` | Reusable editors shared by the offering forms |

Shared helper: `features/admin/offerings/formHelpers.ts` exports `parseOptCoord`
(used by the settings and meetings cards).
