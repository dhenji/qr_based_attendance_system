<script lang="ts">
	import { isAuthenticated, isStudent, isProfessor, isAdmin, doLogout } from '$lib/features/auth/store.svelte';
	import AppIcon from '$lib/components/AppIcon.svelte';

	const features = [
		{ icon: 'qr', title: 'QR Scanning', desc: 'Fast, accurate' },
		{ icon: 'shield', title: 'Anti-Spoof', desc: 'Face liveness' },
		{ icon: 'offline', title: 'Offline', desc: 'Works anywhere' },
	] as const;

	const portals = [
		{ label: 'Student Portal', path: '/student/dashboard' },
		{ label: 'Professor Portal', path: '/professor/sessions' },
		{ label: 'Admin Portal', path: '/admin/students' },
	];

	const authLink = () => {
		if (isStudent()) return '/student/dashboard';
		if (isProfessor()) return '/professor/sessions';
		if (isAdmin()) return '/admin/students';
		return '/auth/login';
	};

	const authLabel = () => {
		if (isStudent()) return 'Student Dashboard';
		if (isProfessor()) return 'Professor Sessions';
		if (isAdmin()) return 'Admin Panel';
		return 'Login';
	};
</script>

<main class="landing">
	<div class="deco deco-a"></div>
	<div class="deco deco-b"></div>

	<div class="hero">
		<div class="logo-tile"><img src="/qr-attend-logo.svg" alt="Attendly" class="brand-logo" /></div>
		<h1>Attendly</h1>
		<p class="tagline">Attendance System · QR-based · Offline · Anti-spoofing PWA</p>
	</div>

	<div class="card">
		{#if isAuthenticated()}
			<div class="authed">
				<h2>Welcome back</h2>
				<a class="btn-primary" href={authLink()}>Go to {authLabel()}</a>
				<button class="btn-ghost" onclick={doLogout}>Logout</button>
			</div>
		{:else}
			<a class="btn-primary" href="/auth/login">Login to Your Account</a>
			<p class="register-hint">
				Don't have an account? <a href="/auth/register">Register here</a>
			</p>
		{/if}

		<div class="divider"></div>

		<div class="features">
			{#each features as f}
				<div class="feature">
					<div class="feature-icon"><AppIcon name={f.icon} size={28} /></div>
					<div class="feature-title">{f.title}</div>
					<div class="feature-desc">{f.desc}</div>
				</div>
			{/each}
		</div>

		<p class="footnote">A PWA — no app installation required</p>
	</div>

	<div class="portals">
		{#each portals as p}
			<a class="portal-pill" href={p.path}>{p.label}</a>
		{/each}
	</div>
</main>

<style>
	.landing {
		min-height: 100vh;
		background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 50%, #0d9488 100%);
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 2rem;
		position: relative;
		overflow: hidden;
		font-family: 'DM Sans', system-ui, sans-serif;
	}

	.deco {
		position: absolute;
		border-radius: 50%;
		pointer-events: none;
	}

	.deco-a {
		width: 500px;
		height: 500px;
		background: rgba(13, 148, 136, 0.1);
		top: -100px;
		right: -100px;
	}

	.deco-b {
		width: 300px;
		height: 300px;
		background: rgba(30, 58, 95, 0.3);
		bottom: -80px;
		left: -80px;
	}

	.hero {
		text-align: center;
		margin-bottom: 2.5rem;
	}

	.logo-tile {
		width: 72px;
		height: 72px;
		background: rgba(255, 255, 255, 0.15);
		border-radius: 20px;
		display: flex;
		align-items: center;
		justify-content: center;
		margin: 0 auto 1rem;
		backdrop-filter: blur(8px);
		border: 1px solid rgba(255, 255, 255, 0.2);
		color: white;
	}

	.logo-tile img {
		width: 56px;
		height: 56px;
		display: block;
	}

	h1 {
		font-family: 'DM Sans', sans-serif;
		font-size: 2.25rem;
		font-weight: 700;
		color: white;
		margin: 0 0 0.5rem;
	}

	.tagline {
		color: rgba(255, 255, 255, 0.7);
		font-size: 1rem;
		margin: 0;
	}

	.card {
		background: rgba(255, 255, 255, 0.06);
		backdrop-filter: blur(16px);
		border: 1px solid rgba(255, 255, 255, 0.15);
		border-radius: 20px;
		padding: 2.5rem;
		width: 100%;
		max-width: 420px;
		box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
	}

	.authed {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.authed h2 {
		color: white;
		margin: 0 0 0.5rem;
		font-size: 1.25rem;
	}

	.btn-primary {
		display: block;
		text-align: center;
		background: white;
		color: #0f172a;
		margin-bottom: 1rem;
		font-weight: 700;
		width: 100%;
		padding: 0.75rem 1rem;
		border: none;
		border-radius: 12px;
		font-size: 1rem;
		font-family: 'DM Sans', sans-serif;
		cursor: pointer;
		text-decoration: none;
	}

	.btn-primary:hover {
		opacity: 0.92;
	}

	.btn-ghost {
		background: rgba(255, 255, 255, 0.1);
		border: 1px solid rgba(255, 255, 255, 0.2);
		border-radius: 12px;
		color: white;
		padding: 0.6rem 1rem;
		font-size: 0.9rem;
		font-family: 'DM Sans', sans-serif;
		cursor: pointer;
	}

	.btn-ghost:hover {
		background: rgba(255, 255, 255, 0.18);
	}

	.register-hint {
		text-align: center;
		color: rgba(255, 255, 255, 0.6);
		font-size: 0.875rem;
		margin: 0;
	}

	.register-hint a {
		color: #5eead4;
		font-weight: 600;
		text-decoration: none;
		cursor: pointer;
	}

	.divider {
		margin: 1.5rem 0;
		border-top: 1px solid rgba(255, 255, 255, 0.1);
	}

	.features {
		display: grid;
		grid-template-columns: 1fr 1fr 1fr;
		gap: 0.875rem;
	}

	.feature {
		background: rgba(255, 255, 255, 0.07);
		border-radius: 12px;
		padding: 0.875rem 0.5rem;
		text-align: center;
		border: 1px solid rgba(255, 255, 255, 0.1);
	}

	.feature-icon {
		display: flex;
		align-items: center;
		justify-content: center;
		color: white;
		margin-bottom: 0.375rem;
	}

	.feature-title {
		color: white;
		font-size: 0.75rem;
		font-weight: 700;
	}

	.feature-desc {
		color: rgba(255, 255, 255, 0.5);
		font-size: 0.6875rem;
	}

	.footnote {
		text-align: center;
		color: rgba(255, 255, 255, 0.4);
		font-size: 0.75rem;
		margin-top: 1.25rem;
		margin-bottom: 0;
	}

	.portals {
		margin-top: 1.5rem;
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
		justify-content: center;
	}

	.portal-pill {
		background: rgba(255, 255, 255, 0.08);
		border: 1px solid rgba(255, 255, 255, 0.15);
		border-radius: 99px;
		padding: 0.375rem 1rem;
		color: rgba(255, 255, 255, 0.7);
		font-size: 0.75rem;
		font-weight: 500;
		cursor: pointer;
		text-decoration: none;
	}

	.portal-pill:hover {
		background: rgba(255, 255, 255, 0.14);
	}
</style>