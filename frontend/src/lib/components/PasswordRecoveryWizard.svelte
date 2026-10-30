<script lang="ts">
	import { onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { APIError } from '$lib/api/client';
	import {
		startPasswordRecovery,
		resetPasswordAuthenticated,
		} from '$lib/features/auth/service';
	import { doResetPasswordAuthenticated } from '$lib/features/auth/store.svelte';
	import { defaultRouteFor } from '$lib/features/auth/store.svelte';
	import { Routes } from '$lib/shared/constants/routes';
	import { evaluatePassword, isPasswordStrong } from '$lib/shared/utils/password';
	import { createOtpWindow } from '$lib/features/auth/store.svelte';
	import OtpInput from '$lib/components/OtpInput.svelte';
	import OtpCodeRow from '$lib/components/OtpCodeRow.svelte';

	let step = $state<'idle' | 'loading' | 'otp' | 'password' | 'done'>('idle');
	let recoveryToken = $state<string | null>(null);
	let maskedEmail = $state<string>('');
	let otp = $state<string[]>(['', '', '', '', '', '']);
	let newPwd = $state('');
	let confirmPwd = $state('');
	let showNewPwd = $state(false);
	let showConfirmPwd = $state(false);
	let busy = $state(false);
	let error = $state('');
	let otpInput: import('$lib/components/OtpInput.svelte').default | undefined = $state();
	let successTimer: ReturnType<typeof setTimeout> | null = null;

	const win = createOtpWindow();

	const passwordsMatch = $derived(
		newPwd !== '' && confirmPwd !== '' ? newPwd === confirmPwd : null
	);
	const req = $derived(evaluatePassword(newPwd));
	const allReqsMet = $derived(isPasswordStrong(req));

	onDestroy(() => {
		win.stop();
		if (successTimer) clearTimeout(successTimer);
	});

	const clearError = () => {
		if (error) error = '';
	};

	const toMessage = (e: unknown, fallback: string): string => {
		if (e instanceof APIError && e.code === 'recovery_locked') {
			const match = e.message.match(/try again in (\d+)\s*minute/i);
			if (match) {
				const minutes = match[1];
				return `Too many recovery attempts. Try again in ${minutes} minute${minutes === '1' ? '' : 's'}.`;
			}
			return e.message;
		}
		if (e instanceof APIError && (e.code === 'otp_invalid' || e.code === 'otp_expired' || e.code === 'otp_max_attempts'))
			return e.code === 'otp_expired' ? 'That code has expired. Request a new one.' : e.code === 'otp_max_attempts' ? 'Too many incorrect codes. Request a new code.' : 'That code is incorrect. Check your email and try again.';
		if (e instanceof APIError && e.code === 'password_policy_violation')
			return 'Password does not meet the required policy.';
		return e instanceof Error && e.message ? e.message : fallback;
	};

	async function start() {
		busy = true;
		error = '';
		try {
			const result = await startPasswordRecovery();
			recoveryToken = result.recoveryToken;
			maskedEmail = result.maskedEmail;
			step = 'otp';
			win.restart();
		} catch (e: unknown) {
			error = toMessage(e, 'Could not start password recovery. Please try again.');
			step = 'idle';
		} finally {
			busy = false;
		}
	}

	async function handleOtpStep() {
		if (otp.some((d) => !d)) {
			error = 'Enter all 6 digits';
			return;
		}
		error = '';
		step = 'password';
	}

	async function handleReset() {
		if (!newPwd || !confirmPwd) {
			error = 'Both fields required';
			return;
		}
		if (newPwd !== confirmPwd) {
			error = 'Passwords do not match';
			return;
		}
		if (!allReqsMet) {
			error = 'Password does not meet all requirements.';
			return;
		}
		busy = true;
		error = '';
		try {
			const user = await doResetPasswordAuthenticated(otp.join(''), newPwd);
			step = 'done';
			if (successTimer) clearTimeout(successTimer);
			successTimer = setTimeout(() => {
				successTimer = null;
				if (user) void goto(defaultRouteFor(user));
				else void goto(Routes.LOGIN);
			}, 1500);
		} catch (e: unknown) {
			error = toMessage(e, 'Password reset failed. Please try again.');
			if (e instanceof APIError && (e.code === 'otp_invalid' || e.code === 'otp_expired' || e.code === 'otp_max_attempts')) {
				step = 'otp';
			}
		} finally {
			busy = false;
		}
	}

	async function resend() {
		if (!recoveryToken) {
			error = 'Session expired. Restart recovery.';
			return;
		}
		busy = true;
		error = '';
		try {
			const result = await startPasswordRecovery();
			recoveryToken = result.recoveryToken;
			maskedEmail = result.maskedEmail;
			win.restart();
			otp = ['', '', '', '', '', ''];
			otpInput?.focus();
		} catch (e: unknown) {
			error = toMessage(e, 'Could not resend the code. Please try again.');
		} finally {
			busy = false;
		}
	}
</script>

<div class="recovery">
	{#if step === 'idle'}
		<button class="btn-primary" onclick={start} disabled={busy} aria-busy={busy}>
			{busy ? 'Starting…' : 'Change Password'}
		</button>
		{#if error}
			<div class="error-banner">{error}</div>
		{/if}
	{:else if step === 'loading'}
		<p class="muted">Starting password recovery…</p>
	{:else if step === 'otp'}
		<p class="step-sub">A verification code has been sent to your registered email address.</p>
		{#if maskedEmail}
			<p class="step-sub">Sent to <strong>{maskedEmail}</strong></p>
		{/if}
		{#if error}
			<div class="error-banner">{error}</div>
		{/if}
		<OtpInput bind:digits={otp} bind:this={otpInput} disabled={busy} onChange={clearError} />
		<OtpCodeRow win={win} busy={busy} onresend={resend} />
		<button class="btn-primary" onclick={handleOtpStep} disabled={busy} aria-busy={busy}>
			{busy ? 'Working…' : 'Verify'}
		</button>
	{:else if step === 'password'}
		<p class="step-sub">Enter your new password.</p>
		{#if error}
			<div class="error-banner">{error}</div>
		{/if}
		<div class="field">
			<label class="form-label" for="rw-new">New Password</label>
			<div class="pwd-wrap">
				<input class="form-input" id="rw-new" type={showNewPwd ? 'text' : 'password'} placeholder="••••••••••••"
					value={newPwd} oninput={(e) => { newPwd = (e.target as HTMLInputElement).value; }} style="padding-right: 2.5rem;" />
				<button class="pwd-toggle" onclick={() => { showNewPwd = !showNewPwd; }} aria-label={showNewPwd ? 'Hide password' : 'Show password'}>
					{showNewPwd ? 'Hide' : 'Show'}
				</button>
			</div>
		</div>
		<div class="field">
			<label class="form-label" for="rw-confirm">Confirm Password</label>
			<div class="pwd-wrap">
				<input class="form-input" id="rw-confirm" type={showConfirmPwd ? 'text' : 'password'} placeholder="••••••••••••"
					value={confirmPwd} oninput={(e) => { confirmPwd = (e.target as HTMLInputElement).value; }} style="padding-right: 2.5rem;" />
				<button class="pwd-toggle" onclick={() => { showConfirmPwd = !showConfirmPwd; }} aria-label={showConfirmPwd ? 'Hide password' : 'Show password'}>
					{showConfirmPwd ? 'Hide' : 'Show'}
				</button>
			</div>
		</div>
		{#if passwordsMatch !== null}
			<div class="match-banner {passwordsMatch ? 'match' : 'no-match'}">
				{passwordsMatch ? 'Passwords match.' : 'Passwords do not match.'}
			</div>
		{/if}
		<div class="req-list">
			<div class="req-item {req.length ? 'met' : ''}">{req.length ? '✔' : '✘'} 8+ characters</div>
			<div class="req-item {req.upper ? 'met' : ''}">{req.upper ? '✔' : '✘'} One uppercase letter</div>
			<div class="req-item {req.lower ? 'met' : ''}">{req.lower ? '✔' : '✘'} One lowercase letter</div>
			<div class="req-item {req.number ? 'met' : ''}">{req.number ? '✔' : '✘'} One number</div>
			<div class="req-item {req.symbol ? 'met' : ''}">{req.symbol ? '✔' : '✘'} One symbol</div>
		</div>
		<button class="btn-primary" onclick={handleReset} disabled={busy} aria-busy={busy}>
			{busy ? 'Resetting…' : 'Reset password'}
		</button>
	{:else}
		<div class="success-banner">Password updated. Redirecting…</div>
	{/if}
</div>

<style>
	.recovery { display: flex; flex-direction: column; gap: 0.75rem; }
	.step-sub { color: var(--text-muted); font-size: 0.8125rem; line-height: 1.5; margin: 0 0 0.75rem; }
	.step-sub strong { color: var(--text-strong); }
	.error-banner { background: var(--danger-bg); border: 1px solid color-mix(in srgb, var(--danger) 22%, transparent); border-left: 3px solid var(--danger); border-radius: 8px; padding: 0.625rem 0.875rem; margin-bottom: 1rem; color: var(--danger); font-size: 0.8125rem; line-height: 1.45; }
	.field { margin-bottom: 1.25rem; }
	.form-label { display: block; font-weight: 600; font-size: 0.8125rem; color: var(--text-secondary); margin-bottom: 0.375rem; }
	.form-input { width: 100%; padding: 0.6875rem 0.875rem; background: var(--bg-input); color: var(--text); border: 1px solid var(--border-strong); border-radius: 10px; font-size: 0.9375rem; font-family: inherit; outline: none; }
	.pwd-wrap { position: relative; }
	.pwd-toggle { position: absolute; right: 10px; top: 50%; transform: translateY(-50%); background: none; border: none; cursor: pointer; color: var(--text-muted); padding: 0; }
	.req-list { background: var(--info-bg); border: 1px solid var(--info-bg); border-radius: 8px; padding: 0.625rem; margin-bottom: 1rem; font-size: 0.8rem; display: flex; flex-direction: column; gap: 0.25rem; }
	.req-item { color: var(--text-muted); }
	.req-item.met { color: var(--success); }
	.match-banner { border-radius: 8px; padding: 0.5rem 0.75rem; margin-bottom: 1rem; font-size: 0.8rem; }
	.match-banner.match { background: var(--success-bg); border-left: 3px solid var(--success); color: var(--success); }
	.match-banner.no-match { background: var(--danger-bg); border-left: 3px solid var(--danger); color: var(--danger); }
	.btn-primary { width: 100%; padding: 0.8125rem; border: 1px solid color-mix(in srgb, var(--brand) 80%, #0a1220); border-radius: 10px; background: linear-gradient(135deg, var(--brand), color-mix(in srgb, var(--brand) 70%, #0a1220)); color: var(--on-brand); font-size: 1rem; font-weight: 600; font-family: inherit; cursor: pointer; }
	.btn-primary:disabled { background: var(--border-strong); color: var(--text-muted); cursor: not-allowed; }
	.success-banner { background: var(--success-bg); border: 1px solid color-mix(in srgb, var(--success) 22%, transparent); border-left: 3px solid var(--success); border-radius: 8px; padding: 0.625rem 0.875rem; margin-bottom: 1rem; color: var(--success); font-size: 0.8125rem; font-weight: 600; }
	.muted { color: var(--text-muted); font-size: 0.875rem; }
</style>