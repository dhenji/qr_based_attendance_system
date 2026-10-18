<script lang="ts">
	import { goto } from '$app/navigation';
	import { onDestroy } from 'svelte';
	import { APIError } from '$lib/api/client';
	import {
		forgotPassword,
		forgotPasswordVerify,
		requestOtp,
	} from '$lib/features/auth/service';
	import { Routes } from '$lib/shared/constants/routes';
	import { defaultRouteFor, doResetPassword, createOtpWindow } from '$lib/features/auth/store.svelte';
	import { evaluatePassword, isPasswordStrong } from '$lib/shared/utils/password';
	import OtpInput from '$lib/components/OtpInput.svelte';
	import OtpCodeRow from '$lib/components/OtpCodeRow.svelte';
	import Turnstile from '$lib/components/Turnstile.svelte';

	// Forgot-password recovery (ADR-056), live against the backend:
	//  1. POST /auth/forgot-password {email, turnstile_token?} -> {question}
	//     (decoy for unknown emails — always render it, never hint at account
	//     existence; turnstile_token omitted when unconfigured).
	//  2. POST /auth/forgot-password/verify {email, answer} -> recovery_token
	//     (5-min grant held in memory; 423 recovery_locked on lockout).
	//  3. OTP request (grant-gated); the code is collected here and verified
	//     + consumed exactly once, by the reset call at step 4 (ADR-056).
	//  4. POST /auth/reset-password {email, otp_code, new_password}
	//     -> TokenResponse (session or MFA challenge).
	//  5. On success, auto-login with the new password and land on the role
	//     dashboard (mfa_pending or a login failure falls back to the login
	//     page).

	let step = $state(1);
	let email = $state('');
	let answer = $state('');
	let otp = $state<string[]>(['', '', '', '', '', '']);
	let newPwd = $state('');
	let confirmPwd = $state('');
	let showNewPwd = $state(false);
	let showConfirmPwd = $state(false);
	let busy = $state(false);
	let error = $state('');

	let securityQuestion = $state('');
	let recoveryToken = $state<string | null>(null);

	let otpInput: import('$lib/components/OtpInput.svelte').default | undefined = $state();
	let turnstile: import('$lib/components/Turnstile.svelte').default | undefined = $state();

	// Shared OTP window: remaining = code validity (display), resendIn = cooldown gate
	const win = createOtpWindow();

	const passwordsMatch = $derived(
		newPwd !== '' && confirmPwd !== '' ? newPwd === confirmPwd : null
	);

	const req = $derived(evaluatePassword(newPwd));

	const allReqsMet = $derived(isPasswordStrong(req));
	let success = $state(false);
	let successTimer: ReturnType<typeof setTimeout> | null = null;

	onDestroy(() => {
		win.stop();
		if (successTimer) clearTimeout(successTimer);
	});

	// Dismiss a stale failure as soon as the user starts correcting the form,
	// so the banner never reads as "still broken" while they type.
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
		if (e instanceof APIError && e.code === 'security_answer_invalid')
			return 'Incorrect answer. Check your security answer and try again.';
		if (e instanceof APIError && (e.code === 'otp_invalid' || e.code === 'otp_expired'))
			return e.code === 'otp_expired' ? 'That code has expired. Request a new one.' : 'That code is incorrect. Check your email and try again.';
		if (e instanceof APIError && e.code === 'unrecognized_email')
			return 'No account matches that email. Contact an administrator.';
		if (e instanceof APIError && e.code === 'password_policy_violation')
			return 'Password does not meet the required policy.';
		if (e instanceof APIError && e.code === 'password_reused')
			return 'New password must be different from your current one.';
		return e instanceof Error && e.message ? e.message : fallback;
	};

	async function handleStep1() {
		if (!email.trim()) {
			error = 'Email is required';
			return;
		}
		busy = true;
		error = '';
		try {
			const result = await forgotPassword(email, turnstile?.getToken() ?? null);
			securityQuestion = result.question;
			step = 2;
		} catch (e: unknown) {
			error = toMessage(e, 'Could not start recovery. Please try again.');
			if (e instanceof APIError && e.code === 'invalid_captcha') turnstile?.reset();
		} finally {
			busy = false;
		}
	}

	async function handleStep2() {
		if (!answer.trim()) {
			error = 'Answer is required';
			return;
		}
		busy = true;
		error = '';
		try {
			const grant = await forgotPasswordVerify(email, answer);
			recoveryToken = grant.recoveryToken;
			await requestOtp(email, 'forget_password', grant.recoveryToken);
			step = 3;
			win.restart();
		} catch (e: unknown) {
			error = toMessage(e, 'Verification failed. Please try again.');
		} finally {
			busy = false;
		}
	}

	async function handleStep3() {
		if (otp.some((d) => !d)) {
			error = 'Enter all 6 digits';
			return;
		}
		error = '';
		step = 4;
	}

	async function handleStep4() {
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
			// Step 4 signs the account in directly (or returns an MFA
			// challenge for MFA-enabled accounts); the success beat below
			// only delays the navigation, not the request.
			const user = await doResetPassword(email, otp.join(''), newPwd);
			success = true;
			if (successTimer) clearTimeout(successTimer);
			successTimer = setTimeout(() => {
				successTimer = null;
				if (user) void goto(defaultRouteFor(user));
				else void goto(Routes.LOGIN);
			}, 1500);
		} catch (e: unknown) {
			error = toMessage(e, 'Password reset failed. Please try again.');
			if (e instanceof APIError && (e.code === 'otp_invalid' || e.code === 'otp_expired')) {
				step = 3;
			}
		} finally {
			busy = false;
		}
	}

	async function resend() {
		busy = true;
		error = '';
		try {
			if (!recoveryToken) {
				error = 'Session expired. Restart recovery from step 1.';
				return;
			}
			await requestOtp(email, 'forget_password', recoveryToken);
			win.restart();
			otpInput?.focus();
		} catch (e: unknown) {
			error = toMessage(e, 'Could not resend the code. Please try again.');
		} finally {
			busy = false;
		}
	}
</script>

<main class="auth">
	<div class="wrapper">
		<div class="brand-header">
			<div class="header-logo"><img src="/qr-attend-logo.svg" alt="Attendly" /></div>
			<span class="brand-name">Attendly</span>
		</div>

		<div class="steps">
			{#each [1, 2, 3, 4] as s}
				<div class="step">
					<div class="step-dot {s === step ? 'active' : s < step ? 'done' : ''}">
						{s < step ? '✓' : s}
					</div>
					{#if s < 4}
						<div class="step-line {s < step ? 'done' : ''}"></div>
					{/if}
				</div>
			{/each}
		</div>

		<div class="card">
			{#if step === 1}
				<div class="step-panel">
					<h2>Forgot Password</h2>
					<p class="step-sub">Step 1 of 4. Enter your email.</p>

					{#if error}
						<div class="error-banner">{error}</div>
					{/if}

					<div class="field">
						<label class="form-label" for="fp-email">Email</label>
						<input class="form-input" id="fp-email" type="email" placeholder="juan.delacruz@isu.edu.ph"
							value={email} oninput={(e) => { email = (e.target as HTMLInputElement).value; }} />
					</div>

					<Turnstile bind:this={turnstile} />

					<button class="btn-primary" onclick={handleStep1} disabled={busy}>
						{busy ? 'Checking…' : 'Continue'}
					</button>
					<button class="back-btn" onclick={() => goto(Routes.LOGIN)}>← Back to Login</button>
				</div>
			{:else if step === 2}
				<div class="step-panel">
					<h2>Verify Identity</h2>
					<p class="step-sub">Step 2 of 4. Answer your security question.</p>

					{#if error}
						<div class="error-banner">{error}</div>
					{/if}

					<div class="question-panel">"{securityQuestion}"</div>

					<div class="field">
						<label class="form-label" for="fp-answer">Your Answer</label>
						<input class="form-input" id="fp-answer" placeholder="Your answer..."
							value={answer} oninput={(e) => { answer = (e.target as HTMLInputElement).value; }} />
					</div>

					<button class="btn-primary" onclick={handleStep2} disabled={busy}>
						{busy ? 'Verifying…' : 'Verify'}
					</button>
				</div>
			{:else if step === 3}
				<div class="step-panel">
					<h2>One-Time Code</h2>
					<p class="step-sub">Step 3 of 4. Enter the code from your email.</p>
					<p class="step-sub">A 6-digit code was sent to <strong>{email}</strong></p>

					{#if error}
						<div class="error-banner">{error}</div>
					{/if}

					<OtpInput bind:digits={otp} bind:this={otpInput} disabled={busy} onChange={clearError} />

					<OtpCodeRow win={win} busy={busy} onresend={resend} />

					<button class="btn-primary" onclick={handleStep3} disabled={busy}>
						{busy ? 'Verifying…' : 'Verify'}
					</button>
				</div>
			{:else}
				<div class="step-panel">
					<h2>New Password</h2>
					<p class="step-sub">Step 4 of 4. Set your new password.</p>

					{#if error}
						<div class="error-banner">{error}</div>
					{/if}

					<div class="field">
						<label class="form-label" for="fp-new">New Password</label>
						<div class="pwd-wrap">
							<input class="form-input" id="fp-new" type={showNewPwd ? 'text' : 'password'}
								placeholder="••••••••••••" value={newPwd}
								oninput={(e) => { newPwd = (e.target as HTMLInputElement).value; }}
								style="padding-right: 2.5rem;" />
							<button class="pwd-toggle" onclick={() => { showNewPwd = !showNewPwd; }}
								aria-label={showNewPwd ? 'Hide password' : 'Show password'}>
								{#if showNewPwd}
									<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" /><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" /><path d="M14.12 14.12a3 3 0 1 1-4.24-4.24" /><line x1="1" y1="1" x2="23" y2="23" /></svg>
								{:else}
									<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></svg>
								{/if}
							</button>
						</div>
					</div>

					<div class="field">
						<label class="form-label" for="fp-confirm">Confirm Password</label>
						<div class="pwd-wrap">
							<input class="form-input" id="fp-confirm" type={showConfirmPwd ? 'text' : 'password'}
								placeholder="••••••••••••" value={confirmPwd}
								oninput={(e) => { confirmPwd = (e.target as HTMLInputElement).value; }}
								style="padding-right: 2.5rem;" />
							<button class="pwd-toggle" onclick={() => { showConfirmPwd = !showConfirmPwd; }}
								aria-label={showConfirmPwd ? 'Hide password' : 'Show password'}>
								{#if showConfirmPwd}
									<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" /><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" /><path d="M14.12 14.12a3 3 0 1 1-4.24-4.24" /><line x1="1" y1="1" x2="23" y2="23" /></svg>
								{:else}
									<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></svg>
								{/if}
							</button>
						</div>
					</div>

					{#if success}
						<div class="success-banner">Password updated. Signing you in…</div>
					{/if}

					<div class="req-list">
						<div class="req-item {req.length ? 'met' : ''}">{req.length ? '✔' : '✘'} 8+ characters</div>
						<div class="req-item {req.upper ? 'met' : ''}">{req.upper ? '✔' : '✘'} One uppercase letter</div>
						<div class="req-item {req.lower ? 'met' : ''}">{req.lower ? '✔' : '✘'} One lowercase letter</div>
						<div class="req-item {req.number ? 'met' : ''}">{req.number ? '✔' : '✘'} One number</div>
						<div class="req-item {req.symbol ? 'met' : ''}">{req.symbol ? '✔' : '✘'} One symbol</div>
					</div>

					{#if passwordsMatch !== null}
						<div class="match-banner {passwordsMatch ? 'match' : 'no-match'}">
							{passwordsMatch ? 'Passwords match.' : 'Passwords do not match.'}
						</div>
					{/if}

					<button class="btn-primary" onclick={handleStep4} disabled={success || busy}>
						{success ? 'Password updated' : busy ? 'Resetting…' : 'Reset password'}
					</button>
				</div>
			{/if}
		</div>
	</div>
</main>

<style>
	main.auth {
		min-height: calc(100vh - 3.75rem);
		background: var(--bg-page);
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 2rem;
	}

	.wrapper {
		width: 100%;
		max-width: 420px;
	}

	.brand-header {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.625rem;
		margin-bottom: 1.5rem;
	}

	.header-logo {
		width: 40px;
		height: 40px;
		background: var(--brand);
		border-radius: 12px;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.header-logo img {
		width: 26px;
		height: 26px;
		display: block;
	}

	.brand-name {
		font-size: 1.375rem;
		font-weight: 700;
		color: var(--brand);
		letter-spacing: -0.01em;
	}

	.steps {
		display: flex;
		align-items: center;
		justify-content: center;
		margin-bottom: 1.5rem;
	}

	.step {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.step-dot {
		width: 28px;
		height: 28px;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 0.75rem;
		font-weight: 700;
		background: var(--bg-muted);
		color: var(--text-muted);
		flex-shrink: 0;
	}

	.step-dot.active {
		background: var(--accent);
		color: var(--on-brand);
	}

	.step-dot.done {
		background: #0d9488;
		color: var(--on-brand);
	}

	.step-line {
		width: 24px;
		height: 2px;
		background: var(--border-strong);
	}

	.step-line.done {
		background: #0d9488;
	}

	.card {
		background: var(--bg-card);
		padding: 2rem;
		border-radius: 12px;
		box-shadow: var(--shadow-sm);
	}

	h2 {
		font-size: 1.375rem;
		font-weight: 700;
		color: var(--brand);
		margin: 0 0 0.25rem;
	}

	.step-sub {
		color: var(--text-muted);
		font-size: 0.8125rem;
		margin: 0 0 1.5rem;
	}

	.step-sub strong {
		color: var(--brand);
	}

	.error-banner {
		background: var(--danger-bg);
		border: 1px solid var(--danger-bg);
		border-radius: 8px;
		padding: 0.625rem 0.875rem;
		margin-bottom: 1rem;
		color: var(--danger);
		font-size: 0.8125rem;
	}

	.field {
		margin-bottom: 1.25rem;
	}

	.form-label {
		display: block;
		font-weight: 600;
		font-size: 0.8125rem;
		color: var(--text-secondary);
		margin-bottom: 0.375rem;
	}

	.form-input {
		width: 100%;
		padding: 0.625rem 0.875rem;
		border: 1.5px solid var(--border-strong);
		border-radius: 8px;
		font-size: 0.9375rem;
		font-family: inherit;
		outline: none;
		transition: border-color 0.15s;
	}

	.form-input:focus {
		border-color: var(--accent);
	}

	.pwd-wrap {
		position: relative;
	}

	.pwd-toggle {
		position: absolute;
		right: 10px;
		top: 50%;
		transform: translateY(-50%);
		background: none;
		border: none;
		cursor: pointer;
		color: var(--text-muted);
		padding: 0;
		display: flex;
		align-items: center;
	}

	.pwd-toggle:hover {
		color: var(--text-secondary);
	}

	.question-panel {
		background: var(--bg-page);
		border: 1px solid var(--border-strong);
		border-radius: 8px;
		padding: 0.875rem;
		margin-bottom: 1rem;
		font-size: 0.875rem;
		color: var(--brand);
		font-style: italic;
		font-weight: 500;
	}

	.req-list {
		background: var(--info-bg);
		border: 1px solid var(--info-bg);
		border-radius: 8px;
		padding: 0.625rem;
		margin-bottom: 1rem;
		font-size: 0.8rem;
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.req-item {
		color: var(--text-muted);
	}

	.req-item.met {
		color: var(--success);
	}

	.success-banner {
		background: var(--success-bg);
		border: 1px solid var(--success-bg);
		border-radius: 8px;
		padding: 0.625rem 0.875rem;
		margin-bottom: 1rem;
		color: var(--success);
		font-size: 0.8125rem;
		font-weight: 600;
	}

	.match-banner {
		border-radius: 8px;
		padding: 0.5rem 0.75rem;
		margin-bottom: 1rem;
		font-size: 0.8rem;
	}

	.match-banner.match {
		background: var(--success-bg);
		color: var(--success);
	}

	.match-banner.no-match {
		background: var(--danger-bg);
		color: var(--danger);
	}

	.btn-primary {
		width: 100%;
		padding: 0.75rem;
		border: none;
		border-radius: 8px;
		background: var(--brand);
		color: var(--on-brand);
		font-size: 1rem;
		font-weight: 600;
		font-family: inherit;
		cursor: pointer;
	}

	.btn-primary:hover {
		background: var(--brand-hover);
	}

	.btn-primary:disabled {
		background: var(--border-strong);
		cursor: not-allowed;
	}

	.back-btn {
		width: 100%;
		margin-top: 0.75rem;
		background: none;
		border: none;
		cursor: pointer;
		color: var(--text-muted);
		font-size: 0.8125rem;
		font-family: inherit;
		padding: 0;
	}

	.back-btn:hover {
		color: var(--text-secondary);
	}
</style>
