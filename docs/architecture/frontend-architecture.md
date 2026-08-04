# Frontend Architecture (Production Ready)

> This document contains a recommended production-ready SvelteKit
> frontend structure for the Attendance System. Comments beside each
> major file describe its responsibility.

```text
frontend/
│
├── src/
│   ├── app.html                          # Main HTML template
│   ├── app.d.ts                          # Global TypeScript declarations
│   ├── hooks.server.ts                   # Authentication, authorization, request hooks
│   ├── hooks.client.ts                   # Theme, analytics, reconnect handling
│   ├── service-worker.ts                 # PWA offline caching & background sync
│   │
│   ├── routes/
│   │   ├── +layout.svelte                # Root application layout
│   │   ├── +error.svelte                 # Global error page
│   │   ├── +page.svelte                  # Landing page
│   │   │
│   │   ├── (auth)/
│   │   │   ├── +layout.svelte            # Authentication layout
│   │   │   ├── login/
│   │   │   │   ├── +page.svelte          # Login page
│   │   │   │   └── +page.ts              # Redirect authenticated users
│   │   │   ├── register/
│   │   │   │   ├── +page.svelte          # Registration page
│   │   │   │   └── +page.ts              # Registration loader
│   │   │   ├── forgot-password/
│   │   │   │   └── +page.svelte          # Forgot password
│   │   │   └── reset-password/
│   │   │       └── +page.svelte          # Reset password
│   │   │
│   │   ├── (student)/
│   │   │   ├── +layout.svelte            # Student layout/sidebar
│   │   │   ├── dashboard/
│   │   │   │   ├── +page.svelte          # Student dashboard
│   │   │   │   ├── attendance/+page.svelte   # Today's attendance
│   │   │   │   ├── history/+page.svelte      # Attendance history
│   │   │   │   ├── schedule/+page.svelte     # Class schedule
│   │   │   │   ├── notifications/+page.svelte# Notifications
│   │   │   │   ├── profile/+page.svelte      # Student profile
│   │   │   │   └── settings/+page.svelte     # Student settings
│   │   │   └── scan/
│   │   │       ├── +page.svelte          # QR scanner
│   │   │       ├── success/+page.svelte  # Scan success
│   │   │       └── failed/+page.svelte   # Scan failed
│   │   │
│   │   ├── (professor)/
│   │   │   ├── +layout.svelte            # Professor layout
│   │   │   └── dashboard/
│   │   │       ├── +page.svelte          # Professor dashboard
│   │   │       ├── attendance/
│   │   │       │   ├── +page.svelte      # Attendance list
│   │   │       │   ├── live/+page.svelte # Live attendance
│   │   │       │   ├── history/+page.svelte # Attendance history
│   │   │       │   └── export/+page.svelte  # Export attendance
│   │   │       ├── sessions/
│   │   │       │   ├── +page.svelte      # Sessions overview
│   │   │       │   ├── create/+page.svelte # Create session
│   │   │       │   ├── active/+page.svelte # Active session
│   │   │       │   └── history/+page.svelte # Session history
│   │   │       ├── courses/+page.svelte  # Assigned courses
│   │   │       ├── reports/
│   │   │       │   ├── +page.svelte      # Reports dashboard
│   │   │       │   ├── daily/+page.svelte
│   │   │       │   ├── weekly/+page.svelte
│   │   │       │   ├── monthly/+page.svelte
│   │   │       │   └── export/+page.svelte
│   │   │       ├── profile/+page.svelte  # Professor profile
│   │   │       └── settings/+page.svelte # Professor settings
│   │   │
│   │   └── (admin)/
│   │       ├── +layout.svelte            # Admin layout
│   │       └── dashboard/
│   │           ├── +page.svelte          # Admin dashboard
│   │           ├── students/
│   │           │   ├── +page.svelte      # Student management
│   │           │   ├── create/+page.svelte
│   │           │   ├── edit/+page.svelte
│   │           │   ├── import/+page.svelte
│   │           │   └── archive/+page.svelte
│   │           ├── professors/
│   │           │   ├── +page.svelte
│   │           │   ├── create/+page.svelte
│   │           │   └── edit/+page.svelte
│   │           ├── courses/
│   │           │   ├── +page.svelte
│   │           │   ├── create/+page.svelte
│   │           │   ├── edit/+page.svelte
│   │           │   └── schedule/+page.svelte
│   │           ├── attendance/
│   │           │   ├── +page.svelte
│   │           │   ├── overview/+page.svelte
│   │           │   └── analytics/+page.svelte
│   │           ├── reports/
│   │           │   ├── +page.svelte
│   │           │   ├── attendance/+page.svelte
│   │           │   ├── students/+page.svelte
│   │           │   ├── professors/+page.svelte
│   │           │   └── export/+page.svelte
│   │           ├── audit-logs/+page.svelte   # System logs
│   │           ├── system/
│   │           │   ├── settings/+page.svelte
│   │           │   ├── backup/+page.svelte
│   │           │   └── maintenance/+page.svelte
│   │           └── profile/+page.svelte
│   │
│   ├── lib/
│   │   ├── components/
│   │   │   ├── attendance/              # Attendance UI components
│   │   │   ├── scanner/                 # QR scanner module
│   │   │   │   ├── QRScanner.svelte         # Initialize scanner
│   │   │   │   ├── CameraView.svelte        # Camera preview
│   │   │   │   ├── ScannerOverlay.svelte    # Scanner guide
│   │   │   │   ├── SessionCodeInput.svelte  # Session code input
│   │   │   │   ├── GPSStatus.svelte         # GPS indicator
│   │   │   │   ├── PermissionPrompt.svelte  # Camera/GPS permissions
│   │   │   │   ├── ScanResult.svelte        # Result message
│   │   │   │   └── OfflineStatus.svelte     # Pending sync
│   │   │   ├── dashboard/              # Dashboard widgets
│   │   │   ├── charts/                 # Chart components
│   │   │   ├── forms/                  # Form components
│   │   │   ├── modals/                 # Modal dialogs
│   │   │   ├── navigation/             # Navbar/Sidebar
│   │   │   ├── ui/                     # Generic UI
│   │   │   └── common/                 # Loading/Error states
│   │   ├── services/                   # API services
│   │   │   ├── api.ts                  # Fetch wrapper
│   │   │   ├── auth.ts                 # Auth API
│   │   │   ├── attendance.ts           # Attendance API
│   │   │   ├── student.ts              # Student API
│   │   │   ├── professor.ts            # Professor API
│   │   │   ├── course.ts               # Course API
│   │   │   ├── report.ts               # Reports API
│   │   │   ├── session.ts              # Session API
│   │   │   ├── gps.ts                  # GPS helpers
│   │   │   └── qr.ts                   # QR helpers
│   │   ├── stores/                     # Global stores
│   │   ├── offline/                    # IndexedDB & sync logic
│   │   ├── validators/                 # Zod validators
│   │   ├── constants/                  # Roles, routes, status
│   │   ├── types/                      # TypeScript models
│   │   ├── utils/                      # Shared utilities
│   │   └── server/
│   │       ├── auth.ts                 # Server auth helpers
│   │       ├── cookies.ts              # Cookie helpers
│   │       ├── permissions.ts          # RBAC utilities
│   │       └── session.ts              # Server session utilities
│
├── static/
│   ├── icons/                          # PWA icons
│   ├── images/                         # Images & logos
│   ├── fonts/                          # Custom fonts
│   ├── manifest.json                   # PWA manifest
│   ├── robots.txt                      # Robots rules
│   └── favicon.png                     # Website icon
```
