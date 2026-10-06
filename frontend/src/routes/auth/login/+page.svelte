<script lang="ts">
	import { goto } from '$app/navigation';
	import { Routes } from '$lib/shared/constants/routes';
	import { toAuthMessage } from '$lib/features/auth/errors';
	import type { User } from '$lib/shared/types';
	import {
		authState,
		defaultRouteFor,
		doChangePassword,
		doLogin,
		doMfaVerify,
	} from '$lib/features/auth/store.svelte';
	import LoadingSpinner from '$lib/components/LoadingSpinner.svelte';
	import ErrorBoundary from '$lib/components/ErrorBoundary.svelte';
	import { isMockMode } from '$lib/api/client';

	// 'credentials' -> 'mfa' (when the account has MFA enabled) -> 'change-password'
	// (when an admin issued a temporary password).
	type Stage = 'credentials' | 'mfa' | 'change-password';
	let stage = $state<Stage>('credentials');

	let email = $state('');
	let password = $state('');
	let showPwd = $state(false);
	let mfaCode = $state('');
	let currentPassword = $state('');
	let newPassword = $state('');
	let confirmPassword = $state('');
	let error = $state('');

	// Same policy the backend enforces in shared/validators.password_strength:
	// 8+ chars with an uppercase, a lowercase, a digit and a symbol.
	const passwordReq = $derived({
		length: newPassword.length >= 8,
		upper: /[A-Z]/.test(newPassword),
		lower: /[a-z]/.test(newPassword),
		number: /\d/.test(newPassword),
		symbol: /[^A-Za-z0-9]/.test(newPassword),
	});
	const passwordOk = $derived(Object.values(passwordReq).every(Boolean));
	const passwordsMatch = $derived(newPassword === confirmPassword);

	const describe = (e: unknown, fallback: string) => toAuthMessage(e, fallback);

	const handleLogin = async (event: SubmitEvent) => {
		event.preventDefault();
		error = '';

		if (!email.trim() || !password) {
			error = 'Email and password are required.';
			return;
		}

		try {
			const user = await doLogin(email, password);
			if (!user) {
				// Password accepted, second factor required.
				stage = 'mfa';
				mfaCode = '';
				return;
			}
			await finishLogin(user);
		} catch (e: unknown) {
			error = describe(e, 'Login failed. Please try again.');
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

		try {
			await doChangePassword(currentPassword, newPassword);
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
		await goto(defaultRouteFor(user));
	};

	const backToCredentials = () => {
		stage = 'credentials';
		error = '';
		mfaCode = '';
	};
</script>

<main class="auth">
	<div class="wrapper">

		<div class="header">
			<div class="logo-tile"><img src="/qr-attend-logo.svg" alt="Attendly" /></div>
			{#if stage === 'credentials'}
				<h1>Log In</h1>
				<p class="subtitle">Enter your registered email and password.</p>
			{:else if stage === 'mfa'}
				<h1>Two-Factor Authentication</h1>
				<p class="subtitle">Enter the 6-digit code for {email}.</p>
			{:else}
				<h1>Set a New Password</h1>
				<p class="subtitle">Your temporary password must be replaced before you continue.</p>
			{/if}
		</div>

		<div class="card">
			{#if isMockMode()}
				<p class="hint mock-hint" data-testid="mock-accounts">
					Mock mode — sign in with any password as
					<span class="mono">superadmin@isu.edu.ph</span>,
					<span class="mono">admin@isu.edu.ph</span>,
					<span class="mono">maria.c.delacruz@isu.edu.ph</span>, or
					<span class="mono">jose.p.rizal@isu.edu.ph</span>.
				</p>
			{/if}
			<ErrorBoundary {error} retryButton={false}>
				{#snippet children()}

			{#if stage === 'credentials'}
				<form onsubmit={handleLogin}>
					<div class="field">
						<label class="form-label" for="email">Email</label>
						<input class="form-input" id="email" type="email" required
							autocomplete="email" placeholder="universityemail@isu.edu.ph"
							value={email}
							oninput={(e) => { email = (e.target as HTMLInputElement).value; }} />
					</div>

					<div class="field">
						<label class="form-label" for="password">Password</label>
						<div class="pwd-wrap">
							<input class="form-input" id="password" type={showPwd ? 'text' : 'password'}
								required autocomplete="current-password" placeholder="••••••••••••"
								value={password}
								oninput={(e) => { password = (e.target as HTMLInputElement).value; }}
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

					<button class="btn-primary" type="submit" disabled={authState.loading}>
						{#if authState.loading}
							<div style="display: flex; align-items: center; justify-content: center; gap: 8px;">
								<LoadingSpinner size="sm" message="" />
								<span>Signing in…</span>
							</div>
						{:else}
							Login
						{/if}
					</button>
				</form>
			{:else if stage === 'mfa'}
				<form onsubmit={handleMfa}>
					<div class="field">
						<label class="form-label" for="mfa">Authenticator code</label>
						<input class="form-input mono" id="mfa" required inputmode="numeric"
							autocomplete="one-time-code" maxlength="16" placeholder="000000"
							value={mfaCode}
							oninput={(e) => { mfaCode = (e.target as HTMLInputElement).value; }} />
						<p class="hint">Enter the 6-digit TOTP, or one of your backup codes
							(formatted <span class="mono">XXXX-XXXX-XX</span>).</p>
					</div>

					<button class="btn-primary" type="submit" disabled={authState.loading}>
						{#if authState.loading}
							<div style="display: flex; align-items: center; justify-content: center; gap: 8px;">
								<LoadingSpinner size="sm" message="" />
								<span>Verifying…</span>
							</div>
						{:else}
							Verify
						{/if}
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
							oninput={(e) => { currentPassword = (e.target as HTMLInputElement).value; }} />
					</div>

					<div class="field">
						<label class="form-label" for="new-password">New password</label>
						<input class="form-input" id="new-password" type="password" required
							autocomplete="new-password" value={newPassword}
							oninput={(e) => { newPassword = (e.target as HTMLInputElement).value; }} />
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
							oninput={(e) => { confirmPassword = (e.target as HTMLInputElement).value; }} />
						{#if confirmPassword && !passwordsMatch}
							<p class="hint warn">Passwords do not match.</p>
						{/if}
					</div>

					<button class="btn-primary" type="submit" disabled={authState.loading}>
						{#if authState.loading}
							<div style="display: flex; align-items: center; justify-content: center; gap: 8px;">
								<LoadingSpinner size="sm" message="" />
								<span>Saving…</span>
							</div>
						{:else}
							Set password and continue
						{/if}
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

			{/snippet}
		</ErrorBoundary>
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
		margin-bottom: 2rem;
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
		font-size: 1.5rem;
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

	.card {
		background: var(--bg-card);
		padding: 2rem;
		border-radius: 12px;
		box-shadow: var(--shadow-sm);
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

	.form-input.mono {
		font-family: monospace;
		font-size: 1.125rem;
		letter-spacing: 0.2em;
		text-align: center;
	}

	.hint {
		color: var(--text-muted);
		font-size: 0.75rem;
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
		border-radius: 8px;
		padding: 0.625rem 0.875rem;
		margin: 0 0 1rem;
	}

	.mock-hint .mono {
		font-family: monospace;
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
		padding: 0.75rem;
		border: none;
		border-radius: 8px;
		background: var(--brand);
		color: var(--on-brand);
		font-size: 1rem;
		font-weight: 600;
		font-family: inherit;
		cursor: pointer;
		margin-bottom: 1rem;
	}

	.btn-primary:hover:not(:disabled) {
		background: var(--brand-hover);
	}

	.btn-primary:disabled {
		opacity: 0.6;
		cursor: not-allowed;
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
</style>
