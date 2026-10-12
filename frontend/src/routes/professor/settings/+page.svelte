<script lang="ts">
	import { onMount } from 'svelte';
	import { authState } from '$lib/features/auth/store.svelte';
	import MfaSettings from '$lib/components/MfaSettings.svelte';
	import { SECURITY_QUESTIONS } from '$lib/features/auth/security';
	import { setSecurityQuestion } from '$lib/features/auth/service';
	import { Routes } from '$lib/shared/constants/routes';
	import {
		DEFAULT_PREFS,
		getPrefs,
		savePrefs,
		type SettingsPrefs,
	} from '$lib/features/settings/service';
	import { applyTheme, setTheme as persistTheme } from '$lib/features/settings/theme';
	import { requestNotificationPermission } from '$lib/features/notifications/poll';

	const prefs = $state<SettingsPrefs>({ ...DEFAULT_PREFS });

	onMount(() => {
		const loaded = getPrefs();
		Object.assign(prefs, loaded);
		applyTheme(loaded.theme);
	});

	function setTheme(theme: 'light' | 'dark') {
		prefs.theme = theme;
		persistTheme(theme);
	}

	function flip<K extends 'pushNotifications' | 'emailNotifications' | 'shareGps' | 'cameraScanning'>(key: K) {
		prefs[key] = !prefs[key];
		savePrefs({ ...prefs });
		if (key === 'pushNotifications' && prefs[key]) {
			// Opting in unlocks OS toasts on new queue arrivals (in-app pill
			// works regardless). A denied permission reverts the toggle so the
			// switch never promises what the OS blocks.
			void requestNotificationPermission().then((permission) => {
				if (permission === 'denied') {
					prefs.pushNotifications = false;
					savePrefs({ ...prefs });
					pushNote = 'Browser notifications are blocked — enable them in the browser site settings first.';
				} else {
					pushNote = null;
				}
			});
		}
	}

	let pushNote = $state<string | null>(null);

	// Change Password goes through the shared forgot-password recovery wizard
	// (email → security question → emailed OTP code → strong new password),
	// the same process as the student settings page.

	// Security Question — live on POST /auth/security-question. The server
	// is the source of truth (GET /auth/me security_question_set); nothing
	// is mirrored to localStorage.
	let questionOpen = $state(false);
	let questionBusy = $state(false);
	// Server truth (GET /auth/me security_question_set), flipped locally on
	// save so the label updates without a session round-trip.
	const hasQuestion = $derived(authState.user?.securityQuestionSet === true);
	let question = $state('');
	let answer = $state('');
	let securityError = $state('');
	let securityMsg = $state('');

	async function onSaveQuestion() {
		securityError = '';
		securityMsg = '';
		if (!question) {
			securityError = 'Please choose a security question';
			return;
		}
		if (!answer.trim()) {
			securityError = 'Security answer is required';
			return;
		}
		questionBusy = true;
		try {
			await setSecurityQuestion(question, answer.trim());
			if (authState.user) authState.user.securityQuestionSet = true;
			securityMsg = 'Security question saved.';
			questionOpen = false;
			answer = '';
		} catch (e: unknown) {
			securityError = e instanceof Error && e.message ? e.message : 'Save failed. Please try again.';
		} finally {
			questionBusy = false;
		}
	}
</script>

<div class="wrap">
	<header class="header">
		<h1>Settings</h1>
		<p class="muted">Preferences are stored on this device.</p>
	</header>

	<section class="card">
		<h2 class="section-title">Appearance</h2>
		<div class="row">
			<span class="row-label">Theme</span>
			<div class="segmented">
				<button class="segment" class:active={prefs.theme === 'light'} onclick={() => setTheme('light')}>
					Light
				</button>
				<button class="segment" class:active={prefs.theme === 'dark'} onclick={() => setTheme('dark')}>
					Dark
				</button>
			</div>
		</div>
		<p class="muted note">Applies instantly across the app and is remembered on this device.</p>
	</section>

	<section class="card">
		<h2 class="section-title">Notifications</h2>
		<label class="switch-row">
			<span class="row-label">Push notifications</span>
			<span class="switch">
				<input type="checkbox" checked={prefs.pushNotifications} onchange={() => flip('pushNotifications')} />
				<span class="slider"></span>
			</span>
		</label>
		<label class="switch-row">
			<span class="row-label">Email notifications</span>
			<span class="switch">
				<input type="checkbox" checked={prefs.emailNotifications} onchange={() => flip('emailNotifications')} />
				<span class="slider"></span>
			</span>
		</label>
		{#if pushNote}
			<p class="muted note" role="status">{pushNote}</p>
		{/if}
		<p class="muted note">OS toasts only appear while the app is open — no background push.</p>
	</section>

	<section class="card">
		<h2 class="section-title">Privacy</h2>
		<label class="switch-row">
			<span class="row-label">Share GPS for attendance</span>
			<span class="switch">
				<input type="checkbox" checked={prefs.shareGps} onchange={() => flip('shareGps')} />
				<span class="slider"></span>
			</span>
		</label>
		<label class="switch-row">
			<span class="row-label">Enable camera scanning</span>
			<span class="switch">
				<input type="checkbox" checked={prefs.cameraScanning} onchange={() => flip('cameraScanning')} />
				<span class="slider"></span>
			</span>
		</label>
	</section>

	<section class="card">
		<h2 class="section-title">Security</h2>

		<h3 class="sub-title">Change Password</h3>
		<a class="btn" href={Routes.FORGOT_PASSWORD}>Change Password</a>

		<hr class="divider" />

		<MfaSettings />

		<hr class="divider" />

		<h3 class="sub-title">Security Question</h3>
		{#if hasQuestion}
			<p class="muted">Current: Set</p>
		{/if}
		{#if !questionOpen}
			<button class="btn ghost" onclick={() => (questionOpen = true)}>
				{hasQuestion ? 'Change Security Question' : 'Set Security Question'}
			</button>
			{#if securityMsg && !questionOpen}<p class="success">{securityMsg}</p>{/if}
		{:else}
			<div class="field">
				<label for="security-question">Question</label>
				<select id="security-question" bind:value={question}>
					<option value="" disabled>Choose a question…</option>
					{#each SECURITY_QUESTIONS as q (q)}
						<option value={q}>{q}</option>
					{/each}
				</select>
			</div>
			<div class="field">
				<label for="security-answer">Answer</label>
				<input id="security-answer" bind:value={answer} placeholder="Your answer" />
			</div>
			{#if securityError}<p class="error">{securityError}</p>{/if}
			<div class="action-row">
				<button class="btn" onclick={onSaveQuestion} disabled={questionBusy}>
					{questionBusy ? 'Saving…' : 'Save'}
				</button>
				<button class="btn ghost" onclick={() => (questionOpen = false)}>Cancel</button>
			</div>
		{/if}
	</section>

	<p class="meta muted">App version: 1.0.0</p>
</div>

<style>
	.wrap {
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
		max-width: 720px;
		margin-inline: auto;
		font-family: system-ui, sans-serif;
	}

	.header h1 {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.625rem;
		font-weight: 700;
		color: var(--text);
		margin: 0 0 0.25rem;
	}

	.muted {
		color: var(--text-muted);
		font-size: 0.875rem;
		margin: 0;
	}

	.note {
		font-size: 0.8125rem;
		margin-top: 0.75rem;
	}

	.card {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 1.5rem;
		box-shadow: var(--shadow-sm);
	}

	.section-title {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.0625rem;
		font-weight: 700;
		color: var(--text);
		margin: 0 0 1rem;
	}

	.sub-title {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 0.9375rem;
		font-weight: 700;
		color: var(--text-secondary);
		margin: 0 0 0.75rem;
	}

	.row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		flex-wrap: wrap;
	}

	.row-label {
		font-size: 0.9375rem;
		color: var(--text-secondary);
	}

	.segmented {
		display: inline-flex;
		border: 1px solid var(--border);
		border-radius: 8px;
		overflow: hidden;
	}

	.segment {
		border: none;
		background: var(--bg-card);
		color: var(--text-muted);
		padding: 0.5rem 1rem;
		font-size: 0.875rem;
		font-weight: 600;
		font-family: system-ui, sans-serif;
		cursor: pointer;
	}

	.segment.active {
		background: var(--brand);
		color: var(--on-brand);
	}

	.switch-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		cursor: pointer;
	}

	.switch-row + .switch-row {
		margin-top: 0.75rem;
	}

	.switch {
		position: relative;
		display: inline-block;
		width: 42px;
		height: 24px;
		flex-shrink: 0;
	}

	.switch input {
		opacity: 0;
		width: 0;
		height: 0;
	}

	.slider {
		position: absolute;
		inset: 0;
		background: var(--border-strong);
		border-radius: 999px;
		transition: background 0.15s ease;
	}

	.slider::before {
		content: '';
		position: absolute;
		width: 18px;
		height: 18px;
		left: 3px;
		top: 3px;
		background: var(--bg-card);
		border-radius: 50%;
		transition: transform 0.15s ease;
	}

	.switch input:checked + .slider {
		background: var(--accent);
	}

	.switch input:checked + .slider::before {
		transform: translateX(18px);
	}

	.switch input:focus-visible + .slider {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.field {
		margin-bottom: 0.75rem;
	}

	.field label {
		display: block;
		font-size: 0.8125rem;
		font-weight: 700;
		color: var(--text-muted);
		margin-bottom: 0.375rem;
	}

	.field input,
	.field select {
		width: 100%;
		padding: 0.625rem 0.75rem;
		border: 1px solid var(--border);
		border-radius: 8px;
		background: var(--bg-card);
		color: var(--text-secondary);
		font-size: 0.9375rem;
		font-family: system-ui, sans-serif;
	}

	.field input:focus-visible,
	.field select:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: -1px;
	}

	.btn {
		display: inline-block;
		padding: 0.625rem 1.25rem;
		border: none;
		border-radius: 8px;
		background: var(--brand);
		color: var(--on-brand);
		font-size: 0.9375rem;
		font-weight: 700;
		font-family: system-ui, sans-serif;
		text-decoration: none;
		cursor: pointer;
		transition: background 0.15s ease, box-shadow 0.15s ease;
	}

	.btn:hover:not(:disabled) {
		background: var(--brand-hover);
	}

	.btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.btn.ghost {
		background: var(--bg-card);
		color: var(--brand);
		border: 1px solid var(--border-strong);
	}

	.btn.ghost:hover {
		background: var(--bg-page);
	}

	.divider {
		border: none;
		border-top: 1px solid var(--divider);
		margin: 1.25rem 0;
	}

	.action-row {
		display: flex;
		gap: 0.75rem;
	}

	.error {
		color: var(--danger);
		font-size: 0.875rem;
		margin: 0 0 0.75rem;
	}

	.success {
		color: var(--success);
		font-size: 0.875rem;
		margin: 0.75rem 0 0;
	}

	.meta {
		text-align: center;
		font-size: 0.8125rem;
	}
</style>
