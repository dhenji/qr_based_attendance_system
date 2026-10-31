<script lang="ts">
	import SkeletonDetail from '$lib/components/SkeletonDetail.svelte';
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { me, setSecurityQuestion } from '$lib/features/auth/service';
	import MfaSettings from '$lib/components/MfaSettings.svelte';
	import { SECURITY_QUESTIONS } from '$lib/features/auth/security';
	import {
		authState,
		doChangePassword,
		isAdmin,
		isSuperAdmin,
		restoreSession,
	} from '$lib/features/auth/store.svelte';
	import {
		DEFAULT_PREFS,
		getPrefs,
		type SettingsPrefs,
	} from '$lib/features/settings/service';
	import { applyTheme, setTheme as persistTheme } from '$lib/features/settings/theme';
	import type { MeResponse } from '$lib/shared/types';
	import { Routes } from '$lib/shared/constants/routes';
	import { evaluatePassword, isPasswordStrong } from '$lib/shared/utils/password';

	// Admin Profile (wireframe 4.11): identity is read-only (admins are
	// model-less — no roster row owns the names), sourced from GET /auth/me.
	// Password change is live on POST /auth/change-password. Gated on
	// isAdmin() like the rest of the portal shell.

	let identity = $state<MeResponse | null>(null);
	let loading = $state(true);
	let loadError = $state<string | null>(null);

	// Device-local display prefs — same storage and helper as the student and
	// professor Settings pages. Theme never leaves the browser.
	const prefs = $state<SettingsPrefs>({ ...DEFAULT_PREFS });

	function setTheme(theme: 'light' | 'dark') {
		prefs.theme = theme;
		persistTheme(theme);
	}

	let currentPassword = $state('');
	let newPassword = $state('');
	let confirmPassword = $state('');
	let formError = $state<string | null>(null);
	let formOk = $state<string | null>(null);
	let formBusy = $state(false);

	// Security Question — only for non-super-admin admins; mirrors student/professor.
	let questionOpen = $state(false);
	let questionBusy = $state(false);
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

	const displayName = $derived(
		[identity?.first_name, identity?.last_name].filter(Boolean).join(' ') || 'Admin'
	);

	const passwordReq = $derived(evaluatePassword(newPassword));
	const passwordOk = $derived(isPasswordStrong(passwordReq));
	const passwordsMatch = $derived(newPassword === confirmPassword);

	onMount(async () => {
		const loaded = getPrefs();
		Object.assign(prefs, loaded);
		applyTheme(loaded.theme);

		const user = await restoreSession();
		if (!user || !isAdmin()) {
			await goto(Routes.HOME);
			return;
		}
		try {
			identity = await me();
		} catch (e: unknown) {
			loadError = e instanceof Error && e.message ? e.message : 'Could not load profile.';
		} finally {
			loading = false;
		}
	});

	const submitPassword = async (event: SubmitEvent) => {
		event.preventDefault();
		formError = null;
		formOk = null;
		if (!currentPassword) {
			formError = 'Enter your current password.';
			return;
		}
		if (!passwordOk) {
			formError = 'New password does not meet all requirements.';
			return;
		}
		if (!passwordsMatch) {
			formError = 'Passwords do not match.';
			return;
		}
		formBusy = true;
		try {
			await doChangePassword(currentPassword, newPassword);
			formOk = 'Password changed.';
			currentPassword = '';
			newPassword = '';
			confirmPassword = '';
		} catch (e: unknown) {
			formError = e instanceof Error && e.message ? e.message : 'Password change failed.';
		} finally {
			formBusy = false;
		}
	};
</script>

<div class="wrap">
	<header class="header">
		<h1>Admin Profile</h1>
		<p class="muted">Signed-in identity (read-only) · {authState.user?.role ?? ''}</p>
	</header>

	{#if loading}
		<SkeletonDetail rows={5} label="Loading profile…" />
	{:else if loadError}
		<section class="card"><p class="error">{loadError}</p></section>
	{:else if identity}
		<section class="card">
			<h2 class="section-title">Profile</h2>
			<dl class="detail">
				<div><dt>Name</dt><dd>{displayName}</dd></div>
				<div><dt>Email</dt><dd class="mono">{identity.email}</dd></div>
				<div><dt>Role</dt><dd>{identity.role}</dd></div>
				<div>
					<dt>Last login</dt>
					<dd>{identity.last_login ? identity.last_login.slice(0, 16).replace('T', ' ') : '—'}</dd>
				</div>
			</dl>
		</section>

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
			<h2 class="section-title">Security</h2>
			{#if isSuperAdmin()}
				<h3 class="sub-title">Change password</h3>
				{#if formError}
					<p class="error" role="alert">{formError}</p>
				{/if}
				{#if formOk}
					<p class="ok" role="status">{formOk}</p>
				{/if}
				<form onsubmit={submitPassword}>
					<div class="form">
						<label>Current password
							<input class="input" type="password" autocomplete="current-password" bind:value={currentPassword} />
						</label>
						<label>New password
							<input class="input" type="password" autocomplete="new-password" bind:value={newPassword} />
						</label>
						<ul class="req-list">
							<li class:met={passwordReq.length}>At least 8 characters</li>
							<li class:met={passwordReq.upper}>One uppercase letter</li>
							<li class:met={passwordReq.lower}>One lowercase letter</li>
							<li class:met={passwordReq.number}>One number</li>
							<li class:met={passwordReq.symbol}>One symbol</li>
						</ul>
						<label>Confirm new password
							<input class="input" type="password" autocomplete="new-password" bind:value={confirmPassword} />
							{#if confirmPassword && !passwordsMatch}
								<span class="hint warn">Passwords do not match.</span>
							{/if}
						</label>
					</div>
					<div class="modal-actions">
						<button class="btn" type="submit" aria-busy={formBusy} disabled={formBusy}>
							{formBusy ? 'Saving…' : 'Change password'}
						</button>
					</div>
				</form>
			{:else}
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
						<button class="btn" aria-busy={questionBusy} onclick={onSaveQuestion} disabled={questionBusy}>
							{questionBusy ? 'Saving…' : 'Save'}
						</button>
						<button class="btn ghost" onclick={() => (questionOpen = false)}>Cancel</button>
					</div>
				{/if}
			{/if}
			{#if isSuperAdmin()}
				<hr class="divider" />
				<MfaSettings />
			{/if}
		</section>

		<p class="meta muted">App version: 1.0.0</p>
	{/if}
</div>

<style>
	.wrap {
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
		max-width: 720px;
		margin-inline: auto;
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
		cursor: pointer;
	}

	.segment.active {
		background: var(--brand);
		color: var(--on-brand);
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
		font-size: 0.875rem;
		font-weight: 700;
		text-decoration: none;
		cursor: pointer;
		transition: background 0.15s ease, box-shadow 0.15s ease;
	}

	.btn:hover {
		background: var(--brand-hover);
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
		margin: 0 0 0.75rem;
	}

	.meta {
		text-align: center;
		font-size: 0.8125rem;
	}

	/* admin-specific */
	.detail {
		display: flex;
		flex-direction: column;
		gap: 0.625rem;
		margin: 0;
	}

	.detail > div {
		display: grid;
		grid-template-columns: 10rem minmax(0, 1fr);
		gap: 0.75rem;
		font-size: 0.9375rem;
	}

	.detail dt {
		color: var(--text-muted);
		font-weight: 600;
	}

	.detail dd {
		margin: 0;
		color: var(--text-strong);
	}

	.form {
		display: flex;
		flex-direction: column;
		gap: 0.875rem;
		max-width: 28rem;
	}

	.form label {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-secondary);
	}

	.input {
		padding: 0.625rem 0.875rem;
		border: 1px solid var(--border-strong);
		border-radius: 8px;
		font-size: 0.9375rem;
		font-family: inherit;
		color: var(--text-strong);
		background: var(--bg-card);
	}

	.input:focus {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
		border-color: var(--accent);
	}

	.req-list {
		list-style: none;
		display: flex;
		flex-wrap: wrap;
		gap: 0.375rem 1rem;
		margin: 0;
		padding: 0;
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.req-list .met {
		color: var(--success);
	}

	.hint {
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.hint.warn {
		color: var(--danger);
	}

	.ok {
		color: var(--success);
		font-size: 0.875rem;
		margin: 0 0 1rem;
	}

	.modal-actions {
		display: flex;
		gap: 0.75rem;
		justify-content: flex-start;
		margin-top: 1.25rem;
	}

	.mono {
		font-variant-numeric: tabular-nums;
	}
</style>
