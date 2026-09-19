<script lang="ts">
	import { goto } from '$app/navigation';
	import { onDestroy, onMount } from 'svelte';
	import { SECURITY_QUESTIONS, saveSecurityQA } from '$lib/features/auth/security';

	let email = $state('');
	let password = $state('');
	let confirm = $state('');
	let role = $state<'student' | 'professor'>('student');
	let step = $state<'form' | 'security' | 'otp'>('form');
	let otp = $state<string[]>(['', '', '', '', '', '']);
	let error = $state('');

	let securityQuestion = $state('');
	let securityAnswer = $state('');
	let questionOpen = $state(false);
	let questionMenu: HTMLDivElement | undefined = $state();

	let showPwd = $state(false);
	let showConfirmPwd = $state(false);
	let roleOpen = $state(false);
	let roleMenu: HTMLDivElement | undefined = $state();

	onMount(() => {
		function onDocClick(e: MouseEvent) {
			if (!roleMenu?.contains(e.target as Node)) roleOpen = false;
			if (!questionMenu?.contains(e.target as Node)) questionOpen = false;
		}
		document.addEventListener('click', onDocClick);
		return () => document.removeEventListener('click', onDocClick);
	});

	let otpInputs: HTMLInputElement[] = $state([]);
	let countdown = $state(300);
	let intervalId: ReturnType<typeof setInterval> | null = null;

	const passwordChecks = $derived({
		length: password.length >= 8,
		upper: /[A-Z]/.test(password),
		lower: /[a-z]/.test(password),
		number: /\d/.test(password),
		symbol: /[^A-Za-z0-9]/.test(password),
	});
	const passwordOk = $derived(
		passwordChecks.length && passwordChecks.upper && passwordChecks.lower &&
		passwordChecks.number && passwordChecks.symbol
	);

	const countdownText = $derived.by(() => {
		const m = Math.floor(countdown / 60);
		const s = countdown % 60;
		return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
	});

	onDestroy(() => {
		if (intervalId) clearInterval(intervalId);
	});

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

	function handleRegister() {
		if (!email) {
			error = 'Email is required';
			return;
		}
		if (!passwordOk) {
			error = 'Password does not meet requirements';
			return;
		}
		if (password !== confirm) {
			error = 'Passwords do not match';
			return;
		}
		error = '';
		step = 'security';
	}

	function handleSecurity() {
		if (!securityQuestion) {
			error = 'Please select a security question';
			return;
		}
		if (!securityAnswer.trim()) {
			error = 'Security answer is required';
			return;
		}
		error = '';
		saveSecurityQA(email, securityQuestion, securityAnswer);
		step = 'otp';
		startCountdown();
	}

	function handleOtp() {
		if (otp.some((d) => !d)) {
			error = 'Enter all 6 digits';
			return;
		}
		goto('/auth/login');
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
		<div class="header">
			<div class="logo-tile"><img src="/qr-attend-logo.svg" alt="Attendly" /></div>
			{#if step === 'form'}
				<h1>Create Account</h1>
				<p class="subtitle">Email must match admin-seeded roster</p>
			{:else if step === 'security'}
				<h1>Security Question</h1>
				<p class="subtitle">Choose a question and answer to recover your account</p>
			{:else}
				<h1>Verify Email</h1>
				<p class="subtitle">A 6-digit code was sent to <strong>{email}</strong></p>
			{/if}
		</div>

		<div class="card">
			{#if error}
				<div class="error-banner">{error}</div>
			{/if}

			{#if step === 'form'}
				<div class="field">
					<label class="form-label" for="reg-email">Email</label>
					<input class="form-input" id="reg-email" type="email" placeholder="universityemail@isu.edu.ph"
						value={email} oninput={(e) => { email = (e.target as HTMLInputElement).value; }} />
				</div>

				<div class="field">
					<label class="form-label" for="reg-password">Password</label>
					<div class="pwd-wrap">
						<input class="form-input" id="reg-password" type={showPwd ? 'text' : 'password'}
							placeholder="••••••••" value={password}
							oninput={(e) => { password = (e.target as HTMLInputElement).value; }}
							style="padding-right: 2.5rem;" />
						<button class="pwd-toggle" onclick={() => { showPwd = !showPwd; }}
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
							placeholder="••••••••" value={confirm}
							oninput={(e) => { confirm = (e.target as HTMLInputElement).value; }}
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

				<div class="field">
					<label class="form-label" for="reg-role" id="reg-role-label">Role</label>
					<div class="dropdown" bind:this={roleMenu}>
						<button id="reg-role" class="dropdown-toggle" onclick={() => { roleOpen = !roleOpen; }}
							aria-haspopup="listbox" aria-expanded={roleOpen}>
							<span>{role === 'student' ? 'Student' : 'Professor'}</span>
							<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6" /></svg>
						</button>
						{#if roleOpen}
							<ul class="dropdown-menu" role="listbox" aria-labelledby="reg-role-label">
								<li>
									<button class="dropdown-item {role === 'student' ? 'selected' : ''}"
										onclick={() => { role = 'student'; roleOpen = false; }}>
										<span>Student</span>
										{#if role === 'student'}<span class="check">✓</span>{/if}
									</button>
								</li>
								<li>
									<button class="dropdown-item {role === 'professor' ? 'selected' : ''}"
										onclick={() => { role = 'professor'; roleOpen = false; }}>
										<span>Professor</span>
										{#if role === 'professor'}<span class="check">✓</span>{/if}
									</button>
								</li>
							</ul>
						{/if}
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

				<button class="btn-primary" onclick={handleRegister}>Continue</button>

				<div class="links">
					<span class="login-hint">
						Already have an account?
						<button class="link-btn" onclick={() => goto('/auth/login')}>Login</button>
					</span>
				</div>
			{:else if step === 'security'}
				<div class="field">
					<label class="form-label" for="reg-question" id="reg-question-label">Security Question</label>
					<div class="dropdown" bind:this={questionMenu}>
						<button id="reg-question" class="dropdown-toggle {!securityQuestion ? 'placeholder' : ''}"
							onclick={() => { questionOpen = !questionOpen; }}
							aria-haspopup="listbox" aria-expanded={questionOpen}>
							<span>{securityQuestion || 'Select a question…'}</span>
							<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6" /></svg>
						</button>
						{#if questionOpen}
							<ul class="dropdown-menu" role="listbox" aria-labelledby="reg-question-label">
								{#each SECURITY_QUESTIONS as q}
									<li>
										<button class="dropdown-item {securityQuestion === q ? 'selected' : ''}"
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
					<input class="form-input" id="reg-answer" placeholder="Your answer..."
						value={securityAnswer} oninput={(e) => { securityAnswer = (e.target as HTMLInputElement).value; }} />
				</div>

				<button class="btn-primary" onclick={handleSecurity}>Continue</button>
				<button class="back-btn" onclick={() => { step = 'form'; error = ''; }}>← Back</button>
			{:else}
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

				<button class="btn-primary" onclick={handleOtp}>Verify & Create Account</button>
				<button class="back-btn" onclick={() => { step = 'security'; error = ''; }}>← Back</button>
			{/if}
		</div>
	</div>
</main>

<style>
	main.auth {
		min-height: calc(100vh - 3.75rem);
		background: #f5f7fb;
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
		margin-bottom: 2rem;
	}

	.logo-tile {
		width: 52px;
		height: 52px;
		background: #1e3a5f;
		border-radius: 14px;
		display: flex;
		align-items: center;
		justify-content: center;
		margin: 0 auto 1rem;
		color: white;
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
		color: #1e3a5f;
		margin: 0 0 0.25rem;
	}

	.subtitle {
		color: #6b7280;
		font-size: 0.875rem;
		margin: 0;
	}

	.subtitle strong {
		color: #1e3a5f;
	}

	.card {
		background: white;
		padding: 2rem;
		border-radius: 12px;
		box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
	}

	.error-banner {
		background: #fee2e2;
		border: 1px solid #fca5a5;
		border-radius: 8px;
		padding: 0.625rem 0.875rem;
		margin-bottom: 1.25rem;
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
		border: 1.5px solid #d1d5db;
		border-radius: 8px;
		background: white;
		font-size: 0.9375rem;
		font-family: inherit;
		color: #1e3a5f;
		cursor: pointer;
		outline: none;
		transition: border-color 0.15s;
	}

	.dropdown-toggle:hover {
		border-color: #9ca3af;
	}

	.dropdown-toggle.placeholder {
		color: #9ca3af;
	}

	.dropdown-toggle:focus-visible {
		border-color: #2563eb;
	}

	.dropdown-menu {
		position: absolute;
		top: calc(100% + 4px);
		left: 0;
		right: 0;
		list-style: none;
		margin: 0;
		padding: 0.25rem;
		background: white;
		border: 1.5px solid #d1d5db;
		border-radius: 8px;
		box-shadow: 0 8px 24px rgba(0, 0, 0, 0.1);
		z-index: 10;
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
		color: #374151;
		cursor: pointer;
		text-align: left;
	}

	.dropdown-item:hover {
		background: #f3f4f6;
	}

	.dropdown-item.selected {
		color: #2563eb;
		font-weight: 600;
	}

	.check {
		color: #16a34a;
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
		color: #6b7280;
		padding: 0;
		display: flex;
		align-items: center;
	}

	.pwd-toggle:hover {
		color: #374151;
	}

	.req-list {
		background: #f0f9ff;
		border: 1px solid #bae6fd;
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
		color: #0369a1;
		margin-bottom: 0.25rem;
	}

	.req-item {
		color: #64748b;
		display: flex;
		gap: 0.375rem;
		align-items: center;
	}

	.req-item.met {
		color: #16a34a;
	}

	.otp-row {
		display: flex;
		gap: 0.5rem;
		justify-content: center;
		margin-bottom: 1.25rem;
	}

	.otp-input {
		width: 46px;
		height: 52px;
		text-align: center;
		font-size: 1.25rem;
		font-family: monospace;
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

	.btn-primary {
		width: 100%;
		padding: 0.75rem;
		border: none;
		border-radius: 8px;
		background: #1e3a5f;
		color: white;
		font-size: 1rem;
		font-weight: 600;
		font-family: inherit;
		cursor: pointer;
	}

	.btn-primary:hover {
		background: #16324f;
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

	.links {
		text-align: center;
		margin-top: 1rem;
		font-size: 0.8125rem;
		color: #6b7280;
	}

	.link-btn {
		background: none;
		border: none;
		cursor: pointer;
		color: #0d9488;
		font-size: 0.8125rem;
		font-weight: 600;
		font-family: inherit;
		padding: 0;
	}

	.link-btn:hover {
		text-decoration: underline;
	}
</style>