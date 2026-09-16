<script lang="ts">
	import { goto } from '$app/navigation';
	import { onDestroy } from 'svelte';
	import { loadSecurityQA, DEFAULT_QUESTION, DEFAULT_ANSWER } from '$lib/features/auth/security';

	let step = $state(1);
	let email = $state('');
	let captcha = $state('');
	let answer = $state('');
	let otp = $state<string[]>(['', '', '', '', '', '']);
	let newPwd = $state('');
	let confirmPwd = $state('');
	let showNewPwd = $state(false);
	let showConfirmPwd = $state(false);
	let attempts = $state(3);
	let error = $state('');

	let securityQuestion: string = $state(DEFAULT_QUESTION);
	let securityAnswer: string = $state(DEFAULT_ANSWER);

	let captchaCode = $state('2D8MQA');

	let otpInputs: HTMLInputElement[] = $state([]);
	let countdown = $state(300);
	let intervalId: ReturnType<typeof setInterval> | null = null;

	const countdownText = $derived.by(() => {
		const m = Math.floor(countdown / 60);
		const s = countdown % 60;
		return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
	});

	const passwordsMatch = $derived(
		newPwd !== '' && confirmPwd !== '' ? newPwd === confirmPwd : null
	);

	const req = $derived({
		length: newPwd.length >= 8,
		upper: /[A-Z]/.test(newPwd),
		lower: /[a-z]/.test(newPwd),
		number: /\d/.test(newPwd),
		symbol: /[^A-Za-z0-9]/.test(newPwd),
	});

	const allReqsMet = $derived(req.length && req.upper && req.lower && req.number && req.symbol);
	let success = $state(false);

	onDestroy(() => {
		if (intervalId) clearInterval(intervalId);
	});

	function refreshCaptcha() {
		const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
		let code = '';
		for (let i = 0; i < 6; i++) {
			code += chars[Math.floor(Math.random() * chars.length)];
		}
		captchaCode = code;
	}

	function startCountdown() {
		if (intervalId) clearInterval(intervalId);
		countdown = 300;
		intervalId = setInterval(() => {
			countdown -= 1;
			if (countdown <= 0) {
				if (intervalId) clearInterval(intervalId);
				intervalId = null;
			}
		}, 1000);
	}

	function handleStep1() {
		if (!email) {
			error = 'Email is required';
			return;
		}
		if (captcha.toUpperCase() !== captchaCode) {
			error = 'Captcha incorrect';
			return;
		}
		error = '';
		const saved = loadSecurityQA(email);
		securityQuestion = saved?.question ?? DEFAULT_QUESTION;
		securityAnswer = saved?.answer ?? DEFAULT_ANSWER;
		step = 2;
	}

	function handleStep2() {
		if (!answer) {
			error = 'Answer is required';
			return;
		}
		if (answer.toLowerCase() !== securityAnswer.toLowerCase()) {
			attempts -= 1;
			if (attempts <= 0) {
				error = 'Account temporarily locked due to too many failed attempts.';
				return;
			}
			error = `Wrong answer. ${attempts} attempt${attempts !== 1 ? 's' : ''} remaining.`;
			return;
		}
		error = '';
		step = 3;
		startCountdown();
	}

	function handleStep3() {
		if (otp.some((d) => !d)) {
			error = 'Enter all 6 digits';
			return;
		}
		error = '';
		step = 4;
	}

	function handleStep4() {
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
		error = '';
		success = true;
		setTimeout(() => goto('/auth/login'), 1500);
	}

	function onOtpInput(i: number, value: string) {
		const v = value.replace(/\D/g, '').slice(-1);
		if (v) error = '';
		otp[i] = v;
		if (v && i < 5) otpInputs[i + 1]?.focus();
	}

	function onOtpKeydown(i: number, e: KeyboardEvent) {
		if (e.key === 'Backspace' && otp[i] === '' && i > 0) {
			otpInputs[i - 1]?.focus();
		}
	}

	function resend() {
		startCountdown();
		error = '';
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
					<p class="step-sub">Step 1 of 4 · Enter your email</p>

					{#if error}
						<div class="error-banner">⚠️ {error}</div>
					{/if}

					<div class="field">
						<label class="form-label" for="fp-email">Email</label>
						<input class="form-input" id="fp-email" type="email" placeholder="your@email.com"
							value={email} oninput={(e) => { email = (e.target as HTMLInputElement).value; }} />
					</div>

					<div class="field">
						<label class="form-label" for="fp-captcha">Captcha</label>
						<div class="captcha-row">
							<div class="captcha-display">{captchaCode}</div>
							<button class="captcha-refresh" onclick={refreshCaptcha}>↻</button>
						</div>
						<input class="form-input" id="fp-captcha" placeholder="Enter code above"
							value={captcha} oninput={(e) => { captcha = (e.target as HTMLInputElement).value; }} />
					</div>

					<button class="btn-primary" onclick={handleStep1}>Continue</button>
					<button class="back-btn" onclick={() => goto('/auth/login')}>← Back to Login</button>
				</div>
			{:else if step === 2}
				<div class="step-panel">
					<h2>Verify Identity</h2>
					<p class="step-sub">Step 2 of 4 · Security question</p>

					{#if error}
						<div class="error-banner">⚠️ {error}</div>
					{/if}

					<div class="question-panel">"{securityQuestion}"</div>

					<div class="field">
						<label class="form-label" for="fp-answer">Your Answer</label>
						<input class="form-input" id="fp-answer" placeholder="Your answer..."
							value={answer} oninput={(e) => { answer = (e.target as HTMLInputElement).value; }} />
					</div>

					{#if attempts < 3}
						<div class="warning-banner">
							⚠️ {attempts} attempt{attempts !== 1 ? 's' : ''} remaining (3 max — then lock)
						</div>
					{/if}

					<button class="btn-primary" onclick={handleStep2}>Verify</button>
				</div>
			{:else if step === 3}
				<div class="step-panel">
					<h2>One-Time Code</h2>
					<p class="step-sub">Step 3 of 4 · Check your email</p>
					<p class="step-sub">A 6-digit code was sent to <strong>{email}</strong></p>

					{#if error}
						<div class="error-banner">⚠️ {error}</div>
					{/if}

					<div class="otp-row">
						{#each otp as digit, i}
							<input class="otp-input" maxlength="1" inputmode="numeric"
								aria-label={`Digit ${i + 1}`} value={digit}
								bind:this={otpInputs[i]}
								oninput={(e) => onOtpInput(i, (e.target as HTMLInputElement).value)}
								onkeydown={(e) => onOtpKeydown(i, e)} />
						{/each}
					</div>

					<div class="expiry">
						Expires in <strong class={countdown <= 0 ? 'expired' : ''}>{countdownText}</strong> ·
						<button class="resend-btn" onclick={resend} disabled={countdown > 0 && countdown < 300}>Resend code</button>
					</div>

					<button class="btn-primary" onclick={handleStep3}>Verify</button>
				</div>
			{:else}
				<div class="step-panel">
					<h2>New Password</h2>
					<p class="step-sub">Step 4 of 4 · Set your new password</p>

					{#if error}
						<div class="error-banner">⚠️ {error}</div>
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
						<div class="success-banner">✓ Password reset successful. Redirecting to login…</div>
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
							{passwordsMatch ? '✔ Passwords match' : '✗ Passwords do not match'}
						</div>
					{/if}

					<button class="btn-primary" onclick={handleStep4} disabled={success}>
						{success ? 'Success!' : 'Reset Password'}
					</button>
				</div>
			{/if}
		</div>
	</div>
</main>

<style>
	main.auth {
		min-height: 100vh;
		background: #f5f7fb;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 2rem;
		font-family: 'DM Sans', system-ui, sans-serif;
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
		background: linear-gradient(135deg, #1e3a5f, #0d9488);
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
		font-family: 'DM Sans', sans-serif;
		font-size: 1.375rem;
		font-weight: 700;
		color: #1e3a5f;
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
		background: #f3f4f6;
		color: #6b7280;
		flex-shrink: 0;
	}

	.step-dot.active {
		background: #2563eb;
		color: white;
	}

	.step-dot.done {
		background: #0d9488;
		color: white;
	}

	.step-line {
		width: 24px;
		height: 2px;
		background: #d1d5db;
	}

	.step-line.done {
		background: #0d9488;
	}

	.card {
		background: white;
		padding: 2rem;
		border-radius: 12px;
		box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
	}

	h2 {
		font-family: 'DM Sans', sans-serif;
		font-size: 1.375rem;
		font-weight: 700;
		color: #1e3a5f;
		margin: 0 0 0.25rem;
	}

	.step-sub {
		color: #6b7280;
		font-size: 0.8125rem;
		margin: 0 0 1.5rem;
	}

	.step-sub strong {
		color: #1e3a5f;
	}

	.error-banner {
		background: #fee2e2;
		border: 1px solid #fca5a5;
		border-radius: 8px;
		padding: 0.625rem 0.875rem;
		margin-bottom: 1rem;
		color: #dc2626;
		font-size: 0.8125rem;
	}

	.field {
		margin-bottom: 1.25rem;
	}

	.form-label {
		display: block;
		font-weight: 600;
		font-size: 0.8125rem;
		color: #374151;
		margin-bottom: 0.375rem;
	}

	.form-input {
		width: 100%;
		padding: 0.625rem 0.875rem;
		border: 1.5px solid #d1d5db;
		border-radius: 8px;
		font-size: 0.9375rem;
		font-family: inherit;
		outline: none;
		transition: border-color 0.15s;
	}

	.form-input:focus {
		border-color: #2563eb;
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
		color: #6b7280;
		padding: 0;
		display: flex;
		align-items: center;
	}

	.pwd-toggle:hover {
		color: #374151;
	}

	.captcha-row {
		display: flex;
		gap: 0.5rem;
		margin-bottom: 0.5rem;
	}

	.captcha-display {
		flex: 1;
		background: linear-gradient(135deg, #f0f4f8, #e2e8f0);
		border: 1.5px solid #d1d5db;
		border-radius: 8px;
		padding: 0.625rem;
		display: flex;
		align-items: center;
		justify-content: center;
		text-align: center;
		font-family: 'JetBrains Mono', monospace;
		font-weight: 700;
		font-size: 1.125rem;
		letter-spacing: 0.25em;
		color: #1e3a5f;
		user-select: none;
	}

	.captcha-refresh {
		background: #f3f4f6;
		border: 1.5px solid #d1d5db;
		border-radius: 8px;
		width: 44px;
		cursor: pointer;
		font-size: 1.125rem;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
	}

	.captcha-refresh:hover {
		background: #e5e7eb;
	}

	.question-panel {
		background: #f8fafc;
		border: 1px solid #d1d5db;
		border-radius: 8px;
		padding: 0.875rem;
		margin-bottom: 1rem;
		font-size: 0.875rem;
		color: #1e3a5f;
		font-style: italic;
		font-weight: 500;
	}

	.warning-banner {
		background: #fff7ed;
		border: 1px solid #fed7aa;
		border-radius: 8px;
		padding: 0.5rem 0.75rem;
		margin-bottom: 1rem;
		color: #c2410c;
		font-size: 0.8rem;
	}

	.otp-row {
		display: flex;
		gap: 0.5rem;
		justify-content: center;
		margin-bottom: 1rem;
	}

	.otp-input {
		width: 46px;
		height: 52px;
		text-align: center;
		font-size: 1.25rem;
		font-family: 'JetBrains Mono', monospace;
		font-weight: 700;
		color: #1e3a5f;
		border: 1.5px solid #d1d5db;
		border-radius: 8px;
		outline: none;
		transition: border-color 0.15s;
		background: white;
	}

	.otp-input:focus {
		border-color: #2563eb;
	}

	.expiry {
		text-align: center;
		color: #6b7280;
		font-size: 0.8125rem;
		margin-bottom: 1.25rem;
	}

	.expiry strong {
		color: #1e3a5f;
	}

	.expiry strong.expired {
		color: #dc2626;
	}

	.resend-btn {
		background: none;
		border: none;
		cursor: pointer;
		color: #0d9488;
		font-weight: 600;
		font-size: 0.8125rem;
		font-family: inherit;
		padding: 0;
	}

	.resend-btn:hover {
		text-decoration: underline;
	}

	.resend-btn:disabled {
		color: #6b7280;
		cursor: not-allowed;
		text-decoration: none;
	}

	.req-list {
		background: #f0f9ff;
		border: 1px solid #bae6fd;
		border-radius: 8px;
		padding: 0.625rem;
		margin-bottom: 1rem;
		font-size: 0.8rem;
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.req-item {
		color: #9ca3af;
	}

	.req-item.met {
		color: #16a34a;
	}

	.success-banner {
		background: #dcfce7;
		border: 1px solid #86efac;
		border-radius: 8px;
		padding: 0.625rem 0.875rem;
		margin-bottom: 1rem;
		color: #16a34a;
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
		background: #dcfce7;
		color: #16a34a;
	}

	.match-banner.no-match {
		background: #fee2e2;
		color: #dc2626;
	}

	.btn-primary {
		width: 100%;
		padding: 0.75rem;
		border: none;
		border-radius: 8px;
		background: #2563eb;
		color: white;
		font-size: 1rem;
		font-weight: 600;
		font-family: inherit;
		cursor: pointer;
	}

	.btn-primary:hover {
		background: #1d4ed8;
	}

	.btn-primary:disabled {
		background: #a5b4fc;
		cursor: not-allowed;
	}

	.back-btn {
		width: 100%;
		margin-top: 0.75rem;
		background: none;
		border: none;
		cursor: pointer;
		color: #6b7280;
		font-size: 0.8125rem;
		font-family: inherit;
		padding: 0;
	}

	.back-btn:hover {
		color: #374151;
	}
</style>