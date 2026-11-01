import adapter from '@sveltejs/adapter-auto';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';
import { visualizer } from 'rollup-plugin-visualizer';
import { svelteTesting } from '@testing-library/svelte/vite';

// Optional later upgrade to full offline precaching:
//   npm i -D vite-plugin-pwa
// and add VitePWA() here + a post-build script (see docs/architecture/frontend-architecture.md).
export default defineConfig({
	// api/client.ts reads import.meta.env.PUBLIC_API_URL / PUBLIC_MOCK_MODE.
	// Vite only exposes VITE_* to the browser by default, so without this the
	// PUBLIC_* values never reach the bundle and mock mode can never engage.
	envPrefix: ['VITE_', 'PUBLIC_'],
	build: {
		rollupOptions: {
			output: {
				manualChunks(id) {
					if (id.includes('node_modules/@mediapipe/tasks-vision')) return 'mediapipe';
					if (id.includes('node_modules/html5-qrcode')) return 'html5qrcode';
					if (id.includes('node_modules/leaflet')) return 'leaflet';
					if (id.includes('node_modules/qrcode')) return 'qrcode';
					if (id.includes('node_modules/zod')) return 'zod';
					return undefined;
				}
			}
		}
	},
	plugins: [
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},

			// adapter-auto only supports some environments, see https://svelte.dev/docs/kit/adapter-auto for a list.
			// If your environment is not supported, or you settled on a specific environment, switch out the adapter.
			// See https://svelte.dev/docs/kit/adapters for more information about adapters.
			adapter: adapter()
		}),
		process.env.ANALYZE === 'true'
			? visualizer({ filename: 'stats.html', gzipSize: true, brotliSize: true })
			: null,
		svelteTesting()
	].filter(Boolean) as any,
	test: {
		environment: 'jsdom',
		setupFiles: ['./src/test-setup.ts'],
		coverage: {
			provider: 'v8',
			reporter: ['text', 'lcov'],
			reportsDirectory: './coverage',
			include: ['src/lib/**/*.{ts,svelte}'],
			exclude: ['**/*.test.ts', '**/*.spec.ts', 'src/test-setup.ts'],
			thresholds: {
				statements: 11,
				branches: 7,
				functions: 5,
				lines: 13
			}
		}
	}
});