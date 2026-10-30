<script lang="ts">
	import { isAuthenticated, isStudent, isProfessor, isAdmin, doLogout, authState, defaultRouteFor } from '$lib/features/auth/store.svelte';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import { Routes } from '$lib/shared/constants/routes';

	const features = [
		{ icon: 'qr', title: 'Session QR codes', tag: 'Unique per session', desc: 'Every session gets a unique code, so each meeting can only be joined once.' },
		{ icon: 'offline', title: 'Offline-first', tag: 'No signal needed', desc: 'Check-ins save on the device and sync back when a signal returns.' },
		{ icon: 'camera', title: 'Face liveness', tag: 'Liveness check', desc: 'A camera check confirms a real person, not a photo or a video.' },
		{ icon: 'shield', title: 'Classroom geofence', tag: 'On-campus only', desc: 'Attendance records only inside the classroom, within a set radius.' },
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

	const navLinks = [
		{ label: 'About', path: Routes.ABOUT },
		{ label: 'Privacy Policy', path: Routes.PRIVACY_POLICY },
		{ label: 'Cookies', path: Routes.COOKIES },
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
			<p class="eyebrow"><span class="eyebrow-mark" aria-hidden="true"></span>For ISU classrooms</p>
			<h1>Class attendance, recorded in <span class="mark">one scan.</span></h1>
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
			<p class="hero-note mono-data">
				<span class="note-dot" aria-hidden="true"></span>
				Face + location verified · works offline
			</p>
		</div>

		<div class="hero-visual">
			<div class="visual-stage">
				<div class="phone" aria-hidden="true">
					<div class="phone-screen">
						<div class="screen-top">
							<span class="screen-dot"></span>
							<span class="screen-title">Scan session</span>
							<span class="screen-code mono-data">A7K2</span>
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
							<span class="scan-beam"></span>
						</div>
					</div>
				</div>

				<div class="record-card" aria-hidden="true">
					<div class="record-top">
						<span class="record-dot"></span>
						<span class="record-status">Check-in recorded</span>
						<span class="record-time mono-data">10:42</span>
					</div>
					<p class="record-name">Jose P. Rizal</p>
					<p class="record-meta mono-data">BSCS 3A · Room 204</p>
					<div class="record-rows">
						<span><em>Session</em><strong class="mono-data">A7K2</strong></span>
						<span><em>Method</em><strong>QR + face</strong></span>
					</div>
				</div>
			</div>
		</div>
	</section>

	<section class="how">
		<p class="section-eyebrow">01 / How it works</p>
		<h2>Three steps, one scan.</h2>
		<div class="steps">
			{#each steps as step, i}
				<div class="step-card" data-step={'0' + (i + 1)}>
					<span class="step-num">0{i + 1}</span>
					<h3>{step.title}</h3>
					<p>{step.desc}</p>
				</div>
			{/each}
		</div>
	</section>

	<section class="features">
		<p class="section-eyebrow">02 / Built for reliability</p>
		<h2>Attendance that works in the real classroom.</h2>
		<div class="feature-grid">
			{#each features as f}
				<div class="feature">
					<div class="feature-top">
						<div class="feature-icon"><AppIcon name={f.icon} size={26} /></div>
						<span class="feature-tag mono-data">{f.tag}</span>
					</div>
					<h3>{f.title}</h3>
					<p>{f.desc}</p>
				</div>
			{/each}
		</div>
	</section>


</main>

<footer class="footer" id="site-footer">
	<div class="footer-inner">
		<a class="footer-brand" href="/">
			<img src="/qr-attend-logo.svg" alt="" class="footer-logo" />
			<span class="footer-name">Attendly</span>
		</a>
		<nav class="footer-links" aria-label="Footer">
			{#each navLinks as link}
				<a class="footer-link" href={link.path}>{link.label}</a>
			{/each}
		</nav>
	</div>
	<p class="footer-note mono-data">QR attendance · recorded where it happens</p>
</footer>

<style>
	.landing {
		min-height: 100vh;
		min-height: 100dvh;
		font-family: var(--font-ui);
		background: var(--bg-page);
		color: var(--text);
		overflow-x: clip;
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
		background: color-mix(in srgb, var(--brand) 32%, #080f1a);
		border-bottom: 1px solid rgba(255, 255, 255, 0.08);
		box-shadow: 0 10px 30px rgba(2, 6, 23, 0.18);
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
		color: var(--on-brand);
		font-weight: 700;
		font-size: 1.125rem;
		letter-spacing: -0.02em;
		white-space: nowrap;
	}

	.nav-links {
		display: flex;
		align-items: center;
		gap: 0.125rem;
		flex-wrap: wrap;
		justify-content: flex-end;
	}

	.nav-link {
		position: relative;
		padding: 0.5rem 0.875rem;
		border-radius: 8px;
		color: color-mix(in srgb, var(--on-brand) 70%, transparent);
		font-size: 0.875rem;
		font-weight: 500;
		text-decoration: none;
		white-space: nowrap;
		transition: background 0.15s ease, color 0.15s ease;
	}

	.nav-link:hover {
		background: rgba(255, 255, 255, 0.08);
		color: var(--on-brand);
	}

	.hero {
		position: relative;
		isolation: isolate;
		display: grid;
		grid-template-columns: 1.08fr 0.92fr;
		gap: 3rem;
		align-items: center;
		max-width: 1080px;
		margin: 0 auto;
		padding: 9.5rem 2rem 6rem;
	}

	.hero::before {
		content: '';
		position: absolute;
		inset: 0;
		z-index: -1;
		background-image:
			linear-gradient(to right, color-mix(in srgb, var(--border) 65%, transparent) 1px, transparent 1px),
			linear-gradient(to bottom, color-mix(in srgb, var(--border) 65%, transparent) 1px, transparent 1px);
		background-size: 44px 44px;
		mask-image: radial-gradient(ellipse 72% 72% at 50% 42%, #000 0%, transparent 76%);
		-webkit-mask-image: radial-gradient(ellipse 72% 72% at 50% 42%, #000 0%, transparent 76%);
		opacity: 0.7;
		pointer-events: none;
	}

	.hero::after {
		content: '';
		position: absolute;
		top: -8%;
		right: -6%;
		width: 58%;
		height: 82%;
		z-index: -1;
		background: radial-gradient(closest-side, color-mix(in srgb, var(--accent) 13%, transparent), transparent 72%);
		pointer-events: none;
	}

	.eyebrow,
	.section-eyebrow {
		font-family: var(--font-data);
		font-size: 0.6875rem;
		font-weight: 500;
		letter-spacing: 0.14em;
		text-transform: uppercase;
		color: var(--accent);
		margin: 0 0 0.875rem;
	}

	.eyebrow {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.eyebrow-mark {
		position: relative;
		width: 12px;
		height: 12px;
		border: 2px solid currentColor;
		border-radius: 3px;
		flex: none;
	}

	.eyebrow-mark::after {
		content: '';
		position: absolute;
		inset: 2px;
		background: currentColor;
		border-radius: 1px;
		opacity: 0.75;
	}

	h1 {
		font-size: 3.25rem;
		line-height: 1.04;
		font-weight: 700;
		color: var(--text-strong);
		margin: 0 0 1.125rem;
		letter-spacing: -0.035em;
	}

	.mark {
		background-image: linear-gradient(transparent 63%, color-mix(in srgb, var(--accent) 22%, transparent) 63%);
		background-repeat: no-repeat;
		box-decoration-break: clone;
		-webkit-box-decoration-break: clone;
		padding: 0 0.06em;
	}

	.hero-sub {
		font-size: 1.0625rem;
		line-height: 1.65;
		color: var(--text-secondary);
		margin: 0 0 1.875rem;
		max-width: 34rem;
	}

	.hero-actions {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		flex-wrap: wrap;
	}

	.hero-note {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin: 1.5rem 0 0;
		font-size: 0.625rem;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		color: var(--text-muted);
	}

	.note-dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: var(--success);
		box-shadow: 0 0 0 3px color-mix(in srgb, var(--success) 16%, transparent);
		flex: none;
	}

	.btn-primary {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		background: linear-gradient(135deg, var(--brand), color-mix(in srgb, var(--brand) 70%, #0a1220));
		border: 1px solid color-mix(in srgb, var(--brand) 80%, #0a1220);
		color: var(--on-brand);
		font-weight: 600;
		font-size: 0.9375rem;
		padding: 0.8125rem 1.375rem;
		border-radius: 10px;
		text-decoration: none;
		cursor: pointer;
		box-shadow: 0 6px 16px color-mix(in srgb, var(--brand) 26%, transparent);
		transition: transform 0.15s ease, box-shadow 0.15s ease, filter 0.15s ease;
	}

	.btn-primary:hover {
		transform: translateY(-2px);
		filter: brightness(1.08);
		box-shadow: 0 10px 24px color-mix(in srgb, var(--brand) 34%, transparent);
	}

	.btn-primary:active {
		transform: translateY(0);
	}

	.btn-ghost {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		background: color-mix(in srgb, var(--bg-card) 88%, transparent);
		border: 1px solid var(--border-strong);
		color: var(--text-strong);
		font-weight: 600;
		font-size: 0.9375rem;
		padding: 0.8125rem 1.375rem;
		border-radius: 10px;
		text-decoration: none;
		cursor: pointer;
		transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease, transform 0.15s ease;
	}

	.btn-ghost:hover {
		background: var(--bg-hover);
		border-color: var(--accent);
		color: var(--accent);
		transform: translateY(-2px);
	}

	.hero-visual {
		display: flex;
		justify-content: center;
		align-items: center;
	}

	.visual-stage {
		position: relative;
		display: flex;
		flex-direction: column;
		align-items: center;
		width: min(360px, 100%);
		animation: float 7s ease-in-out infinite;
	}

	.visual-stage::before {
		content: '';
		position: absolute;
		inset: 12% -10% 22%;
		z-index: -1;
		background: radial-gradient(closest-side, color-mix(in srgb, var(--accent) 14%, transparent), transparent 75%);
		filter: blur(18px);
		pointer-events: none;
	}

	.phone {
		width: 280px;
		max-width: 100%;
		border-radius: 30px;
		background: linear-gradient(160deg, var(--brand), var(--brand-hover));
		border: 1px solid color-mix(in srgb, var(--brand) 70%, #0a1220);
		padding: 9px;
		box-shadow: var(--shadow-lg), inset 0 1px 0 rgba(255, 255, 255, 0.16);
	}

	.phone-screen {
		background: var(--bg-page);
		border-radius: 22px;
		overflow: hidden;
		border: 1px solid rgba(255, 255, 255, 0.08);
	}

	.screen-top {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.875rem 1rem;
		border-bottom: 1px solid var(--border);
	}

	.screen-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--success);
		box-shadow: 0 0 0 3px color-mix(in srgb, var(--success) 14%, transparent);
		flex: none;
	}

	.screen-title {
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text);
	}

	.screen-code {
		margin-left: auto;
		padding: 0.125rem 0.375rem;
		border-radius: 4px;
		background: var(--bg-muted);
		color: var(--text-muted);
		font-size: 0.625rem;
		letter-spacing: 0.08em;
	}

	.scan-area {
		position: relative;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 0.875rem;
		height: 290px;
		max-height: 60vw;
		padding: 1rem;
		overflow: hidden;
		background: radial-gradient(circle at 50% 44%, color-mix(in srgb, var(--accent) 6%, transparent), transparent 68%);
	}

	.corner {
		position: absolute;
		width: 22px;
		height: 22px;
		border: 0 solid color-mix(in srgb, var(--accent) 55%, var(--border-strong));
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
		position: relative;
		z-index: 1;
		background: #f8fafc;
		padding: 8px;
		border-radius: 10px;
		box-shadow: 0 6px 18px rgba(15, 23, 42, 0.16);
		max-width: 60%;
		height: auto;
	}

	.scan-hint {
		position: relative;
		z-index: 1;
		font-family: var(--font-data);
		font-size: 0.625rem;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		color: var(--text-muted);
	}

	.scan-beam {
		position: absolute;
		left: 18%;
		right: 18%;
		top: 20%;
		height: 2px;
		border-radius: 2px;
		background: linear-gradient(90deg, transparent, var(--accent) 18%, var(--accent) 82%, transparent);
		box-shadow: 0 0 14px color-mix(in srgb, var(--accent) 55%, transparent);
		animation: scan-sweep 3.4s ease-in-out infinite;
		pointer-events: none;
	}

	.record-card {
		position: relative;
		z-index: 2;
		width: 266px;
		margin: -24px 0 0 44px;
		padding: 0.875rem 1rem;
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-top: 2px solid color-mix(in srgb, var(--success) 65%, var(--border));
		border-radius: 12px;
		box-shadow: var(--shadow-sm);
		transform: rotate(-1.5deg);
	}

	.record-top {
		display: flex;
		align-items: center;
		gap: 0.45rem;
	}

	.record-dot {
		width: 7px;
		height: 7px;
		border-radius: 50%;
		background: var(--success);
		box-shadow: 0 0 0 3px color-mix(in srgb, var(--success) 14%, transparent);
		flex: none;
	}

	.record-status {
		font-size: 0.75rem;
		font-weight: 700;
		color: var(--text-strong);
	}

	.record-time {
		margin-left: auto;
		font-size: 0.625rem;
		letter-spacing: 0.05em;
		color: var(--text-muted);
	}

	.record-name {
		margin: 0.5rem 0 0.125rem;
		font-size: 0.9375rem;
		font-weight: 700;
		letter-spacing: -0.01em;
		color: var(--text-strong);
	}

	.record-meta {
		margin: 0;
		font-size: 0.5625rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--text-muted);
	}

	.record-rows {
		display: flex;
		gap: 1.5rem;
		margin-top: 0.75rem;
		padding-top: 0.625rem;
		border-top: 1px dashed var(--border-strong);
	}

	.record-rows span {
		display: flex;
		flex-direction: column;
		gap: 0.1rem;
	}

	.record-rows em {
		font-style: normal;
		font-size: 0.5rem;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--text-muted);
	}

	.record-rows strong {
		font-size: 0.6875rem;
		font-weight: 600;
		color: var(--text-secondary);
	}

	.how,
	.features {
		max-width: 1080px;
		margin: 0 auto;
		padding: 5.5rem 2rem;
	}

	.how,
	.features {
		position: relative;
		border-top: 1px solid var(--border);
	}

	.how::before,
	.features::before {
		content: '';
		position: absolute;
		top: -1px;
		left: 2rem;
		width: 56px;
		height: 2px;
		background: var(--accent);
	}

	h2 {
		font-size: 2.125rem;
		font-weight: 700;
		color: var(--text-strong);
		margin: 0 0 2.25rem;
		letter-spacing: -0.03em;
		max-width: 22ch;
	}

	.steps {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 1.25rem;
	}

	.step-card {
		position: relative;
		overflow: hidden;
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 14px;
		padding: 1.75rem 1.5rem;
		transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
	}

	.step-card::before {
		content: '';
		position: absolute;
		top: 0;
		left: 0;
		width: 18px;
		height: 18px;
		border-top: 2px solid var(--accent);
		border-left: 2px solid var(--accent);
		border-top-left-radius: 14px;
		opacity: 0.75;
	}

	.step-card::after {
		content: attr(data-step);
		position: absolute;
		top: 0.25rem;
		right: 0.75rem;
		font-family: var(--font-data);
		font-size: 3.25rem;
		font-weight: 700;
		line-height: 1;
		letter-spacing: -0.04em;
		color: color-mix(in srgb, var(--text-strong) 5%, transparent);
		pointer-events: none;
	}

	.step-card > * {
		position: relative;
		z-index: 1;
	}

	.step-card:hover {
		transform: translateY(-3px);
		border-color: color-mix(in srgb, var(--accent) 28%, var(--border));
		box-shadow: var(--shadow-sm);
	}

	.step-num {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 30px;
		height: 30px;
		border-radius: 8px;
		background: color-mix(in srgb, var(--accent) 10%, transparent);
		border: 1px solid color-mix(in srgb, var(--accent) 24%, transparent);
		color: var(--accent);
		font-family: var(--font-data);
		font-weight: 700;
		font-size: 0.6875rem;
		letter-spacing: 0.04em;
		margin-bottom: 1.125rem;
	}

	.step-card h3,
	.feature h3 {
		font-size: 1.05rem;
		font-weight: 700;
		color: var(--text-strong);
		margin: 0 0 0.5rem;
	}

	.step-card p,
	.feature p {
		font-size: 0.9375rem;
		line-height: 1.55;
		color: var(--text-secondary);
		margin: 0;
	}

	.feature-grid {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 16px;
		overflow: hidden;
	}

	.feature {
		padding: 1.75rem;
		transition: background 0.15s ease;
	}

	.feature:nth-child(odd) {
		border-right: 1px solid var(--border);
	}

	.feature:nth-child(-n + 2) {
		border-bottom: 1px solid var(--border);
	}

	.feature:hover {
		background: var(--bg-muted);
	}

	.feature-top {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 1rem;
		margin-bottom: 1.25rem;
	}

	.feature-icon {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 48px;
		height: 48px;
		border-radius: 12px;
		background: color-mix(in srgb, var(--accent) 8%, var(--bg-muted));
		border: 1px solid color-mix(in srgb, var(--accent) 14%, transparent);
		color: var(--brand);
		flex: none;
	}

	.feature-tag {
		max-width: 12ch;
		text-align: right;
		font-family: var(--font-data);
		font-size: 0.625rem;
		font-weight: 500;
		line-height: 1.4;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--text-muted);
		padding-top: 0.25rem;
	}

	.footer {
		max-width: 1080px;
		margin: 0 auto;
		padding: 2rem 2rem 3rem;
		border-top: 1px solid var(--border);
	}

	.footer-inner {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1.5rem;
		flex-wrap: wrap;
	}

	.footer-brand {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		color: var(--text-strong);
		font-weight: 700;
		text-decoration: none;
	}

	.footer-logo {
		width: 26px;
		height: 26px;
		display: block;
	}

	.footer-name {
		font-size: 1rem;
		letter-spacing: -0.02em;
	}

	.footer-links {
		display: flex;
		align-items: center;
		gap: 1.25rem;
		flex-wrap: wrap;
	}

	.footer-link {
		color: var(--text-muted);
		font-size: 0.8125rem;
		text-decoration: none;
		transition: color 0.15s ease;
	}

	.footer-link:hover {
		color: var(--accent);
	}

	.footer-note {
		margin: 1.75rem 0 0;
		font-size: 0.5625rem;
		letter-spacing: 0.14em;
		text-transform: uppercase;
		color: var(--text-muted);
	}

	.hero-copy {
		animation: rise-in 0.55s cubic-bezier(0.22, 1, 0.36, 1) both;
	}

	.hero-visual {
		animation: rise-in 0.55s cubic-bezier(0.22, 1, 0.36, 1) 0.08s both;
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

	@keyframes scan-sweep {
		0%,
		100% {
			transform: translateY(0);
			opacity: 0.35;
		}
		50% {
			transform: translateY(170px);
			opacity: 1;
		}
	}

	@keyframes rise-in {
		from {
			opacity: 0;
			transform: translateY(14px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	@media (max-width: 900px) {
		.hero {
			grid-template-columns: 1fr;
			gap: 2.5rem;
			padding: 8rem 1.5rem 4rem;
			text-align: center;
		}

		.eyebrow {
			justify-content: center;
		}

		.hero-sub {
			margin-left: auto;
			margin-right: auto;
		}

		.hero-actions,
		.hero-note {
			justify-content: center;
		}

		.hero-visual {
			margin-top: 0.5rem;
		}

		.how,
		.features {
			padding: 4rem 1.5rem;
		}

		.how::before,
		.features::before {
			left: 1.5rem;
		}

		.steps,
		.feature-grid {
			grid-template-columns: 1fr;
		}

		.feature:nth-child(odd) {
			border-right: none;
		}

		.feature:not(:last-child) {
			border-bottom: 1px solid var(--border);
		}

		.record-card {
			margin-left: 24px;
		}

		h1 {
			font-size: 2.5rem;
		}

		h2 {
			font-size: 1.75rem;
		}

		.footer {
			padding: 2rem 1.5rem 2.5rem;
		}
	}

	@media (max-width: 560px) {
		.nav {
			padding: 0.625rem 1rem;
		}

		.nav-links {
			display: none;
		}

		.hero {
			padding: 6.5rem 1.25rem 3.5rem;
		}

		.hero-actions {
			flex-direction: column;
			align-items: stretch;
		}

		.btn-primary,
		.btn-ghost {
			width: 100%;
		}

		.phone {
			width: 252px;
		}

		.record-card {
			width: 100%;
			max-width: 280px;
			margin: -18px 0 0;
			transform: none;
		}

		.record-rows {
			gap: 1rem;
		}

		h1 {
			font-size: 2rem;
		}

		h2 {
			font-size: 1.5rem;
		}

		.footer-inner {
			flex-direction: column;
			align-items: flex-start;
			gap: 1rem;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.visual-stage,
		.hero-copy,
		.hero-visual {
			animation: none;
		}

		.scan-beam {
			display: none;
		}

		.btn-primary,
		.btn-ghost,
		.step-card {
			transition: none;
		}

		.btn-primary:hover,
		.btn-ghost:hover,
		.step-card:hover {
			transform: none;
		}
	}

	:global(a:focus-visible),
	:global(button:focus-visible) {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}
</style>