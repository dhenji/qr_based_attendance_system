<script lang="ts">
	import { goto } from '$app/navigation';
	import { onDestroy, onMount } from 'svelte';
	import { Routes } from '$lib/shared/constants/routes';
	import { toAuthMessage } from '$lib/features/auth/errors';
	import { requestOtp } from '$lib/features/auth/service';
	import { authState, defaultRouteFor, doRegister, createOtpWindow } from '$lib/features/auth/store.svelte';
	import { SECURITY_QUESTIONS } from '$lib/features/auth/security';
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

	// Mirrors shared/validators.py:password_strength plus the 8-char minimum.
	// The symbol rule excludes whitespace, because the backend counts a symbol as
	// "not alphanumeric and not a space" — a bare space must not satisfy it.
	const passwordChecks = $derived({
		length: password.length >= 8,
		upper: /[A-Z]/.test(password),
		lower: /[a-z]/.test(password),
		number: /\d/.test(password),
		symbol: /[^A-Za-z0-9\s]/.test(password),
	});
	const passwordOk = $derived(
		passwordChecks.length && passwordChecks.upper && passwordChecks.lower &&
		passwordChecks.number && passwordChecks.symbol
	);

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

					<button class="btn-primary" type="submit" disabled={submitting}>
						{submitting ? 'Sending code…' : 'Send verification code'}
					</button>
				</form>
			{:else if step === 'otp'}
				<form onsubmit={continueToDetails}>
					<OtpInput bind:digits={otp} bind:this={otpInput} disabled={submitting} onChange={clearError} />

					<OtpCodeRow win={win} busy={submitting} onresend={resend} />

					<button class="btn-primary" type="submit" disabled={submitting}>Continue</button>
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

					<button class="btn-primary" type="submit" disabled={submitting || authState.loading}>
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
		background: var(--bg-page);
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 2rem;
		font-family: system-ui, sans-serif;
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
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.steps li {
		padding: 0.1875rem 0.625rem;
		border-radius: 999px;
		background: var(--border);
	}

	.steps li.active {
		background: var(--brand);
		color: var(--on-brand);
		font-weight: 600;
	}

	.steps li.done {
		background: var(--success-bg);
		color: var(--success);
	}

	.logo-tile {
		width: 52px;
		height: 52px;
		background: var(--brand);
		border-radius: 14px;
		display: flex;
		align-items: center;
		justify-content: center;
		margin: 0 auto 1rem;
		color: var(--on-brand);
	}

	.logo-tile img {
		width: 34px;
		height: 34px;
		display: block;
	}

	h1 {
		font-family: system-ui, sans-serif;
		font-size: 1.625rem;
		font-weight: 700;
		color: var(--brand);
		margin: 0 0 0.25rem;
	}

	.subtitle {
		color: var(--text-muted);
		font-size: 0.875rem;
		margin: 0;
	}

	.subtitle strong {
		color: var(--brand);
	}

	.card {
		background: var(--bg-card);
		padding: 2rem;
		border-radius: 12px;
		box-shadow: var(--shadow-sm);
	}

	.error-banner {
		background: var(--danger-bg);
		border: 1px solid var(--danger-bg);
		border-radius: 8px;
		padding: 0.625rem 0.875rem;
		margin-bottom: 1.25rem;
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
		padding: 0.625rem 0.875rem;
		border: 1.5px solid var(--border-strong);
		border-radius: 8px;
		background: var(--bg-card);
		font-size: 0.9375rem;
		font-family: inherit;
		color: var(--brand);
		cursor: pointer;
		outline: none;
		transition: border-color 0.15s;
	}

	.dropdown-toggle:hover {
		border-color: var(--text-muted);
	}

	.dropdown-toggle.placeholder {
		color: var(--text-muted);
	}

	.dropdown-toggle:focus-visible {
		border-color: var(--accent);
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
		border: 1.5px solid var(--border-strong);
		border-radius: 8px;
		box-shadow: 0 8px 24px rgba(0, 0, 0, 0.1);
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
		border-radius: 6px;
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

	.btn-primary:hover:not(:disabled) {
		background: var(--brand-hover);
	}

	.btn-primary:disabled {
		opacity: 0.6;
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
	}
</style>
