<script lang="ts">
	import { isAuthenticated, isStudent, isProfessor, isAdmin, doLogout, authState, defaultRouteFor } from '$lib/features/auth/store.svelte';
	import AppIcon from '$lib/components/AppIcon.svelte';

	const features = [
		{ icon: 'qr', title: 'Session QR codes', desc: 'Every session gets a unique code, so each meeting can only be joined once.' },
		{ icon: 'offline', title: 'Offline-first', desc: 'Check-ins save on the device and sync back when a signal returns.' },
		{ icon: 'camera', title: 'Face liveness', desc: 'A camera check confirms a real person, not a photo or a video.' },
		{ icon: 'shield', title: 'Classroom geofence', desc: 'Attendance records only inside the classroom, within a set radius.' },
	] as const;

	const steps = [
		{
			title: 'Scan the session QR',
			desc: 'The professor opens a session and students scan the code on the board.',
		},
		{
			title: 'Verify location and face',
			desc: 'The app checks the classroom geofence and runs a live face check.',
		},
		{
			title: 'Check-in recorded',
			desc: 'Attendance saves immediately, even offline, and syncs later.',
		},
	] as const;

	const portals = [
		{
			label: 'Student portal',
			desc: 'Scan, view your schedule, and track your attendance rate.',
			path: '/student/dashboard',
			cta: 'Open dashboard',
			ready: true,
		},
		{
			label: 'Professor portal',
			desc: 'Create sessions and review attendance for every meeting.',
			path: '/professor/sessions',
			cta: 'Open sessions',
			ready: true,
		},
		{
			// The admin portal is still being built — linking to it would 404.
			label: 'Admin portal',
			desc: 'Manage rosters, courses, and attendance records.',
			path: '',
			cta: 'Coming soon',
			ready: false,
		},
	];

	const navLinks = [
		{ label: 'About', path: '/about' },
		{ label: 'Privacy Policy', path: '/privacy-policy' },
		{ label: 'Cookies', path: '/cookies' },
	];

	// Single source of truth for where a signed-in user lands, so the header
	// can't drift from what the login page does after authenticating.
	const authLink = () => defaultRouteFor(authState.user);

	const authLabel = () => {
		if (isStudent()) return 'Student Dashboard';
		if (isProfessor()) return 'Professor Sessions';
		if (isAdmin()) return 'Home';
		return 'Login';
	};
</script>

<main class="landing">
	<header class="nav">
		<a class="nav-brand" href="/">
			<img src="/qr-attend-logo.svg" alt="Attendly logo" class="nav-logo" />
			<span class="nav-name">Attendly</span>
		</a>
		<nav class="nav-links" aria-label="Landing">
			{#each navLinks as link}
				<a class="nav-link" href={link.path}>{link.label}</a>
			{/each}
		</nav>
	</header>

	<section class="hero">
		<div class="hero-copy">
			<p class="eyebrow">For ISU classrooms</p>
			<h1>Class attendance, recorded in one scan.</h1>
			<p class="hero-sub">
				Students scan the session QR code, verify their location and face, and the
				check-in is recorded. Even without a signal.
			</p>
			<div class="hero-actions">
				{#if isAuthenticated()}
					<a class="btn-primary" href={authLink()}>Go to {authLabel()}</a>
					<button class="btn-ghost" onclick={doLogout}>Logout</button>
				{:else}
					<a class="btn-primary" href="/auth/login">Login to your account</a>
					<a class="btn-ghost" href="/auth/register">Create an account</a>
				{/if}
			</div>
		</div>

		<div class="hero-visual">
			<div class="phone" aria-hidden="true">
				<div class="phone-screen">
					<div class="screen-top">
						<span class="screen-dot"></span>
						<span class="screen-title">Scan session</span>
					</div>
					<div class="scan-area">
						<span class="corner tl"></span>
						<span class="corner tr"></span>
						<span class="corner bl"></span>
						<span class="corner br"></span>
						<svg class="qr" viewBox="0 0 29 29" width="112" height="112">
							<rect x="0" y="0" width="9" height="9" rx="1" fill="#16324f" />
							<rect x="1" y="1" width="7" height="7" rx="0.5" fill="#f8fafc" />
							<rect x="2.5" y="2.5" width="4" height="4" rx="0.5" fill="#16324f" />
							<rect x="20" y="0" width="9" height="9" rx="1" fill="#16324f" />
							<rect x="21" y="1" width="7" height="7" rx="0.5" fill="#f8fafc" />
							<rect x="22.5" y="2.5" width="4" height="4" rx="0.5" fill="#16324f" />
							<rect x="0" y="20" width="9" height="9" rx="1" fill="#16324f" />
							<rect x="1" y="21" width="7" height="7" rx="0.5" fill="#f8fafc" />
							<rect x="2.5" y="22.5" width="4" height="4" rx="0.5" fill="#16324f" />
							<rect x="11" y="2" width="4" height="4" rx="1" fill="#16324f" />
							<rect x="11" y="11" width="5" height="5" rx="1" fill="#16324f" />
							<rect x="18" y="17" width="4" height="4" rx="1" fill="#16324f" />
							<rect x="23" y="12" width="3" height="3" rx="0.5" fill="#16324f" />
							<rect x="11" y="23" width="3" height="3" rx="0.5" fill="#16324f" />
							<rect x="2" y="12" width="3" height="3" rx="0.5" fill="#16324f" />
							<rect x="17" y="6" width="3" height="3" rx="0.5" fill="#16324f" />
							<rect x="7" y="14" width="4" height="3" rx="0.5" fill="#16324f" />
						</svg>
						<span class="scan-hint">Point camera at the QR</span>
					</div>
					<div class="status-pill">
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
							<path d="m5 13 4 4L19 7" />
						</svg>
						Check-in recorded
					</div>
				</div>
			</div>
		</div>
	</section>

	<section class="how">
		<p class="section-eyebrow">How a check-in works</p>
		<h2>Three steps, one scan.</h2>
		<div class="steps">
			{#each steps as step, i}
				<div class="step-card">
					<span class="step-num">{i + 1}</span>
					<h3>{step.title}</h3>
					<p>{step.desc}</p>
				</div>
			{/each}
		</div>
	</section>

	<section class="features">
		<p class="section-eyebrow">Built for reliability</p>
		<h2>Attendance that works in the real classroom.</h2>
		<div class="feature-grid">
			{#each features as f}
				<div class="feature">
					<div class="feature-icon"><AppIcon name={f.icon} size={28} /></div>
					<h3>{f.title}</h3>
					<p>{f.desc}</p>
				</div>
			{/each}
		</div>
	</section>

	<section class="portals">
		<p class="section-eyebrow">Pick your portal</p>
		<h2>Made for students, professors, and admins.</h2>
		<div class="portal-grid">
			{#each portals as portal}
				{#if portal.ready}
					<a class="portal-card" href={portal.path}>
						<h3>{portal.label}</h3>
						<p>{portal.desc}</p>
						<span class="portal-cta">
							{portal.cta}
							<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
								<path d="M5 12h14" />
								<path d="m13 6 6 6-6 6" />
							</svg>
						</span>
					</a>
				{:else}
					<div class="portal-card is-disabled" aria-disabled="true">
						<h3>{portal.label}</h3>
						<p>{portal.desc}</p>
						<span class="portal-cta">{portal.cta}</span>
					</div>
				{/if}
			{/each}
		</div>
	</section>
</main>

<style>
	.landing {
		min-height: 100vh;
		font-family: 'DM Sans', system-ui, sans-serif;
		background: #f8fafc;
		color: #1e293b;
	}

	.nav {
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		z-index: 20;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		padding: 0.75rem 1.5rem;
		background: #1e3a5f;
		box-shadow: 0 2px 12px rgba(15, 23, 42, 0.25);
	}

	.nav-brand {
		display: flex;
		align-items: center;
		gap: 0.625rem;
		text-decoration: none;
	}

	.nav-logo {
		width: 34px;
		height: 34px;
		display: block;
	}

	.nav-name {
		color: white;
		font-weight: 700;
		font-size: 1.125rem;
		white-space: nowrap;
	}

	.nav-links {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		flex-wrap: wrap;
		justify-content: flex-end;
	}

	.nav-link {
		padding: 0.5rem 0.875rem;
		border-radius: 8px;
		color: #e2e8f0;
		font-size: 0.9375rem;
		font-weight: 500;
		text-decoration: none;
		white-space: nowrap;
		transition: background 0.15s ease, color 0.15s ease;
	}

	.nav-link:hover {
		background: rgba(255, 255, 255, 0.1);
		color: white;
	}

	.hero {
		display: grid;
		grid-template-columns: 1.1fr 0.9fr;
		gap: 3rem;
		align-items: center;
		max-width: 1080px;
		margin: 0 auto;
		padding: 9rem 2rem 5rem;
	}

	.eyebrow,
	.section-eyebrow {
		font-size: 0.8125rem;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: #2563eb;
		margin: 0 0 0.75rem;
	}

	h1 {
		font-size: 2.75rem;
		line-height: 1.08;
		font-weight: 700;
		margin: 0 0 1rem;
		letter-spacing: -0.02em;
	}

	.hero-sub {
		font-size: 1.125rem;
		line-height: 1.6;
		color: #475569;
		margin: 0 0 1.75rem;
		max-width: 34rem;
	}

	.hero-actions {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		flex-wrap: wrap;
	}

	.btn-primary {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		background: #1e3a5f;
		border: 1px solid #1e3a5f;
		color: white;
		font-weight: 600;
		font-size: 1rem;
		padding: 0.8125rem 1.375rem;
		border-radius: 8px;
		text-decoration: none;
		cursor: pointer;
		box-shadow: 0 4px 14px rgba(30, 58, 95, 0.28);
		transition: background 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease;
	}

	.btn-primary:hover {
		background: #16324f;
		border-color: #16324f;
		transform: translateY(-1px);
		box-shadow: 0 8px 20px rgba(30, 58, 95, 0.32);
	}

	.btn-ghost {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		background: white;
		border: 1px solid #cbd5e1;
		color: #0f172a;
		font-weight: 600;
		font-size: 1rem;
		padding: 0.8125rem 1.375rem;
		border-radius: 8px;
		text-decoration: none;
		cursor: pointer;
		transition: background 0.15s ease, transform 0.15s ease;
	}

	.btn-ghost:hover {
		background: #f1f5f9;
		transform: translateY(-1px);
	}

	.hero-visual {
		display: flex;
		justify-content: center;
	}

	.phone {
		width: 300px;
		max-width: 100%;
		border-radius: 28px;
		background: #16324f;
		padding: 10px;
		box-shadow: 0 30px 70px rgba(15, 23, 42, 0.3);
		animation: float 6s ease-in-out infinite;
	}

	.phone-screen {
		background: #f8fafc;
		border-radius: 20px;
		overflow: hidden;
	}

	.screen-top {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.875rem 1rem;
		border-bottom: 1px solid #e2e8f0;
	}

	.screen-dot {
		width: 10px;
		height: 10px;
		border-radius: 50%;
		background: #16a34a;
	}

	.screen-title {
		font-size: 0.875rem;
		font-weight: 600;
		color: #1e293b;
	}

	.scan-area {
		position: relative;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 0.875rem;
		height: 300px;
		max-height: 60vw;
		padding: 1rem;
	}

	.corner {
		position: absolute;
		width: 22px;
		height: 22px;
		border: 0 solid #94a3b8;
	}

	.corner.tl {
		top: 16px;
		left: 16px;
		border-top-width: 3px;
		border-left-width: 3px;
		border-top-left-radius: 8px;
	}

	.corner.tr {
		top: 16px;
		right: 16px;
		border-top-width: 3px;
		border-right-width: 3px;
		border-top-right-radius: 8px;
	}

	.corner.bl {
		bottom: 16px;
		left: 16px;
		border-bottom-width: 3px;
		border-left-width: 3px;
		border-bottom-left-radius: 8px;
	}

	.corner.br {
		bottom: 16px;
		right: 16px;
		border-bottom-width: 3px;
		border-right-width: 3px;
		border-bottom-right-radius: 8px;
	}

	.qr {
		background: white;
		padding: 8px;
		border-radius: 8px;
		box-shadow: 0 4px 12px rgba(15, 23, 42, 0.1);
		max-width: 60%;
		height: auto;
	}

	.scan-hint {
		font-size: 0.8125rem;
		color: #64748b;
	}

	.status-pill {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		background: #16a34a;
		color: white;
		font-size: 0.8125rem;
		font-weight: 600;
		padding: 0.5rem 0.875rem;
		border-radius: 8px;
		margin: 0 1rem 1rem;
	}

	.how,
	.features,
	.portals {
		max-width: 1080px;
		margin: 0 auto;
		padding: 5rem 2rem;
	}

	.how {
		border-top: 1px solid #e2e8f0;
	}

	h2 {
		font-size: 1.875rem;
		font-weight: 700;
		margin: 0 0 2rem;
		letter-spacing: -0.02em;
	}

	.steps {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 1.25rem;
	}

	.step-card {
		position: relative;
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 8px;
		padding: 1.5rem;
		transition: transform 0.15s ease, box-shadow 0.15s ease;
	}

	.step-card::before {
		content: '';
		position: absolute;
		top: 0;
		left: 0;
		width: 22px;
		height: 22px;
		border-top: 2px solid #2563eb;
		border-left: 2px solid #2563eb;
		border-top-left-radius: 8px;
	}

	.step-card:hover {
		transform: translateY(-2px);
		box-shadow: 0 10px 28px rgba(15, 23, 42, 0.1);
	}

	.step-num {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 32px;
		height: 32px;
		border-radius: 8px;
		background: #1e3a5f;
		color: white;
		font-weight: 700;
		font-size: 0.9375rem;
		margin-bottom: 1rem;
	}

	.step-card h3,
	.feature h3 {
		font-size: 1.05rem;
		font-weight: 700;
		margin: 0 0 0.5rem;
	}

	.step-card p,
	.feature p {
		font-size: 0.9375rem;
		line-height: 1.55;
		color: #475569;
		margin: 0;
	}

	.features {
		border-top: 1px solid #e2e8f0;
	}

	.feature-grid {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 1.25rem;
	}

	.feature {
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 8px;
		padding: 1.5rem;
		transition: transform 0.15s ease, box-shadow 0.15s ease;
	}

	.feature:hover {
		transform: translateY(-2px);
		box-shadow: 0 10px 28px rgba(15, 23, 42, 0.1);
	}

	.feature-icon {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 52px;
		height: 52px;
		border-radius: 8px;
		background: #f1f5f9;
		color: #1e3a5f;
		margin-bottom: 1rem;
	}

	.portals {
		border-top: 1px solid #e2e8f0;
	}

	.portal-grid {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 1.25rem;
	}

	.portal-card {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		background: #1e3a5f;
		color: white;
		text-decoration: none;
		padding: 1.75rem;
		border-radius: 8px;
		box-shadow: 0 6px 18px rgba(30, 58, 95, 0.25);
		transition: background 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease;
	}

	.portal-card:hover {
		background: #16324f;
		transform: translateY(-2px);
		box-shadow: 0 12px 28px rgba(30, 58, 95, 0.3);
	}

	/* Portals that don't exist yet — no hover lift, muted so it reads as inert. */
	.portal-card.is-disabled {
		background: #475569;
		box-shadow: none;
		cursor: default;
	}

	.portal-card h3 {
		font-size: 1.125rem;
		font-weight: 700;
		margin: 0;
	}

	.portal-card p {
		font-size: 0.9375rem;
		line-height: 1.5;
		color: #cbd5e1;
		margin: 0;
	}

	.portal-cta {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		font-weight: 600;
		font-size: 0.9375rem;
		color: #bfdbfe;
		margin-top: 0.5rem;
	}

	.portal-cta svg {
		transition: transform 0.15s ease;
	}

	.portal-card:hover .portal-cta svg {
		transform: translateX(3px);
	}

	@keyframes float {
		0%,
		100% {
			transform: translateY(0);
		}
		50% {
			transform: translateY(-6px);
		}
	}

	@media (max-width: 900px) {
		.hero {
			grid-template-columns: 1fr;
			padding: 7rem 1.5rem 3rem;
			text-align: center;
		}

		.hero-sub {
			margin-left: auto;
			margin-right: auto;
		}

		.hero-actions {
			justify-content: center;
		}

		.how,
		.features,
		.portals {
			padding: 3rem 1.5rem;
		}

		.steps,
		.feature-grid,
		.portal-grid {
			grid-template-columns: 1fr;
		}

		h1 {
			font-size: 2rem;
		}

		h2 {
			font-size: 1.5rem;
		}
	}

	@media (max-width: 560px) {
		.nav {
			padding: 0.625rem 1rem;
		}

		.nav-links {
			gap: 0.125rem;
		}

		.nav-link {
			padding: 0.4375rem 0.625rem;
			font-size: 0.8125rem;
		}

		.hero-actions {
			flex-direction: column;
			align-items: stretch;
		}

		.btn-primary,
		.btn-ghost {
			width: 100%;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.phone {
			animation: none;
		}

		.portal-cta svg {
			transition: none;
		}
	}

	:global(a:focus-visible),
	:global(button:focus-visible) {
		outline: 2px solid #2563eb;
		outline-offset: 2px;
	}
</style>