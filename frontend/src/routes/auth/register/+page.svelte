<script lang="ts">
	import { goto } from '$app/navigation';
	import { onDestroy, onMount } from 'svelte';
	import { Routes } from '$lib/shared/constants/routes';
	import { toAuthMessage } from '$lib/features/auth/errors';
	import { requestOtp } from '$lib/features/auth/service';
	import { authState, defaultRouteFor, doRegister, createOtpWindow } from '$lib/features/auth/store.svelte';
	import { SECURITY_QUESTIONS } from '$lib/features/auth/security';
	import { evaluatePassword, isPasswordStrong } from '$lib/shared/utils/password';
	import OtpInput from '$lib/components/OtpInput.svelte';
	import OtpCodeRow from '$lib/components/OtpCodeRow.svelte';

	// Mirrors the backend's claim flow: prove you own the roster email with an
	// OTP, then set the credentials. POST /auth/register consumes the CLAIM OTP
	// itself, so it has to be collected before the final step.
	type Step = 'email' | 'otp' | 'details';
	let step = $state<Step>('email');

	let email = $state('');
	let otp = $state<string[]>(['', '', '', '', '', '']);
	let password = $state('');
	let confirm = $state('');
	let securityQuestion = $state('');
	let securityAnswer = $state('');
	let questionOpen = $state(false);
	let questionMenu: HTMLDivElement | undefined = $state();

	let showPwd = $state(false);
	let showConfirmPwd = $state(false);
	let submitting = $state(false);
	let error = $state('');

	// Shared OTP window: remaining = code validity (display), resendIn = cooldown gate
	const win = createOtpWindow();
	let otpInput: import('$lib/components/OtpInput.svelte').default | undefined = $state();

	onMount(() => {
		function onDocClick(e: MouseEvent) {
			if (!questionMenu?.contains(e.target as Node)) questionOpen = false;
		}
		document.addEventListener('click', onDocClick);
		return () => document.removeEventListener('click', onDocClick);
	});

	// Password policy lives in lib/shared/utils/password.ts (mirrors the
	// backend) — derived here so the checklist can never drift.
	const passwordChecks = $derived(evaluatePassword(password));
	const passwordOk = $derived(isPasswordStrong(passwordChecks));

	onDestroy(() => {
		win.stop();
	});

	// Dismiss a stale failure as soon as the user starts correcting the form,
	// so the banner never reads as "still broken" while they type.
	const clearError = () => {
		if (error) error = '';
	};

	// Step 1 -> 2: ask the backend to email a CLAIM OTP.
	const handleEmail = async (event: SubmitEvent) => {
		event.preventDefault();
		error = '';

		const trimmed = email.trim();
		if (!trimmed) {
			error = 'Email is required.';
			return;
		}

		submitting = true;
		try {
			await requestOtp(trimmed, 'claim');
			email = trimmed;
			otp = ['', '', '', '', '', ''];
			step = 'otp';
			win.restart();
		} catch (e: unknown) {
			error = toAuthMessage(e, 'Could not send the verification code. Please try again.');
		} finally {
			submitting = false;
		}
	};

	// Requesting again invalidates the previous code server-side, so the user
	// has to use the newest one.
	const resend = async () => {
		error = '';
		submitting = true;
		try {
			await requestOtp(email, 'claim');
			otp = ['', '', '', '', '', ''];
			win.restart();
			otpInput?.focus();
		} catch (e: unknown) {
			error = toAuthMessage(e, 'Could not resend the code. Please try again.');
		} finally {
			submitting = false;
		}
	};

	// Step 2 -> 3: the code isn't checked yet, it travels with the final request.
	const continueToDetails = (event: SubmitEvent) => {
		event.preventDefault();
		error = '';
		if (otp.some((d) => !d)) {
			error = 'Enter all 6 digits.';
			return;
		}
		step = 'details';
	};

	const handleRegister = async (event: SubmitEvent) => {
		event.preventDefault();
		error = '';

		if (!passwordOk) {
			error = 'Password does not meet all requirements.';
			return;
		}
		if (password !== confirm) {
			error = 'Passwords do not match.';
			return;
		}
		if (!securityQuestion) {
			error = 'Please select a security question.';
			return;
		}
		if (!securityAnswer.trim()) {
			error = 'Security answer is required.';
			return;
		}

		submitting = true;
		try {
			const user = await doRegister({
				email,
				otpCode: otp.join(''),
				password,
				securityQuestion,
				securityAnswer,
			});
			await goto(defaultRouteFor(user));
		} catch (e: unknown) {
			// A rejected OTP belongs on the code step, everything else on this one.
			const message = toAuthMessage(e, 'Registration failed. Please try again.');
			error = message;
			if (/code/i.test(message)) step = 'otp';
		} finally {
			submitting = false;
		}
	};

	const back = (to: Step) => {
		step = to;
		error = '';
		if (to === 'email') {
			win.stop();
		}
	};
</script>

<main class="auth">
	<div class="wrapper">
		<div class="header">
			<div class="logo-tile"><img src="/qr-attend-logo.svg" alt="Attendly" /></div>
			<p class="kicker">Account claim</p>
			{#if step === 'email'}
				<h1>Create Account</h1>
				<p class="subtitle">Use the university email on your roster record.</p>
			{:else if step === 'otp'}
				<h1>Verify Email</h1>
				<p class="subtitle">A 6-digit code was sent to <strong>{email}</strong></p>
			{:else}
				<h1>Finish Setting Up</h1>
				<p class="subtitle">Pick a password to finish claiming your account.</p>
			{/if}
		</div>

		<ol class="steps" aria-label="Registration progress">
			<li class:active={step === 'email'} class:done={step !== 'email'}>Email</li>
			<li class:active={step === 'otp'} class:done={step === 'details'}>Verify</li>
			<li class:active={step === 'details'}>Details</li>
		</ol>

		<div class="card">
			{#if error}
				<div class="error-banner">{error}</div>
			{/if}

			{#if step === 'email'}
				<form onsubmit={handleEmail}>
					<div class="field">
						<label class="form-label" for="reg-email">University email</label>
						<input class="form-input" id="reg-email" type="email" required
							autocomplete="email" placeholder="jose.p.rizal@isu.edu.ph"
							value={email}
							oninput={(e) => { email = (e.target as HTMLInputElement).value; }} />
						<p class="hint">Your name, program and section come from your roster record —
							there is nothing to type here. Accounts cannot be created for an email
							that isn't on the roster.</p>
					</div>

					<button class="btn-primary" type="submit" aria-busy={submitting} disabled={submitting}>
						{submitting ? 'Sending code…' : 'Send verification code'}
					</button>
				</form>
			{:else if step === 'otp'}
				<form onsubmit={continueToDetails}>
					<OtpInput bind:digits={otp} bind:this={otpInput} disabled={submitting} onChange={clearError} />

					<OtpCodeRow win={win} busy={submitting} onresend={resend} />

					<button class="btn-primary" type="submit" aria-busy={submitting} disabled={submitting}>Continue</button>
					<button type="button" class="back-btn" onclick={() => back('email')}>← Back</button>
				</form>
			{:else}
				<form onsubmit={handleRegister}>
					<div class="field">
						<label class="form-label" for="reg-password">Password</label>
						<div class="pwd-wrap">
							<input class="form-input" id="reg-password" type={showPwd ? 'text' : 'password'}
								required autocomplete="new-password" placeholder="••••••••"
								value={password}
								oninput={(e) => { password = (e.target as HTMLInputElement).value; }}
								style="padding-right: 2.5rem;" />
							<button type="button" class="pwd-toggle" onclick={() => { showPwd = !showPwd; }}
								aria-label={showPwd ? 'Hide password' : 'Show password'}>
								{#if showPwd}
									<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" /><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" /><path d="M14.12 14.12a3 3 0 1 1-4.24-4.24" /><line x1="1" y1="1" x2="23" y2="23" /></svg>
								{:else}
									<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></svg>
								{/if}
							</button>
						</div>
					</div>

					<div class="field">
						<label class="form-label" for="reg-confirm">Confirm Password</label>
						<div class="pwd-wrap">
							<input class="form-input" id="reg-confirm" type={showConfirmPwd ? 'text' : 'password'}
								required autocomplete="new-password" placeholder="••••••••"
								value={confirm}
								oninput={(e) => { confirm = (e.target as HTMLInputElement).value; }}
								style="padding-right: 2.5rem;" />
							<button type="button" class="pwd-toggle"
								onclick={() => { showConfirmPwd = !showConfirmPwd; }}
								aria-label={showConfirmPwd ? 'Hide password' : 'Show password'}>
								{#if showConfirmPwd}
									<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" /><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" /><path d="M14.12 14.12a3 3 0 1 1-4.24-4.24" /><line x1="1" y1="1" x2="23" y2="23" /></svg>
								{:else}
									<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></svg>
								{/if}
							</button>
						</div>
					</div>

					<div class="req-list">
						<div class="req-title">Password requirements</div>
						<div class="req-item {passwordChecks.length ? 'met' : ''}">{passwordChecks.length ? '✔' : '✘'} 8+ characters</div>
						<div class="req-item {passwordChecks.upper ? 'met' : ''}">{passwordChecks.upper ? '✔' : '✘'} 1 uppercase letter</div>
						<div class="req-item {passwordChecks.lower ? 'met' : ''}">{passwordChecks.lower ? '✔' : '✘'} 1 lowercase letter</div>
						<div class="req-item {passwordChecks.number ? 'met' : ''}">{passwordChecks.number ? '✔' : '✘'} 1 number</div>
						<div class="req-item {passwordChecks.symbol ? 'met' : ''}">{passwordChecks.symbol ? '✔' : '✘'} 1 symbol</div>
					</div>

					<div class="field">
						<label class="form-label" for="reg-question" id="reg-question-label">Security Question</label>
						<div class="dropdown" bind:this={questionMenu}>
							<button type="button" id="reg-question"
								class="dropdown-toggle {!securityQuestion ? 'placeholder' : ''}"
								onclick={() => { questionOpen = !questionOpen; }}
								aria-haspopup="listbox" aria-expanded={questionOpen}>
								<span>{securityQuestion || 'Select a question…'}</span>
								<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6" /></svg>
							</button>
							{#if questionOpen}
								<ul class="dropdown-menu" role="listbox" aria-labelledby="reg-question-label">
									{#each SECURITY_QUESTIONS as q}
										<li>
											<button type="button"
												class="dropdown-item {securityQuestion === q ? 'selected' : ''}"
												onclick={() => { securityQuestion = q; questionOpen = false; }}>
												<span>{q}</span>
												{#if securityQuestion === q}<span class="check">✓</span>{/if}
											</button>
										</li>
									{/each}
								</ul>
							{/if}
						</div>
					</div>

					<div class="field">
						<label class="form-label" for="reg-answer">Your Answer</label>
						<input class="form-input" id="reg-answer" required minlength="2" maxlength="100"
							placeholder="Your answer..." value={securityAnswer}
							oninput={(e) => { securityAnswer = (e.target as HTMLInputElement).value; }} />
						<p class="hint">You'll need this to recover your account if you forget your
							password. Answers are compared case-insensitively.</p>
					</div>

					<button class="btn-primary" type="submit" aria-busy={submitting} disabled={submitting || authState.loading}>
						{submitting ? 'Creating account…' : 'Create account'}
					</button>
					<button type="button" class="back-btn" onclick={() => back('otp')}>← Back</button>
				</form>
			{/if}

			<div class="links">
				<span class="login-hint">
					Already have an account?
					<button type="button" class="link-btn"
						onclick={() => goto(Routes.LOGIN)}>Login</button>
				</span>
			</div>
		</div>
	</div>
</main>

<style>
	main.auth {
		min-height: calc(100vh - 3.75rem);
		min-height: calc(100dvh - 3.75rem);
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

	.header {
		text-align: center;
		margin-bottom: 1.25rem;
	}

	.steps {
		display: flex;
		justify-content: center;
		gap: 0.375rem;
		list-style: none;
		padding: 0;
		margin: 0 0 1.25rem;
		font-family: var(--font-data);
		font-size: 0.625rem;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		color: var(--text-muted);
	}

	.steps li {
		padding: 0.25rem 0.625rem;
		border: 1px solid var(--border);
		border-radius: 999px;
		background: transparent;
	}

	.steps li.active {
		background: var(--brand);
		border-color: var(--brand);
		color: var(--on-brand);
		font-weight: 600;
	}

	.steps li.done {
		background: var(--success-bg);
		border-color: transparent;
		color: var(--success);
	}

	.logo-tile {
		width: 52px;
		height: 52px;
		background: linear-gradient(145deg, var(--brand), color-mix(in srgb, var(--brand) 72%, #0a1220));
		border-radius: 14px;
		display: flex;
		align-items: center;
		justify-content: center;
		margin: 0 auto 1rem;
		color: var(--on-brand);
		box-shadow: 0 10px 24px color-mix(in srgb, var(--brand) 26%, transparent);
	}

	.logo-tile img {
		width: 34px;
		height: 34px;
		display: block;
	}

	.kicker {
		margin: 0 0 0.5rem;
		font-family: var(--font-data);
		font-size: 0.625rem;
		font-weight: 500;
		letter-spacing: 0.16em;
		text-transform: uppercase;
		color: var(--accent);
	}

	h1 {
		font-size: 1.75rem;
		font-weight: 700;
		color: var(--text-strong);
		margin: 0 0 0.25rem;
		letter-spacing: -0.025em;
	}

	.subtitle {
		color: var(--text-muted);
		font-size: 0.875rem;
		line-height: 1.5;
		margin: 0;
	}

	.subtitle strong {
		color: var(--text-strong);
	}

	.card {
		position: relative;
		background: var(--bg-card);
		padding: 2rem;
		border: 1px solid var(--border);
		border-radius: 16px;
		box-shadow: var(--shadow-sm);
	}

	.card::before {
		content: '';
		position: absolute;
		top: 0;
		left: 16px;
		right: 16px;
		height: 3px;
		border-radius: 0 0 3px 3px;
		background: linear-gradient(90deg, var(--brand), var(--accent) 55%, transparent 90%);
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

	/* Intentional auth variant: taller 10px-radius controls; the shared
	   .form-input is the canonical app control. */
	.form-input {
		width: 100%;
		padding: 0.6875rem 0.875rem;
		background: var(--bg-input);
		color: var(--text);
		border: 1px solid var(--border-strong);
		border-radius: 10px;
		font-size: 0.9375rem;
		font-family: inherit;
		outline: none;
		transition: border-color 0.15s ease, box-shadow 0.15s ease;
	}

	.form-input::placeholder {
		color: color-mix(in srgb, var(--text-muted) 75%, transparent);
	}

	.form-input:focus {
		border-color: var(--accent);
		box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 16%, transparent);
	}

	.hint {
		color: var(--text-muted);
		font-size: 0.75rem;
		margin: 0.375rem 0 0;
	}

	.dropdown {
		position: relative;
	}

	.dropdown-toggle {
		width: 100%;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		padding: 0.6875rem 0.875rem;
		border: 1px solid var(--border-strong);
		border-radius: 10px;
		background: var(--bg-input);
		font-size: 0.9375rem;
		font-family: inherit;
		color: var(--text);
		cursor: pointer;
		outline: none;
		transition: border-color 0.15s ease, box-shadow 0.15s ease;
	}

	.dropdown-toggle:hover {
		border-color: color-mix(in srgb, var(--accent) 55%, var(--border-strong));
	}

	.dropdown-toggle.placeholder {
		color: color-mix(in srgb, var(--text-muted) 85%, transparent);
	}

	.dropdown-toggle:focus-visible {
		border-color: var(--accent);
		box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 16%, transparent);
	}

	.dropdown-menu {
		position: absolute;
		top: calc(100% + 4px);
		left: 0;
		right: 0;
		list-style: none;
		margin: 0;
		padding: 0.25rem;
		background: var(--bg-card);
		border: 1px solid var(--border-strong);
		border-radius: 10px;
		box-shadow: var(--shadow-sm);
		z-index: 10;
		max-height: 16rem;
		overflow-y: auto;
	}

	.dropdown-item {
		width: 100%;
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.5rem 0.625rem;
		border: none;
		border-radius: 8px;
		background: none;
		font-size: 0.875rem;
		font-family: inherit;
		color: var(--text-secondary);
		cursor: pointer;
		text-align: left;
	}

	.dropdown-item:hover {
		background: var(--bg-muted);
	}

	.dropdown-item.selected {
		color: var(--accent);
		font-weight: 600;
	}

	.check {
		color: var(--success);
		font-weight: 700;
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

	.req-list {
		background: var(--info-bg);
		border: 1px solid var(--info-bg);
		border-radius: 8px;
		padding: 0.75rem;
		margin-bottom: 1.25rem;
		font-size: 0.8rem;
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.req-title {
		font-weight: 700;
		color: var(--info-text);
		margin-bottom: 0.25rem;
	}

	.req-item {
		color: var(--text-muted);
		display: flex;
		gap: 0.375rem;
		align-items: center;
	}

	.req-item.met {
		color: var(--success);
	}

	/* Intentional auth variant: full-width gradient CTA. */
	.btn-primary {
		width: 100%;
		padding: 0.8125rem;
		border: 1px solid color-mix(in srgb, var(--brand) 80%, #0a1220);
		border-radius: 10px;
		background: linear-gradient(135deg, var(--brand), color-mix(in srgb, var(--brand) 70%, #0a1220));
		color: var(--on-brand);
		font-size: 1rem;
		font-weight: 600;
		font-family: inherit;
		cursor: pointer;
		box-shadow: 0 6px 16px color-mix(in srgb, var(--brand) 22%, transparent);
		transition: transform 0.15s ease, box-shadow 0.15s ease, filter 0.15s ease;
	}

	.btn-primary:hover:not(:disabled) {
		transform: translateY(-1px);
		filter: brightness(1.07);
		box-shadow: 0 9px 22px color-mix(in srgb, var(--brand) 30%, transparent);
	}

	.btn-primary:active:not(:disabled) {
		transform: translateY(0);
	}

	.btn-primary:disabled {
		opacity: 0.55;
		cursor: not-allowed;
		box-shadow: none;
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

	.links {
		text-align: center;
		margin-top: 1rem;
		font-size: 0.8125rem;
		color: var(--text-muted);
	}

	.link-btn {
		background: none;
		border: none;
		cursor: pointer;
		color: var(--accent);
		font-size: 0.8125rem;
		font-weight: 600;
		font-family: inherit;
		padding: 0;
	}

	.link-btn:hover {
		text-decoration: underline;
		text-underline-offset: 2px;
	}

	@media (prefers-reduced-motion: reduce) {
		.form-input,
		.dropdown-toggle,
		.btn-primary {
			transition: none;
		}

		.btn-primary:hover:not(:disabled) {
			transform: none;
		}
	}
</style>
