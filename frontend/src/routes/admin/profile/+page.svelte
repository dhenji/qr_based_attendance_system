<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { me } from '$lib/features/auth/service';
	import MfaSettings from '$lib/components/MfaSettings.svelte';
	import {
		authState,
		doChangePassword,
		isAdmin,
		restoreSession,
	} from '$lib/features/auth/store.svelte';
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

	let currentPassword = $state('');
	let newPassword = $state('');
	let confirmPassword = $state('');
	let formError = $state<string | null>(null);
	let formOk = $state<string | null>(null);
	let formBusy = $state(false);

	const displayName = $derived(
		[identity?.first_name, identity?.last_name].filter(Boolean).join(' ') || 'Admin'
	);

	const passwordReq = $derived(evaluatePassword(newPassword));
	const passwordOk = $derived(isPasswordStrong(passwordReq));
	const passwordsMatch = $derived(newPassword === confirmPassword);

	onMount(async () => {
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

<div class="page">
	<header class="header">
		<div>
			<h1>Admin Profile</h1>
			<p class="muted">Signed-in identity (read-only) · {authState.user?.role ?? ''}</p>
		</div>
	</header>

	{#if loading}
		<section class="card"><p class="muted">Loading…</p></section>
	{:else if loadError}
		<section class="card"><p class="error">{loadError}</p></section>
	{:else if identity}
		<section class="card">
			<h2 class="section-title">{displayName}</h2>
			<dl class="detail">
				<div><dt>Email</dt><dd class="mono">{identity.email}</dd></div>
				<div><dt>Role</dt><dd>{identity.role}</dd></div>
				<div>
					<dt>Last login</dt>
					<dd>{identity.last_login ? identity.last_login.slice(0, 16).replace('T', ' ') : '—'}</dd>
				</div>
			</dl>
		</section>

		<MfaSettings />

		<section class="card">
			<h2 class="section-title">Change password</h2>
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
					<button class="btn btn-primary" type="submit" disabled={formBusy}>
						{formBusy ? 'Saving…' : 'Change password'}
					</button>
				</div>
			</form>
		</section>
	{/if}
</div>

<style>
	.page {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
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

	.mono {
		font-variant-numeric: tabular-nums;
	}

	.card {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 1.5rem;
		box-shadow: var(--shadow-sm);
	}

	.section-title {
		margin: 0 0 1rem;
		font-size: 1.125rem;
		font-weight: 700;
		color: var(--text);
	}

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

	.error {
		color: var(--danger);
		font-size: 0.875rem;
		margin: 0 0 1rem;
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

	.btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		padding: 0.625rem 1rem;
		border-radius: 8px;
		font-size: 0.875rem;
		font-weight: 600;
		font-family: inherit;
		cursor: pointer;
	}

	.btn-primary {
		background: var(--brand);
		border: 1px solid var(--brand);
		color: var(--on-brand);
	}

	.btn-primary:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}
</style>
