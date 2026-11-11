<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { Routes } from '$lib/shared/constants/routes';
	import { toAuthMessage } from '$lib/features/auth/errors';
	import type { User } from '$lib/shared/types';
	import {
		authState,
		defaultRouteFor,
		doChangePassword,
		doLogin,
		doLoginOtpResend,
		doLoginOtpVerify,
		doMfaVerify,
	} from '$lib/features/auth/store.svelte';
	import { createOtpWindow } from '$lib/features/auth/store.svelte';
	import { evaluatePassword, isPasswordStrong } from '$lib/shared/utils/password';
	import OtpInput from '$lib/components/OtpInput.svelte';
	import OtpCodeRow from '$lib/components/OtpCodeRow.svelte';
	import Turnstile from '$lib/components/Turnstile.svelte';
	import { APIError, isMockMode } from '$lib/api/client';
import { SECURITY_QUESTIONS } from '$lib/features/auth/security';

	// 'credentials' -> 'login-otp' (mandatory OTP) -> 'mfa' (admins with MFA
	// enabled, chained after the OTP) -> 'change-password' (temporary password).
	type Stage = 'credentials' | 'login-otp' | 'mfa' | 'change-password';
	let stage = $state<Stage>('credentials');

	let email = $state('');
	let password = $state('');
	let showPwd = $state(false);
	let mfaCode = $state('');
	let otp = $state<string[]>(['', '', '', '', '', '']);
	let resending = $state(false);
	let redirecting = $state(false);
	let redirectTimer: ReturnType<typeof setTimeout> | null = $state(null);
	let otpRound = $state(0);
let currentPassword = $state('');
let newPassword = $state('');
let confirmPassword = $state('');
let securityQuestion = $state('');
let securityAnswer = $state('');
let error = $state('');

	let passwordInput: HTMLInputElement | undefined = $state();
	let mfaInput: HTMLInputElement | undefined = $state();
	let otpInput: import('$lib/components/OtpInput.svelte').default | undefined = $state();
	let turnstile: import('$lib/components/Turnstile.svelte').default | undefined = $state();

	// Shared OTP window: remaining = code validity (display), resendIn = cooldown gate
	const win = createOtpWindow();

	onMount(() => {
		const reason = page.url.searchParams.get('reason');
		const flag = typeof sessionStorage !== 'undefined' ? sessionStorage.getItem('attendly_signed_out_elsewhere') : null;
		if (reason === 'signed_out_elsewhere' || flag) {
			error = 'You were signed out in another tab.';
			if (flag) sessionStorage.removeItem('attendly_signed_out_elsewhere');
		}
	});

	onDestroy(() => {
		win.stop();
		if (redirectTimer) clearTimeout(redirectTimer);
	});

	// Same policy the backend enforces in shared/validators.password_strength
	// (see lib/shared/utils/password.ts) — derived here so the checklist can
	// never drift from the other signup/recovery forms.
	const passwordReq = $derived(evaluatePassword(newPassword));
	const passwordOk = $derived(isPasswordStrong(passwordReq));
	const passwordsMatch = $derived(newPassword === confirmPassword);

	const describe = (e: unknown, fallback: string) => toAuthMessage(e, fallback);

	// Dismiss a stale failure as soon as the user starts correcting the form,
	// so the banner never reads as "still broken" while they type.
	const clearError = () => {
		if (error) error = '';
	};

	const handleLogin = async (event: SubmitEvent) => {
		event.preventDefault();
		error = '';

		if (!email.trim() || !password) {
			error = 'Email and password are required.';
			return;
		}

		try {
			const user = await doLogin(email, password, turnstile?.getToken() ?? null);
			if (!user) {
				// Password accepted; continue with the step the backend asked for.
				const otpStep = authState.otpPending;
				stage = otpStep ? 'login-otp' : 'mfa';
				otp = ['', '', '', '', '', ''];
				mfaCode = '';
				if (otpStep) {
					win.restart();
				}
				return;
			}
			await finishLogin(user);
		} catch (e: unknown) {
			error = describe(e, 'Login failed. Please try again.');
			// A rejected/expired challenge needs a fresh one before retry.
			if (e instanceof APIError && e.code === 'invalid_captcha') turnstile?.reset();
			// Keep the email so retry is one field, not two; clear the secret
			// and focus it so the next attempt starts in the right place.
			password = '';
			passwordInput?.focus();
		}
	};

	const handleLoginOtp = async (event: SubmitEvent) => {
		event.preventDefault();
		error = '';

		if (otp.some((d) => !d)) {
			error = 'Enter the 6-digit code from your email.';
			return;
		}

		try {
			const user = await doLoginOtpVerify(otp.join(''));
			if (!user) {
				// OTP verified, MFA still required (admins with MFA enabled).
				stage = 'mfa';
				mfaCode = '';
				return;
			}
			await finishLogin(user);
		} catch (e: unknown) {
			error = describe(e, 'Verification failed. Please try again.');
			// Single-use code: never leave a rejected one in the field.
			otp = ['', '', '', '', '', ''];
			otpInput?.focus();
		}
	};

	const scheduleRedirect = () => {
		if (redirectTimer) clearTimeout(redirectTimer);
		redirecting = true;
		redirectTimer = setTimeout(() => {
			redirecting = false;
			redirectTimer = null;
			backToCredentials();
		}, 2500);
	};

	const handleResendOtp = async () => {
		error = '';
		if (win.remaining <= 0) {
			error = 'The code has expired. Redirecting to sign in…';
			scheduleRedirect();
			return;
		}
		resending = true;
		try {
			await doLoginOtpResend();
			otp = ['', '', '', '', '', ''];
			otpRound += 1;
			win.restart();
			otpInput?.focus();
		} catch (e: unknown) {
			if (e instanceof APIError && e.code === 'invalid_credentials') {
				error = 'Your sign-in session expired. Redirecting to sign in…';
				scheduleRedirect();
			} else {
				error = describe(e, 'Could not resend the code. Please try again.');
			}
		} finally {
			resending = false;
		}
	};

	const handleMfa = async (event: SubmitEvent) => {
		event.preventDefault();
		error = '';

		if (!mfaCode.trim()) {
			error = 'Enter the 6-digit code from your authenticator app.';
			return;
		}

		try {
			const user = await doMfaVerify(mfaCode);
			await finishLogin(user);
		} catch (e: unknown) {
			error = describe(e, 'Verification failed. Please try again.');
			// Single-use code: never leave a rejected one in the field.
			mfaCode = '';
			mfaInput?.focus();
		}
	};

	const handleChangePassword = async (event: SubmitEvent) => {
		event.preventDefault();
		error = '';

		if (!currentPassword) {
			error = 'Enter your current password.';
			return;
		}
		if (!passwordOk) {
			error = 'New password does not meet all requirements.';
			return;
		}
		if (!passwordsMatch) {
			error = 'Passwords do not match.';
			return;
		}

		const isAdminTemp = authState.user?.role === 'admin';
		if (isAdminTemp) {
			if (!securityQuestion) {
				error = 'Please choose a security question';
				return;
			}
			if (!securityAnswer.trim()) {
				error = 'Security answer is required';
				return;
			}
		}

		try {
			if (isAdminTemp) {
				await doChangePassword(currentPassword, newPassword, securityQuestion, securityAnswer.trim());
			} else {
				await doChangePassword(currentPassword, newPassword);
			}
			await finishLogin(authState.user);
		} catch (e: unknown) {
			error = describe(e, 'Password change failed.');
		}
	};

	const finishLogin = async (user: User | null) => {
		if (authState.mustChangePassword) {
			stage = 'change-password';
			return;
		}
		await goto(resolvePostLoginRoute(user));
	};

	// Where to send a user after login, honoring the portal intent the auth
	// gate stored in ?next=. Strict allowlist + role match: anything foreign
	// (absolute URL, protocol-relative, encoded slashes, non-portal path) or
	// any portal that does not belong to this role falls back to the role
	// default, so a stale or tampered ?next= can neither open-redirect nor
	// land a user in another portal.
	const resolvePostLoginRoute = (user: User | null): string => {
		const fallback = defaultRouteFor(user);
		const raw = page.url.searchParams.get('next');
		if (!raw) return fallback;
		let path: string;
		try {
			path = decodeURIComponent(raw);
		} catch {
			return fallback;
		}
		if (!path.startsWith('/') || path.startsWith('//') || path.includes('\\')) return fallback;
		if (/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(path)) return fallback;
		const qIndex = path.indexOf('?');
		const hashIndex = path.indexOf('#');
		const end = Math.min(qIndex === -1 ? path.length : qIndex, hashIndex === -1 ? path.length : hashIndex);
		const pathname = path.slice(0, end);
		if (pathname.includes('%') || pathname.includes('%2f') || pathname.includes('%2F')) return fallback;
		const isPortalPath =
			pathname === '/student' ||
			pathname.startsWith('/student/') ||
			pathname === '/professor' ||
			pathname.startsWith('/professor/') ||
			pathname === '/admin' ||
			pathname.startsWith('/admin/');
		if (!isPortalPath) return fallback;
		switch (user?.role) {
			case 'student':
				return pathname.startsWith('/student/') || pathname === '/student' ? path : fallback;
			case 'professor':
				return pathname.startsWith('/professor/') || pathname === '/professor' ? path : fallback;
			case 'admin':
			case 'super_admin':
				return pathname.startsWith('/admin') ? path : fallback;
			default:
				return fallback;
		}
	};

	const backToCredentials = () => {
		stage = 'credentials';
		error = '';
		otp = ['', '', '', '', '', ''];
		mfaCode = '';
		win.stop();
	};
</script>

<main class="auth">
	<div class="wrapper">

		<div class="header">
			<div class="logo-tile"><img src="/qr-attend-logo.svg" alt="Attendly" /></div>
			<p class="kicker">Secure sign-in</p>
			{#if stage === 'credentials'}
				<h1>Log In</h1>
				<p class="subtitle">Enter your registered email and password.</p>
			{:else if stage === 'login-otp'}
				<h1>Verify It's You</h1>
				<p class="subtitle">Enter the 6-digit code sent to <strong>{email}</strong>.</p>
			{:else if stage === 'mfa'}
				<h1>Two-Factor Authentication</h1>
				<p class="subtitle">Enter the 6-digit code for {email}.</p>
			{:else}
				<h1>Set a New Password</h1>
				<p class="subtitle">Your temporary password must be replaced before you continue.</p>
			{/if}
		</div>

		<div class="card" class:redirecting={redirecting}>
			{#if isMockMode()}
				<p class="hint mock-hint" data-testid="mock-accounts">
					Mock mode — sign in with any password as
					<span class="mono">superadmin@isu.edu.ph</span>,
					<span class="mono">admin@isu.edu.ph</span>,
					<span class="mono">maria.c.delacruz@isu.edu.ph</span>, or
					<span class="mono">jose.p.rizal@isu.edu.ph</span>.
				</p>
			{/if}
			{#if error}
				<div class="error-banner" class:redirecting={redirecting} role="alert">{error}</div>
			{/if}

			{#if stage === 'credentials'}
				<form onsubmit={handleLogin}>
					<div class="field">
						<label class="form-label" for="email">Email</label>
						<input class="form-input" id="email" type="email" required
							autocomplete="email" placeholder="universityemail@isu.edu.ph"
							value={email}
							oninput={(e) => { email = (e.target as HTMLInputElement).value; clearError(); }} />
					</div>

					<div class="field">
						<label class="form-label" for="password">Password</label>
						<div class="pwd-wrap">
							<input class="form-input" id="password" type={showPwd ? 'text' : 'password'}
								required autocomplete="current-password" placeholder="••••••••••••"
								value={password}
								bind:this={passwordInput}
								oninput={(e) => { password = (e.target as HTMLInputElement).value; clearError(); }}
								style="padding-right: 2.5rem;" />
							<button type="button" class="pwd-toggle"
								onclick={() => { showPwd = !showPwd; }}
								aria-label={showPwd ? 'Hide password' : 'Show password'}>
								{#if showPwd}
									<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" /><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" /><path d="M14.12 14.12a3 3 0 1 1-4.24-4.24" /><line x1="1" y1="1" x2="23" y2="23" /></svg>
								{:else}
									<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></svg>
								{/if}
							</button>
						</div>
					</div>

					<Turnstile bind:this={turnstile} />

					<button class="btn-primary" type="submit" disabled={authState.loading} aria-busy={authState.loading}>
						{authState.loading ? 'Signing in…' : 'Login'}
					</button>
				</form>
			{:else if stage === 'login-otp'}
				<form onsubmit={handleLoginOtp}>
					{#key otpRound}
						<OtpInput bind:digits={otp} bind:this={otpInput} disabled={authState.loading} onChange={clearError} />
					{/key}

					<OtpCodeRow win={win} busy={resending || redirecting} onresend={handleResendOtp} />

					<button class="btn-primary" type="submit" disabled={authState.loading || redirecting} aria-busy={authState.loading || redirecting}>
						{authState.loading ? 'Verifying…' : 'Verify'}
					</button>
					<button type="button" class="link-btn block" onclick={backToCredentials} disabled={redirecting}>
						Back to sign in
					</button>
				</form>
			{:else if stage === 'mfa'}
				<form onsubmit={handleMfa}>
					<div class="field">
						<label class="form-label" for="mfa">Authenticator code</label>
						<input class="form-input mono" id="mfa" required inputmode="numeric"
							autocomplete="one-time-code" maxlength="16" placeholder="000000"
							value={mfaCode}
							bind:this={mfaInput}
							oninput={(e) => { mfaCode = (e.target as HTMLInputElement).value; clearError(); }} />
						<p class="hint">Enter the 6-digit TOTP, or one of your backup codes
							(formatted <span class="mono">XXXX-XXXX-XX</span>).</p>
					</div>

					<button class="btn-primary" type="submit" disabled={authState.loading} aria-busy={authState.loading}>
						{authState.loading ? 'Verifying…' : 'Verify'}
					</button>
					<button type="button" class="link-btn block" onclick={backToCredentials}>
						Back to sign in
					</button>
				</form>
			{:else}
				<form onsubmit={handleChangePassword}>
					<div class="field">
						<label class="form-label" for="current-password">Current password</label>
						<input class="form-input" id="current-password" type="password" required
							autocomplete="current-password" value={currentPassword}
							oninput={(e) => { currentPassword = (e.target as HTMLInputElement).value; clearError(); }} />
					</div>

					<div class="field">
						<label class="form-label" for="new-password">New password</label>
						<input class="form-input" id="new-password" type="password" required
							autocomplete="new-password" value={newPassword}
							oninput={(e) => { newPassword = (e.target as HTMLInputElement).value; clearError(); }} />
					</div>

					<ul class="req-list">
						<li class:met={passwordReq.length}>At least 8 characters</li>
						<li class:met={passwordReq.upper}>One uppercase letter</li>
						<li class:met={passwordReq.lower}>One lowercase letter</li>
						<li class:met={passwordReq.number}>One number</li>
						<li class:met={passwordReq.symbol}>One symbol</li>
					</ul>

					<div class="field">
						<label class="form-label" for="confirm-password">Confirm new password</label>
						<input class="form-input" id="confirm-password" type="password" required
							autocomplete="new-password" value={confirmPassword}
							oninput={(e) => { confirmPassword = (e.target as HTMLInputElement).value; clearError(); }} />
						{#if confirmPassword && !passwordsMatch}
							<p class="hint warn">Passwords do not match.</p>
						{/if}
					</div>

					{#if authState.user?.role === 'admin'}
						<div class="field">
							<label class="form-label" for="security-question">Security question</label>
							<select class="form-input" id="security-question" bind:value={securityQuestion}>
								<option value="" disabled>Choose a question…</option>
								{#each SECURITY_QUESTIONS as q (q)}
									<option value={q}>{q}</option>
								{/each}
							</select>
						</div>

						<div class="field">
							<label class="form-label" for="security-answer">Security answer</label>
							<input class="form-input" id="security-answer" type="text"
								autocomplete="off" placeholder="Your answer" bind:value={securityAnswer} />
						</div>
					{/if}

					<button class="btn-primary" type="submit" disabled={authState.loading} aria-busy={authState.loading}>
						{authState.loading ? 'Saving…' : 'Set password and continue'}
					</button>
				</form>
			{/if}

			{#if stage === 'credentials'}
				<div class="links">
					<button type="button" class="link-btn"
						onclick={() => goto(Routes.FORGOT_PASSWORD)}>Forgot Password?</button>
					<div class="divider">
						<div class="divider-line"></div>
						<span class="divider-text">OR</span>
						<div class="divider-line"></div>
					</div>
					<span class="register-hint">
						Don't have an account?
						<button type="button" class="link-btn"
							onclick={() => goto(Routes.REGISTER)}>Register</button>
					</span>
				</div>
			{/if}
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
		margin-bottom: 1.75rem;
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
		font-size: 1.5rem;
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

	.card.redirecting {
		opacity: 0.4;
		transition: opacity 0.3s ease;
	}

	.card {
		background: var(--bg-card);
		padding: 2rem;
		border: 1px solid var(--border);
		border-radius: 16px;
		box-shadow: var(--shadow-sm);
	}


	.error-banner.redirecting {
		font-size: 0.9rem;
		font-weight: 700;
		text-align: center;
		background: color-mix(in srgb, var(--danger) 18%, var(--bg-card));
		border-color: var(--danger);
	}

	.error-banner {
		border: 1px solid color-mix(in srgb, var(--danger) 22%, transparent);
		border-left: 3px solid var(--danger);
		border-radius: 8px;
		padding: 0.625rem 0.875rem;
		margin-bottom: 1.25rem;
		color: var(--danger);
		font-size: 0.8125rem;
		line-height: 1.45;
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

	.form-input.mono {
		font-family: var(--font-data);
		font-size: 1.125rem;
		letter-spacing: 0.2em;
		text-align: center;
	}

	.hint {
		color: var(--text-muted);
		font-size: 0.75rem;
		line-height: 1.5;
		margin: 0.375rem 0 0;
	}

	.hint.warn {
		color: var(--danger);
	}

	.mock-hint {
		font-size: 0.8125rem;
		line-height: 1.6;
		background: var(--bg-muted);
		border: 1px dashed var(--border-strong);
		border-radius: 10px;
		padding: 0.625rem 0.875rem;
		margin: 0 0 1rem;
	}

	.mock-hint .mono {
		font-family: var(--font-data);
		font-size: 0.75rem;
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
		list-style: none;
		padding: 0;
		margin: -0.5rem 0 1.25rem;
		font-size: 0.75rem;
		color: var(--text-muted);
		display: grid;
		gap: 0.1875rem;
	}

	.req-list li::before {
		content: '✘ ';
	}

	.req-list li.met {
		color: var(--success);
	}

	.req-list li.met::before {
		content: '✔ ';
	}

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
		margin-bottom: 1rem;
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

	.links {
		text-align: center;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
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

	.link-btn.block {
		display: block;
		width: 100%;
	}

	.link-btn:hover {
		text-decoration: underline;
	}

	.divider {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.divider-line {
		flex: 1;
		height: 1px;
		background: var(--border-strong);
	}

	.divider-text {
		color: var(--text-muted);
		font-size: 0.75rem;
	}

	.register-hint {
		font-size: 0.8125rem;
		color: var(--text-muted);
	}

	.link-btn:hover,
	.link-btn:focus-visible {
		color: var(--accent-hover);
		text-decoration: underline;
		text-underline-offset: 2px;
	}

	@media (prefers-reduced-motion: reduce) {
		.form-input,
		.btn-primary {
			transition: none;
		}

		.btn-primary:hover:not(:disabled) {
			transform: none;
		}
	}
</style>