# Frontend Architecture — QR Attendance System

> Canonical structure for `frontend/src/`. Replaces the earlier flat
> `services/ + stores/ + components/` layout with domain-driven **feature
> slices** that mirror `backend/features/` 1:1.

## Feature-Slice Convention

Each `features/*` folder owns its domain. Files are created only when
needed — no `.gitkeep` placeholders.

| File | Responsibility |
| ---- | -------------- |
| `store.svelte.ts` | Domain state — runes, `.svelte.ts` extension required |
| `service.ts` | API calls (mock or real, same interface — swappable) |
| `schema.ts` | Zod schemas for this domain |
| `mock.ts` | Fixtures / seed data |
| `bundle.ts` | Domain-specific builders (e.g. evidence bundles) |
| `types.ts` | Only if domain types aren't shared (usually in `shared/types`) |
| `components/` | Domain-specific Svelte components (only if needed) |

`features/{course,enrollment,analytics}` are documented but **not created
yet** — the mockup pass doesn't use them.

## Tree

```
frontend/
├── package.json · svelte.config.js · vite.config.ts · tsconfig.json
├── .npmrc · .env.example · .gitignore · README.md
├── static/
│   └── favicon.ico (robots.txt shown in docs; favicon.svg already in lib/assets)
│
└── src/
    ├── app.html                                  (unchanged)
    ├── app.d.ts                                  (unchanged)
    ├── hooks.client.ts                           (mockup)   # connectivity → offline store; sync trigger
    │
    ├── lib/
    │   ├── index.ts                              (mockup)   # barrel exports
    │   │
    │   ├── app/
    │   │   ├── session.svelte.ts                 (mockup)   # auth session, role switcher, guards
    │   │   └── offline.svelte.ts                 (mockup)   # online status + pending-sync queue
    │   │
    │   ├── api/
    │   │   ├── client.ts                         (mockup)   # fetch wrapper, error types, MOCK flag
    │   │   └── endpoints.ts                      (mockup)   # typed endpoint map (mirrors backend)
    │   │
    │   ├── features/
    │   │   ├── auth/                            # ───────── mockup ─────────
    │   │   │   ├── service.ts                    # mock login/register/logout
    │   │   │   ├── schema.ts                     # zod: login + register forms
    │   │   │   ├── mock.ts                       # demo users (student/prof/admin)
    │   │   │   └── components/
    │   │   │       ├── LoginForm.svelte
    │   │   │       └── RegisterForm.svelte
    │   │   │
    │   │   ├── student/                         # ───────── mockup ─────────
    │   │   │   ├── service.ts                    # profile, history, schedule
    │   │   │   ├── mock.ts                       # current student seed
    │   │   │   └── components/
    │   │   │       └── DashboardStats.svelte     # rate/today/total cards
    │   │   │
    │   │   ├── session/                         # ───────── mockup ─────────
    │   │   │   ├── store.svelte.ts               # active session state (professor view)
    │   │   │   ├── service.ts                    # open/close/list/history
    │   │   │   ├── schema.ts                     # zod: create-session form
    │   │   │   ├── mock.ts                       # sample sessions + live-feed stream
    │   │   │   └── components/
    │   │   │       ├── OpenSessionForm.svelte
    │   │   │       ├── SessionCodeCard.svelte    # projector-ready code + timer
    │   │   │       └── LiveFeedTable.svelte      # auto-refreshing scan table
    │   │   │
    │   │   ├── attendance/                      # ───────── mockup ─────────
    │   │   │   ├── store.svelte.ts               # today's records, recent activity
    │   │   │   ├── service.ts                    # submit evidence, list records
    │   │   │   ├── schema.ts                     # zod: evidence bundle
    │   │   │   └── mock.ts                       # seeded attendance (78% rate)
    │   │   │
    │   │   ├── liveness/                        # ───────── mockup ─────────
    │   │   │   ├── store.svelte.ts               # scan state machine (idle→qr→gps→face→done)
    │   │   │   ├── bundle.ts                     # evidence-bundle builder (nonce, timestamp, scores)
    │   │   │   ├── schema.ts                     # zod: evidence bundle validation
    │   │   │   └── components/
    │   │   │       ├── QRScanner.svelte          # real html5-qrcode camera scan
    │   │   │       ├── SessionCodeInput.svelte
    │   │   │       ├── GPSStatus.svelte          # GPS read + geofence pill
    │   │   │       ├── FaceChallenge.svelte      # challenge overlay (simulated pass)
    │   │   │       ├── PermissionPrompt.svelte   # camera/GPS permissions modal
    │   │   │       └── ScanResult.svelte         # success/failure overlay
    │   │   │
    │   │   ├── sync/                            # ───────── mockup ─────────
    │   │   │   ├── db.ts                         # IndexedDB wrapper (queue store)
    │   │   │   └── engine.ts                     # enqueue/dequeue, retry, status transitions
    │   │   │
    │   │   ├── course/  ○                        (deferred — empty until backend)
    │   │   ├── enrollment/ ○                     (deferred)
    │   │   └── analytics/ ○                      (deferred)
    │   │
    │   └── shared/
    │       ├── styles/
    │       │   └── tokens.css                    (mockup)   # palette, spacing, radius, status colors
    │       ├── ui/                               (mockup)
    │       │   ├── Button.svelte · Card.svelte · Input.svelte · Select.svelte
    │       │   ├── Toggle.svelte · Table.svelte · Badge.svelte
    │       │   ├── Modal.svelte · EmptyState.svelte
    │       ├── components/                       (mockup)
    │       │   ├── Sidebar.svelte · Topbar.svelte
    │       │   ├── StatusBadge.svelte · OfflineBanner.svelte
    │       ├── utils/                            (mockup)
    │       │   ├── geo.ts                        # haversine + geofence check
    │       │   ├── format.ts                     # date/time/percent
    │       │   ├── gen.ts                        # fake-id/name generation for fixtures
    │       │   └── qr.ts                         # html5-qrcode init helpers
    │       ├── constants/                        (mockup)
    │       │   ├── roles.ts · routes.ts · status.ts
    │       ├── types/                            (mockup)
    │       │   ├── user.ts · student.ts · course.ts · enrollment.ts
    │       │   ├── session.ts · attendance.ts · liveness.ts · sync.ts
    │       │   └── index.ts                      # barrel
    │       └── validators/                       (mockup)
    │           └── base.ts                       # shared zod bits (email, id, password strength)
    │
    └── routes/
        ├── +layout.svelte                        (mockup)   # tokens import, OfflineBanner, Topbar
        ├── +page.svelte                          (mockup)   # landing + role switcher
        │
        ├── (auth)/
        │   ├── +layout.svelte                    (mockup)
        │   ├── login/+page.svelte                (mockup)
        │   ├── register/+page.svelte             (mockup)
        │   ├── forgot-password/+page.svelte      (stub)
        │   └── reset-password/+page.svelte       (stub)
        │
        ├── (student)/
        │   ├── +layout.svelte                    (mockup)   # sidebar shell
        │   ├── dashboard/+page.svelte            (mockup)
        │   ├── scan/+page.svelte                 (mockup)   # the centerpiece flow
        │   ├── history/+page.svelte              (mockup)
        │   ├── schedule/+page.svelte             (stub)
        │   ├── profile/+page.svelte              (stub)
        │   └── settings/+page.svelte             (stub)
        │
        ├── (professor)/
        │   ├── +layout.svelte                    (mockup)   # sidebar shell
        │   ├── dashboard/+page.svelte            (mockup)
        │   ├── sessions/
        │   │   ├── +page.svelte                  (stub)     # overview
        │   │   ├── create/+page.svelte           (mockup)
        │   │   ├── active/[id]/+page.svelte      (mockup)   # projector mode + live feed
        │   │   └── history/+page.svelte          (stub)
        │   ├── attendance/+page.svelte           (mockup)   # records list + filters
        │   ├── reports/+page.svelte              (stub)
        │   └── courses/+page.svelte              (stub)
        │
        └── (admin)/
            ├── +layout.svelte                    (mockup)   # sidebar shell
            ├── dashboard/+page.svelte            (stub)
            ├── students/+page.svelte             (mockup)   # table + CSV import modal + edit
            ├── courses/+page.svelte              (stub)
            ├── reports/+page.svelte              (stub)
            └── system/+page.svelte               (stub)
```

## Key Rules

- **Routes are thin glue** over features — no business logic in `.svelte` pages
- **`api/` sits above features** — transport is shared infra; features depend on `$lib/api`, never the reverse
- **`app/` vs `features/`** — app-wide state created once (session/offline); domain state lives in feature stores
- **`shared/ui` = dumb primitives · `shared/components` = app-aware composites** (Sidebar needs session state, Button doesn't)
- **Runes only** — `$state`/`$props`, never legacy reactive declarations
- **Mock-first** — services implement a typed contract, `MOCK` flag in `api/client.ts`; swap to real fetch when backend endpoints land

## Deferred (later passes)

`hooks.server.ts` · `service-worker.ts` · `static/icons/` · `vite-plugin-pwa` · `robots.txt`