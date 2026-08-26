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
        filename.split(/[/\\]/).includes('node_modules') ? undefined : true
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

| Rune | Purpose |
|------|---------|
| `$state(value)` | Reactive local state |
| `$state.raw(value)` | Non-deep-reactive state (primitives, objects you mutate manually) |
| `$derived(expression)` | Computed value (replaces `$:` reactive declarations) |
| `$derived.by(fn)` | Derived with a function body |
| `$effect(() => ...)` | Side effect (replaces `$:` with side effects) |
| `$props()` | Component props (replaces `export let`) |
| `$bindable()` | Two-way binding props |
| `$inspect(value)` | Debug logging (dev only) |

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

## Adding Chart.js

D41 specifies Chart.js as the chart library. Install:

```bash
cd frontend
npm install chart.js
```

For the date adapter (required for time axes):

```bash
npm install chartjs-adapter-date-fns date-fns
```

Usage in components:

```svelte
<script lang="ts">
    import Chart from 'chart.js/auto';
    import 'chartjs-adapter-date-fns';

    let canvas: HTMLCanvasElement;

    $effect(() => {
        const chart = new Chart(canvas, {
            type: 'bar',
            data: { /* ... */ },
            options: { responsive: true }
        });

        return () => chart.destroy();
    });
</script>

<canvas bind:this={canvas}></canvas>
```

---

## Service Worker Development

The PWA service worker (`src/service-worker.ts`) is planned but not yet installed. When ready:

```bash
npm install -D vite-plugin-pwa
```

Add to `vite.config.ts`:

```ts
import { VitePWA } from 'vite-plugin-pwa';

// Inside plugins array, after sveltekit():
VitePWA({
    registerType: 'autoUpdate',
    workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}']
    }
})
```

**Dev tips for service workers:**

- Service workers are **not active** during `vite dev` by default — they only activate on `npm run build && npm run preview`.
- To test offline behavior: `npm run build && npm run preview`, then use Chrome DevTools > Application > Service Workers.
- Use Chrome DevTools > Network > "Offline" checkbox to simulate offline.
- Service worker updates are cached — use "Update on reload" in DevTools during development.
- Background sync is browser-dependent — test on real devices.

---

## Mock Service Pattern

The planned feature-slice structure uses mock services for frontend development without a live backend.

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
import type { Program } from './schema';

export const mockPrograms: Program[] = [
    {
        id: 1,
        code: 'BSCS',
        name: 'Bachelor of Science in Computer Science',
        total_years: 4,
        is_active: true
    },
    {
        id: 2,
        code: 'BSIT',
        name: 'Bachelor of Science in Information Technology',
        total_years: 4,
        is_active: true
    }
];
```

### Conditional mock/real switching

```ts
// src/lib/features/program/service.ts
import { PUBLIC_API_URL } from '$env/static/public';
import { mockPrograms } from './mock';
import type { Program } from './schema';

const USE_MOCK = import.meta.env.DEV && !PUBLIC_API_URL;

export async function getPrograms(): Promise<Program[]> {
    if (USE_MOCK) {
        return mockPrograms;
    }

    const res = await fetch(`${PUBLIC_API_URL}/admin/programs`);
    if (!res.ok) throw new Error('Failed to fetch programs');
    return res.json();
}
```

Or use an environment variable:

```ts
const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true';
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

## Useful Commands

| Command | Purpose |
|---------|---------|
| `npm run dev` | Start dev server (hot reload) |
| `npm run build` | Production build |
| `npm run preview` | Preview production build locally |
| `npm run check` | Typecheck all Svelte + TS files |
| `npm run check:watch` | Typecheck in watch mode |

---

## Key Dependencies

| Package | Purpose |
|---------|---------|
| `@sveltejs/kit` | SvelteKit framework |
| `svelte` | Svelte 5 (runes) |
| `html5-qrcode` | QR code scanning |
| `zod` | Schema validation |
| `chart.js` | Charts (D41 — install when needed) |
| `chartjs-adapter-date-fns` | Chart.js time axis adapter |
