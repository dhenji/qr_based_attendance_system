<script lang="ts">
	import { onMount } from 'svelte';

	// Install prompt for the Attendly PWA (static/manifest.webmanifest).
	// Chromium fires beforeinstallprompt, which we defer until the user taps
	// Install; iOS Safari fires nothing, so iPhones/iPads get the manual
	// Share → Add to Home Screen hint instead. Dismissal snoozes for 7 days
	// per device (localStorage); installed (standalone) devices never see it.

	type DeferredPrompt = Event & {
		prompt: () => Promise<void>;
		userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
	};

	const DISMISS_KEY = 'attendly-install-dismissed';
	const SNOOZE_MS = 7 * 24 * 60 * 60 * 1000;

	let deferredPrompt = $state<DeferredPrompt | null>(null);
	let dismissed = $state(true);
	let isStandalone = $state(false);
	let isIos = $state(false);

	const visible = $derived(!dismissed && !isStandalone && (deferredPrompt !== null || isIos));

	onMount(() => {
		isStandalone =
			window.matchMedia('(display-mode: standalone)').matches ||
			(window.navigator as Navigator & { standalone?: boolean }).standalone === true;
		isIos = /iphone|ipad|ipod/i.test(window.navigator.userAgent);
		try {
			dismissed = Number(window.localStorage.getItem(DISMISS_KEY) ?? 0) > Date.now();
		} catch {
			dismissed = false;
		}
		const handler = (event: Event) => {
			event.preventDefault();
			deferredPrompt = event as DeferredPrompt;
		};
		window.addEventListener('beforeinstallprompt', handler);
		return () => {
			window.removeEventListener('beforeinstallprompt', handler);
		};
	});

	const snooze = () => {
		try {
			window.localStorage.setItem(DISMISS_KEY, String(Date.now() + SNOOZE_MS));
		} catch {
			// Private mode: dismissal lasts for this page load only.
		}
		dismissed = true;
	};

	const install = async () => {
		if (!deferredPrompt) return;
		try {
			await deferredPrompt.prompt();
			await deferredPrompt.userChoice;
		} catch {
			// Prompt dismissed by the browser; snooze either way.
		}
		deferredPrompt = null;
		snooze();
	};
</script>

{#if visible}
	<div class="install-banner" role="region" aria-label="Install Attendly">
		<img src="/qr-attend-logo.svg" alt="" class="install-icon" aria-hidden="true" />
		<div class="install-text">
			<strong>Install Attendly</strong>
			{#if deferredPrompt}
				<span>Add attendance scanning to your home screen.</span>
			{:else}
				<span>Tap Share, then “Add to Home Screen”.</span>
			{/if}
		</div>
		{#if deferredPrompt}
			<button class="install-btn" type="button" onclick={() => void install()}>Install</button>
		{/if}
		<button class="install-dismiss" type="button" onclick={snooze} aria-label="Dismiss install prompt">
			✕
		</button>
	</div>
{/if}

<style>
	.install-banner {
		position: fixed;
		left: 1rem;
		right: 1rem;
		bottom: 1rem;
		z-index: 60;
		display: flex;
		align-items: center;
		gap: 0.75rem;
		background: var(--brand);
		color: var(--on-brand);
		border-radius: 12px;
		padding: 0.75rem 1rem;
		box-shadow: var(--shadow-lg);
		font-family: system-ui, sans-serif;
	}

	.install-icon {
		width: 2.5rem;
		height: 2.5rem;
		flex-shrink: 0;
	}

	.install-text {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
		font-size: 0.875rem;
		min-width: 0;
	}

	.install-text span {
		color: color-mix(in srgb, var(--on-brand) 80%, transparent);
		font-size: 0.8125rem;
	}

	.install-btn {
		margin-left: auto;
		background: var(--bg-page);
		color: var(--brand);
		border: none;
		border-radius: 8px;
		padding: 0.5rem 1rem;
		font-family: inherit;
		font-size: 0.875rem;
		font-weight: 700;
		cursor: pointer;
		flex-shrink: 0;
	}

	.install-dismiss {
		background: none;
		border: none;
		color: color-mix(in srgb, var(--on-brand) 70%, transparent);
		font-size: 1rem;
		cursor: pointer;
		padding: 0.25rem;
		flex-shrink: 0;
	}
</style>
