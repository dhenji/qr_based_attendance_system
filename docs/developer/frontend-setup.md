# Frontend Setup Guide

> SvelteKit 2 + Svelte 5 (runes mode). Prerequisites: Node 20+, npm 10+.

---

## Quick Start

```bash
cd frontend
npm install
cp .env.example .env      # only PUBLIC_* vars reach the browser
npm run dev               # http://localhost:5173
```

---

## Docker Development (with HMR)

When using Docker Compose (`docker compose -f docker-compose.dev.yml up --build`), the frontend runs inside a container with hot-reload enabled via polling.

**How it works:**

- `./frontend/src` is mounted into the container at `/app/src`
- `CHOKIDAR_USEPOLLING=1` and `CHOKIDAR_INTERVAL=1000` are set in `docker-compose.dev.yml` — this makes Vite's file watcher use polling instead of `inotify`, which is unreliable through Docker volume mounts on Linux
- Changes to files in `src/` are detected automatically and hot-reloaded in the browser — **no manual page refresh needed**

**What auto-reloads (HMR — no refresh required):**

- Svelte component edits (template, script, style)
- TypeScript/JS changes in `src/lib/`
- CSS/style changes

**What may require a manual refresh:**

- Changes to `svelte.config.js` or `vite.config.ts`
- Changes to the app entry point (`+layout.svelte`, root `+page.svelte`)
- Adding or removing dependencies in `package.json`

**Note:** The polling approach uses slightly more CPU than native `inotify`, but is necessary for reliable file watching in Docker. This is a development-only concern and does not affect production.

---

## Node Engine Strict

`.npmrc` sets `engine-strict=true`. If `npm install` fails with an engine mismatch:

```bash
node --version    # must satisfy package.json engine ranges
npm --version
```

If your Node version doesn't satisfy the range, upgrade Node or temporarily set `engine-strict=false` in `.npmrc` (not recommended for CI).

---

## Svelte 5 Runes Mode

This project forces runes mode globally via `vite.config.ts`:

```ts
compilerOptions: {
  runes: ({ filename }) =>
    filename.split(/[/\\]/).includes("node_modules") ? undefined : true;
}
```

**All components MUST use runes syntax:**

```svelte
<!-- CORRECT (runes) -->
<script lang="ts">
    let count = $state(0);
    let doubled = $derived(count * 2);

    $effect(() => {
        console.log(count);
    });
</script>

<!-- WRONG (legacy — will error) -->
<script lang="ts">
    let count = 0;
    $: doubled = count * 2;
    $: console.log(count);
</script>
```

**Key runes to use:**

| Rune                   | Purpose                                                           |
| ---------------------- | ----------------------------------------------------------------- |
| `$state(value)`        | Reactive local state                                              |
| `$state.raw(value)`    | Non-deep-reactive state (primitives, objects you mutate manually) |
| `$derived(expression)` | Computed value (replaces `$:` reactive declarations)              |
| `$derived.by(fn)`      | Derived with a function body                                      |
| `$effect(() => ...)`   | Side effect (replaces `$:` with side effects)                     |
| `$props()`             | Component props (replaces `export let`)                           |
| `$bindable()`          | Two-way binding props                                             |
| `$inspect(value)`      | Debug logging (dev only)                                          |

**Props pattern:**

```svelte
<script lang="ts">
    interface Props {
        title: string;
        count?: number;
        onsubmit: (value: string) => void;
    }

    let { title, count = 0, onsubmit }: Props = $props();
</script>
```

---

## Charts

There is **no chart library**. D41 specified Chart.js, but it was never installed —
the charts are hand-rolled SVG (ADR-091). Two reusable components cover the whole
chart surface:

| Component                                                | Shape              |
| -------------------------------------------------------- | ------------------ |
| `src/lib/features/report/components/ReportTrendChart.svelte` | Line / area trend  |
| `src/lib/features/report/components/ReportBarChart.svelte`   | Bar / comparison   |

Both take plain arrays of `{label, value}`-style rows and draw SVG primitives —
no canvas, no runtime, no dependency. To add a chart, follow the prop contract of
the existing components rather than reaching for a library.

---

## Service Worker

The PWA offline stack **ships**: `src/service-worker.ts` (SvelteKit's service
worker — SvelteKit registers it automatically in a production build, and the
worker itself is production-only by design) and the local outbox under
`src/lib/features/sync/`. The worker precaches the app shell and relays
Background Sync `attendly-outbox` wake-ups to open pages; it never replays scans
itself, because the auth token lives in `localStorage` which a worker cannot
read.

What is still deferred is the `vite-plugin-pwa` route (the install prompt and
its manifest generation). If it is picked up later:

```bash
npm install -D vite-plugin-pwa
```

Add to `vite.config.ts`:

```ts
import { VitePWA } from "vite-plugin-pwa";

// Inside plugins array, after sveltekit():
VitePWA({
  registerType: "autoUpdate",
  workbox: {
    globPatterns: ["**/*.{js,css,html,ico,png,svg,woff2}"],
  },
});
```

**Dev tips for service workers:**

- Service workers are **not active** during `vite dev` by default — they only activate on `npm run build && npm run preview`.
- To test offline behavior: `npm run build && npm run preview`, then use Chrome DevTools > Application > Service Workers.
- Use Chrome DevTools > Network > "Offline" checkbox to simulate offline.
- Service worker updates are cached — use "Update on reload" in DevTools during development.
- Background sync is browser-dependent — test on real devices.

---

## Mock Service Pattern

The feature-slice structure (under `src/lib/features/`) uses mock services for
frontend development without a live backend.

> **Canonical mock toggle:** the global switch is `MOCK = true` in
> `src/lib/api/client.ts` (mock data comes from `src/lib/api/endpoints.ts`).
> The per-service fallback pattern below is how individual services can also
> short-circuit in dev when `PUBLIC_API_URL` is unset.

### Directory pattern per feature

```
src/lib/features/{feature}/
├── store.svelte.ts      # $state runes store
├── service.ts           # Real API calls
├── schema.ts            # Zod validation schemas
├── mock.ts              # Mock data for dev
└── components/          # Svelte components
```

### Creating a mock service

```ts
// src/lib/features/program/mock.ts
import type { Program } from "./schema";

export const mockPrograms: Program[] = [
  {
    id: 1,
    code: "BSCS",
    name: "Bachelor of Science in Computer Science",
    total_years: 4,
    is_active: true,
  },
  {
    id: 2,
    code: "BSIT",
    name: "Bachelor of Science in Information Technology",
    total_years: 4,
    is_active: true,
  },
];
```

### Conditional mock/real switching

```ts
// src/lib/features/program/service.ts
import { PUBLIC_API_URL } from "$env/static/public";
import { mockPrograms } from "./mock";
import type { Program } from "./schema";

const USE_MOCK = import.meta.env.DEV && !PUBLIC_API_URL;

export async function getPrograms(): Promise<Program[]> {
  if (USE_MOCK) {
    return mockPrograms;
  }

  const res = await fetch(`${PUBLIC_API_URL}/admin/programs`);
  if (!res.ok) throw new Error("Failed to fetch programs");
  return res.json();
}
```

Or use an environment variable:

```ts
const USE_MOCK = import.meta.env.VITE_USE_MOCK === "true";
```

Add to `.env`:

```bash
VITE_USE_MOCK=true
```

---

## Type Checking

```bash
cd frontend
npm run check
```

This runs `svelte-kit sync` (generates `.svelte-kit/`) then `svelte-check`. The `.svelte-kit/` directory is gitignored — it is regenerated on every check.

### Watch mode

```bash
npm run check:watch
```

---

## Testing

Frontend unit/component tests use **Vitest 5** + **@testing-library/svelte** + **jsdom**,
configured in `vite.config.ts` (`environment: 'jsdom'`, setup file
`src/test-setup.ts`, v8 coverage with thresholds 11/7/5/13). Tests are co-located
as `*.test.ts` next to the source they cover; shared helpers (e.g. `ModalWrapper.svelte`)
live in `src/testing/`. Vitest imports are explicit (no `globals: true`).

```bash
cd frontend
npm run test            # single run
npm run test:watch      # watch mode
npm run test:coverage   # with v8 coverage -> ./coverage (lcov + text)
```

Coverage is reported to `frontend/coverage/` (gitignored) and uploaded as the
`frontend-coverage` artifact in CI.

## Useful Commands

| Command               | Purpose                          |
| --------------------- | -------------------------------- |
| `npm run dev`         | Start dev server (hot reload)    |
| `npm run build`       | Production build                 |
| `npm run preview`     | Preview production build locally |
| `npm run check`       | Typecheck all Svelte + TS files  |
| `npm run check:watch` | Typecheck in watch mode          |
| `npm run test`        | Run Vitest unit/component tests  |
| `npm run test:watch`  | Vitest in watch mode             |
| `npm run test:coverage` | Vitest with v8 coverage        |

---

## Key Dependencies

| Package                    | Purpose                            |
| -------------------------- | ---------------------------------- |
| `@sveltejs/kit`            | SvelteKit framework                |
| `svelte`                   | Svelte 5 (runes)                   |
| `html5-qrcode`             | QR code scanning                   |
| `zod`                      | Schema validation                  |
| `@mediapipe/tasks-vision`  | FaceLandmarker WASM runtime + model (the only ML model in the project) |
| `vitest`                   | Unit/component test runner |
| `@testing-library/svelte`  | Svelte component testing utilities |
| `@testing-library/jest-dom` | DOM matchers for Vitest |
| `jsdom`                    | DOM environment for Vitest |
| `@vitest/coverage-v8`      | V8 coverage provider |

## Module-level readiness flags

Feature services (e.g. `session/service.ts`) may cache warmed data behind a
module-level flag (`coursesReady`). These flags must be invalidated on
login/logout/account-switch together with the runes store resets, otherwise
stale or empty identity leaks between accounts. See
`invalidateCourseCache()` and its callers in `features/auth/store.svelte.ts`.
