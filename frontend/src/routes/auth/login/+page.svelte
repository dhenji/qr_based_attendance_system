<script lang="ts">
	import { doLogin, authState } from '$lib/features/auth/store.svelte';
	import { goto } from '$app/navigation';

	let email = $state('');
	let password = $state('');
	let captchaInput = $state('');
	let showPwd = $state(false);
	let captchaCode = $state('4F7K2Q');
	let error = $state('');
	let attempts = $state(0);

	function refreshCaptcha() {
		const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
		let code = '';
		for (let i = 0; i < 6; i++) {
			code += chars[Math.floor(Math.random() * chars.length)];
		}
		captchaCode = code;
	}

	const handleLogin = async () => {
		if (!email || !password || !captchaInput) {
			error = 'All fields are required.';
			return;
		}
		if (captchaInput.toUpperCase() !== captchaCode) {
			attempts += 1;
			const remaining = 5 - attempts;
			error = remaining > 0
				? `Captcha incorrect. ${remaining} attempt${remaining !== 1 ? 's' : ''} remaining.`
				: 'Too many failed attempts. Please refresh the captcha.';
			return;
		}
		error = '';
		try {
			await doLogin(email, password);
			const role = authState.user?.role;
			if (role === 'professor') goto('/professor/sessions');
			else if (role === 'admin') goto('/admin/students');
			else goto('/student/dashboard');
		} catch {
			// error shown via authState.error
		}
	};
</script>

<main class="auth">
	<div class="wrapper">
		<div class="header">
			<div class="logo-tile"><img src="/qr-attend-logo.svg" alt="Attendly" /></div>
			<h1>Log In</h1>
			<p class="subtitle">Enter your registered email and password.</p>
		</div>

		<div class="card">
			{#if error}
				<div class="error-banner">{error}</div>
			{/if}

			<div class="field">
				<label class="form-label" for="email">Email / Username</label>
				<input class="form-input" id="email" type="email" placeholder="universityemail@isu.edu.ph"
					value={email} oninput={(e) => { email = (e.target as HTMLInputElement).value; }} />
			</div>

			<div class="field">
				<label class="form-label" for="password">Password</label>
				<div class="pwd-wrap">
					<input class="form-input" id="password" type={showPwd ? 'text' : 'password'}
						placeholder="••••••••••••" value={password}
						oninput={(e) => { password = (e.target as HTMLInputElement).value; }}
						style="padding-right: 2.5rem;" />
					<button class="pwd-toggle" onclick={() => { showPwd = !showPwd; }} aria-label={showPwd ? 'Hide password' : 'Show password'}>
						{#if showPwd}
							<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" /><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" /><path d="M14.12 14.12a3 3 0 1 1-4.24-4.24" /><line x1="1" y1="1" x2="23" y2="23" /></svg>
						{:else}
							<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></svg>
						{/if}
					</button>
				</div>
			</div>

			<div class="field captcha-field">
				<label class="form-label" for="captcha">Captcha</label>
				<div class="captcha-row">
					<div class="captcha-display">{captchaCode}</div>
					<button class="captcha-refresh" onclick={refreshCaptcha}>↻</button>
				</div>
				<input class="form-input" id="captcha" placeholder="Enter code above"
					value={captchaInput} oninput={(e) => { captchaInput = (e.target as HTMLInputElement).value; }} />
			</div>

			<button class="btn-primary" onclick={handleLogin}>Login</button>

			<div class="links">
				<button class="link-btn" onclick={() => goto('/auth/forgot-password')}>Forgot Password?</button>
				<div class="divider">
					<div class="divider-line"></div>
					<span class="divider-text">OR</span>
					<div class="divider-line"></div>
				</div>
				<span class="register-hint">
					Don't have an account?
					<button class="link-btn" onclick={() => goto('/auth/register')}>Register</button>
				</span>
			</div>
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
		color: #1e3a5f;
		margin: 0 0 0.25rem;
	}

	.subtitle {
		color: #6b7280;
		font-size: 0.875rem;
		margin: 0;
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

	.captcha-field {
		margin-bottom: 1.5rem;
	}

	.captcha-row {
		display: flex;
		gap: 0.5rem;
		margin-bottom: 0.5rem;
	}

	.captcha-display {
		flex: 1;
		background: #f1f5f9;
		border: 1.5px solid #d1d5db;
		border-radius: 8px;
		padding: 0.625rem 0.875rem;
		display: flex;
		align-items: center;
		justify-content: center;
		font-family: monospace;
		font-weight: 700;
		font-size: 1.125rem;
		letter-spacing: 0.3em;
		color: #1e3a5f;
		user-select: none;
		text-decoration: line-through;
		text-decoration-style: wavy;
		text-decoration-color: rgba(30, 58, 95, 0.3);
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
		margin-bottom: 1rem;
	}

	.btn-primary:hover {
		background: #16324f;
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
		color: #2563eb;
		font-size: 0.8125rem;
		font-weight: 600;
		font-family: inherit;
		padding: 0;
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
		background: #d1d5db;
	}

	.divider-text {
		color: #6b7280;
		font-size: 0.75rem;
	}

	.register-hint {
		font-size: 0.8125rem;
		color: #6b7280;
	}
</style>
