import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

// Optional later upgrade to full offline precaching:
//   npm i -D vite-plugin-pwa
// and add VitePWA() here + a post-build script (see docs/architecture/frontend-architecture.md).
export default defineConfig({
	plugins: [sveltekit()]
});
