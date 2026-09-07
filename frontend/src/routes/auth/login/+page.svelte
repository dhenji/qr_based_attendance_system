<script lang="ts">
	import { doLogin, authState } from '$lib/features/auth/store.svelte';
	import { goto } from '$app/navigation';

	let email = $state('student@test.com');
	let password = $state('');

	const handleLogin = async () => {
		try {
			await doLogin(email, password);
			const role = authState.user?.role;
			if (role === 'professor') {
				goto('/professor/sessions');
			} else if (role === 'admin') {
				goto('/admin/students');
			} else {
				goto('/student/dashboard');
			}
		} catch {
			// error is shown via authState.error
		}
	};
</script>

<main class="auth">
	<div class="card">
		<h1>Login</h1>
		<form onsubmit={(e) => { e.preventDefault(); handleLogin(); }}>
			<label>
				Email
				<input type="email" bind:value={email} placeholder="you@school.edu" />
			</label>
			<label>
				Password
				<input type="password" bind:value={password} placeholder="••••••••" />
			</label>
			{#if authState.error}
				<p class="error">{authState.error}</p>
			{/if}
			<button type="submit" disabled={authState.loading}>
				{authState.loading ? 'Logging in…' : 'Login'}
			</button>
		</form>
		<p class="hint">
			Demo accounts:<br />
			student@test.com · prof@test.com · admin@test.com<br />(any password)
		</p>
		<a href="/">← Back</a>
	</div>
</main>

<style>
	main.auth {
		display: flex;
		align-items: center;
		justify-content: center;
		min-height: 100vh;
		font-family: system-ui, sans-serif;
		background: #f5f7fb;
	}

	.card {
		background: white;
		padding: 2rem;
		border-radius: 12px;
		box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
		width: 100%;
		max-width: 360px;
	}

	h1 {
		margin-top: 0;
	}

	form {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	label {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
		font-weight: 500;
	}

	input {
		padding: 0.7rem;
		border: 1px solid #d1d5db;
		border-radius: 8px;
		font-size: 1rem;
	}

	button {
		padding: 0.75rem;
		border: none;
		border-radius: 8px;
		background: #2563eb;
		color: white;
		font-size: 1rem;
		cursor: pointer;
	}

	button:hover {
		background: #1d4ed8;
	}

	.error {
		color: #dc2626;
		margin: 0;
	}

	.hint {
		color: #6b7280;
		font-size: 0.85rem;
	}

	a {
		color: #2563eb;
		text-decoration: none;
		font-size: 0.9rem;
	}
</style>