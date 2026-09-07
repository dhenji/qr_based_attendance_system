<script lang="ts">
	import { register } from '$lib/features/auth/service';
	import { goto } from '$app/navigation';

	let email = $state('');
	let studentNumber = $state('');
	let message = $state<string | null>(null);
	let error = $state<string | null>(null);
	let submitting = $state(false);

	const handleRegister = async () => {
		submitting = true;
		error = null;
		message = null;
		try {
			await register(email, studentNumber);
			message = 'Registration submitted! Check your email for an OTP.';
			goto('/auth/login');
		} catch (e) {
			error = e instanceof Error ? e.message : 'Registration failed';
		} finally {
			submitting = false;
		}
	};
</script>

<main class="auth">
	<div class="card">
		<h1>Register</h1>
		<form onsubmit={(e) => { e.preventDefault(); handleRegister(); }}>
			<label>
				Email
				<input type="email" bind:value={email} placeholder="you@school.edu" required />
			</label>
			<label>
				Student Number
				<input type="text" bind:value={studentNumber} placeholder="STU-XXXXXX" required />
			</label>
			{#if message}
				<p class="message">{message}</p>
			{/if}
			{#if error}
				<p class="error">{error}</p>
			{/if}
			<button type="submit" disabled={submitting}>
				{submitting ? 'Submitting…' : 'Register'}
			</button>
		</form>
		<p class="hint">Claim-based registration with email OTP verification.</p>
		<a href="/auth/login">Already have an account? Login</a>
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

	.message {
		color: #16a34a;
		margin: 0;
	}

	.hint {
		color: #6b7280;
		font-size: 0.85rem;
	}

	a {
		display: block;
		color: #2563eb;
		text-decoration: none;
		font-size: 0.9rem;
		margin-top: 0.5rem;
	}
</style>