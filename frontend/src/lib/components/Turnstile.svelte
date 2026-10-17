<script lang="ts" module>
	interface TurnstileRenderOptions {
		sitekey: string;
		callback?: (token: string) => void;
		'expired-callback'?: () => void;
		'error-callback'?: () => void;
		theme?: 'light' | 'dark' | 'auto';
	}

	interface TurnstileApi {
		render: (container: string | HTMLElement, options: TurnstileRenderOptions) => string;
		reset: (widgetId?: string) => void;
		remove: (widgetId?: string) => void;
	}

	// Turnstile script loader state, shared by every widget instance so the
	// Cloudflare script tag is added at most once per page lifetime.
	let scriptPromise: Promise<TurnstileApi | null> | null = null;
</script>

<script lang="ts">
	// Turnstile captcha widget (Cloudflare).
	//
	// Renders nothing when the site key is unset or the app runs in mock
	// mode — callers then submit a null token and the backend skips
	// verification when its own secret is empty. Parents read the token via
	// getToken() at submit time and call reset() after an `invalid_captcha`
	// rejection so the user gets a fresh challenge.
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import { isMockMode } from '$lib/api/client';

	const SITE_KEY = import.meta.env.PUBLIC_TURNSTILE_SITE_KEY as string | undefined;
	const SCRIPT_SRC = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';

	const enabled = browser && !isMockMode() && !!SITE_KEY;

	let container: HTMLDivElement | undefined = $state();
	let api: TurnstileApi | null = null;
	let widgetId: string | null = null;
	let token: string | null = $state(null);
	let loadError = $state(false);

	const readApi = (): TurnstileApi | null =>
		(window as unknown as { turnstile?: TurnstileApi }).turnstile ?? null;

	const loadScript = (): Promise<TurnstileApi | null> => {
		if (scriptPromise) return scriptPromise;
		scriptPromise = new Promise((resolve, reject) => {
			const existing = document.querySelector(`script[src="${SCRIPT_SRC}"]`);
			if (existing) {
				const ready = readApi();
				if (ready) {
					resolve(ready);
					return;
				}
				existing.addEventListener('load', () => resolve(readApi()), { once: true });
				existing.addEventListener('error', () => reject(new Error('Turnstile script failed to load')), {
					once: true,
				});
				return;
			}
			const tag = document.createElement('script');
			tag.src = SCRIPT_SRC;
			tag.async = true;
			tag.defer = true;
			tag.onload = () => resolve(readApi());
			tag.onerror = () => reject(new Error('Turnstile script failed to load'));
			document.head.appendChild(tag);
		});
		return scriptPromise;
	};

	onMount(() => {
		if (!enabled) return;
		let cancelled = false;
		void loadScript()
			.then((loaded) => {
				if (!loaded) {
					// Resolved-null load (script tag finished without exposing
					// the API): dropping the cached promise lets a later mount
					// retry instead of inheriting the failure forever.
					scriptPromise = null;
				}
				if (cancelled || !loaded || !container) {
					if (!cancelled) loadError = true;
					return;
				}
				api = loaded;
				widgetId = api.render(container, {
					sitekey: SITE_KEY as string,
					theme: 'auto',
					callback: (fresh) => {
						token = fresh;
					},
					'expired-callback': () => {
						token = null;
					},
					'error-callback': () => {
						token = null;
					},
				});
			})
			.catch((error: unknown) => {
				// Never cache a rejection — one CDN hiccup (brief offline,
				// blocked network) would otherwise keep every later widget
				// dead until a full page reload.
				scriptPromise = null;
				console.debug('[auth] Turnstile failed to load:', error);
				if (!cancelled) loadError = true;
			});
		return () => {
			cancelled = true;
			if (widgetId && api) {
				try {
					api.remove(widgetId);
				} catch (error: unknown) {
					console.debug('[auth] Turnstile teardown failed:', error);
				}
				widgetId = null;
				api = null;
			}
		};
	});

	// Token for the current challenge, or null when the widget is disabled,
	// unsolved, or expired. Single-use: the backend consumes it on verify.
	export function getToken(): string | null {
		return token;
	}

	// Drop the current token and present a fresh challenge (e.g. after the
	// backend rejects with `invalid_captcha`).
	export function reset(): void {
		token = null;
		if (widgetId && api) {
			try {
				api.reset(widgetId);
			} catch (error: unknown) {
				console.debug('[auth] Turnstile reset failed:', error);
			}
		}
	}
</script>

{#if enabled}
	<div class="turnstile-wrap">
		<div bind:this={container}></div>
		{#if loadError}
			<p class="turnstile-hint" role="status">
				Security check could not load. You can still continue — contact support if sign-in fails.
			</p>
		{/if}
	</div>
{/if}

<style>
	.turnstile-wrap {
		display: flex;
		flex-direction: column;
		align-items: center;
		margin: 0.75rem 0;
	}

	.turnstile-hint {
		color: var(--text-muted);
		font-size: 0.8125rem;
		margin: 0.5rem 0 0;
		text-align: center;
	}
</style>
