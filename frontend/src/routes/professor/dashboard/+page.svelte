<script lang="ts">
	import { goto } from '$app/navigation';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import { formatPercentage } from '$lib/shared/utils/format';
	import {
		Routes,
		professorActiveSession,
		professorSessionCreate,
	} from '$lib/shared/constants/routes';

	// Fixture data. The professor session endpoints are still prefix-only router
	// stubs on the backend, so this page is driven by local data until the
	// service layer lands. The KPI row is derived from the list below it rather
	// than hardcoded, so the numbers can never contradict the sessions shown.
	type SessionStatus = 'active' | 'upcoming' | 'completed';

	type DashboardSession = {
		id: number;
		offeringId: number;
		code: string;
		name: string;
		section: string;
		room: string;
		startsAt: string;
		endsAt: string;
		scanned: number;
		enrolled: number;
		status: SessionStatus;
	};

	// Status colours follow the wireframe status palette (docs/design/wireframes.md).
	const STATUS_COLORS: Record<SessionStatus, string> = {
		active: '#16a34a',
		upcoming: '#ca8a04',
		completed: '#94a3b8',
	};

	const sessions: DashboardSession[] = [
		{
			id: 1,
			offeringId: 1,
			code: 'CS101',
			name: 'Software Engineering',
			section: 'A',
			room: 'Room 204',
			startsAt: '8:30 AM',
			endsAt: '10:00 AM',
			scanned: 18,
			enrolled: 30,
			status: 'active',
		},
		{
			id: 2,
			offeringId: 2,
			code: 'MATH202',
			name: 'Calculus 2',
			section: 'B',
			room: 'Room 105',
			startsAt: '1:00 PM',
			endsAt: '2:30 PM',
			scanned: 0,
			enrolled: 25,
			status: 'upcoming',
		},
		{
			id: 3,
			offeringId: 3,
			code: 'PHYS303',
			name: 'Physics 3',
			section: 'A',
			room: 'Lab 2',
			startsAt: '3:30 PM',
			endsAt: '5:00 PM',
			scanned: 34,
			enrolled: 40,
			status: 'completed',
		},
	];

	// A same-day average across the week; not derivable from today's snapshot.
	const AVG_ATTENDANCE = 92;

	const today = $derived(
		new Date().toLocaleDateString(undefined, {
			weekday: 'long',
			year: 'numeric',
			month: 'long',
			day: 'numeric',
		})
	);

	// The live session gets its own hero card, so everything else drops into the
	// compact list. At most one session can be live at a time in this view.
	const liveSession = $derived(sessions.find((s) => s.status === 'active'));
	const otherSessions = $derived(sessions.filter((s) => s.status !== 'active'));

	const scanPercent = (session: DashboardSession) =>
		session.enrolled === 0 ? 0 : Math.round((session.scanned / session.enrolled) * 100);

	const kpis = $derived([
		{
			label: 'Active Sessions',
			value: `${sessions.filter((s) => s.status === 'active').length}/${sessions.length}`,
			sub: 'Today',
		},
		{
			label: 'Students',
			value: String(sessions.reduce((total, s) => total + s.enrolled, 0)),
			sub: 'Enrolled total',
		},
		{
			label: 'Avg Attendance',
			value: formatPercentage(AVG_ATTENDANCE),
			sub: 'This week',
		},
	]);

	const statusText = (session: DashboardSession) => {
		if (session.status === 'upcoming') return `Not started · ${session.startsAt}`;
		return `Closed · ${session.scanned}/${session.enrolled} scanned`;
	};
</script>

<div class="dashboard">
	<header class="header">
		<div>
			<h1>Professor Dashboard</h1>
			<p class="muted">{today}</p>
		</div>
	</header>

	{#if liveSession}
		<section class="hero">
			<article class="live-card">
				<span class="live-rail" style="background: {STATUS_COLORS.active}" aria-hidden="true"></span>

				<div class="live-body">
					<div class="live-head">
						<span class="live-pill">
							<span class="live-dot" aria-hidden="true"></span>
							Live
						</span>
						<h2 class="live-title">{liveSession.code} — {liveSession.name}</h2>
					</div>

					<p class="live-sub">
						{liveSession.section} · {liveSession.room}
					</p>

					<div class="live-stats">
						<div class="live-metric">
							<span class="metric-value">
								{liveSession.scanned}<span class="metric-of">/{liveSession.enrolled}</span>
							</span>
							<span class="metric-label">Scanned</span>
						</div>
						<div class="live-metric">
							<span class="metric-value">{liveSession.enrolled - liveSession.scanned}</span>
							<span class="metric-label">Remaining</span>
						</div>
						<div class="live-metric">
							<span class="metric-value">{liveSession.endsAt}</span>
							<span class="metric-label">Class ends</span>
						</div>
					</div>

					<div
						class="live-progress"
						role="progressbar"
						aria-label="Scan progress"
						aria-valuenow={liveSession.scanned}
						aria-valuemin={0}
						aria-valuemax={liveSession.enrolled}
					>
						<span
							class="live-fill"
							style="width: {scanPercent(liveSession)}%; background: {STATUS_COLORS.active}"
						></span>
					</div>

					<div class="live-actions">
						<button
							class="btn btn-primary"
							data-testid="view-live"
							onclick={() => goto(professorActiveSession(liveSession.id))}
						>
							<AppIcon name="qr" size={18} />
							View Live
						</button>
					</div>
				</div>
			</article>
		</section>
	{/if}

	<section class="kpis">
		{#each kpis as kpi (kpi.label)}
			<div class="kpi">
				<span class="kpi-value">{kpi.value}</span>
				<span class="kpi-label">{kpi.label}</span>
				<span class="kpi-sub">{kpi.sub}</span>
			</div>
		{/each}
	</section>

	<section class="actions">
		<button
			class="btn btn-primary"
			data-testid="new-session"
			onclick={() => goto(Routes.PROFESSOR_SESSIONS_CREATE)}
		>
			<AppIcon name="plus" size={18} />
			New Session
		</button>
		<button class="btn btn-secondary" disabled title="Reports arrive in Phase 7">
			<AppIcon name="file" size={18} />
			Export Report
		</button>
	</section>

	<section class="card">
		<h2 class="section-title">Today's Sessions</h2>
		{#if otherSessions.length > 0}
			<ul>
				{#each otherSessions as session (session.id)}
					<li>
						<span
							class="row-rail"
							style="background: {STATUS_COLORS[session.status]}"
							aria-hidden="true"
						></span>
						<div class="row-main">
							<span class="row-title">{session.code} — {session.name}</span>
							<span class="row-data">
								<span
									class="row-dot"
									style="background: {STATUS_COLORS[session.status]}"
									aria-hidden="true"
								></span>
								{statusText(session)} · {session.section}
							</span>
						</div>
						{#if session.status === 'upcoming'}
							<button
								class="btn btn-secondary"
								onclick={() => goto(professorSessionCreate(session.offeringId))}
							>
								Open Session
							</button>
						{:else}
							<span class="row-tag">Closed</span>
						{/if}
					</li>
				{/each}
			</ul>
		{:else}
			<p class="empty">No other sessions scheduled today.</p>
		{/if}
	</section>
</div>

<style>
	.dashboard {
		display: flex;
		flex-direction: column;
		gap: 2rem;
		font-family: system-ui, sans-serif;
	}

	.header h1 {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.625rem;
		font-weight: 700;
		color: #1e293b;
		margin: 0 0 0.25rem;
	}

	.muted {
		color: #64748b;
		font-size: 0.875rem;
		margin: 0;
	}

	/* --- Live session hero --------------------------------------------------- */

	.hero {
		display: grid;
		grid-template-columns: minmax(0, 1fr);
	}

	.live-card {
		display: flex;
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 8px;
		box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
		overflow: hidden;
	}

	.live-rail {
		width: 6px;
		flex-shrink: 0;
	}

	.live-body {
		flex: 1 1 auto;
		min-width: 0;
		padding: 1.75rem 2rem 2rem;
	}

	.live-head {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.75rem;
	}

	.live-pill {
		display: inline-flex;
		align-items: center;
		gap: 0.4375rem;
		padding: 0.25rem 0.625rem;
		border-radius: 99px;
		background: #f0fdf4;
		border: 1px solid #bbf7d0;
		color: #15803d;
		font-size: 0.75rem;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
	}

	.live-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: #16a34a;
		animation: pulse 2s ease-in-out infinite;
	}

	@keyframes pulse {
		0%,
		100% {
			opacity: 1;
			transform: scale(1);
		}
		50% {
			opacity: 0.45;
			transform: scale(0.8);
		}
	}

	/* The course is the headline; everything else hangs beneath it. */
	.live-title {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.25rem;
		font-weight: 700;
		color: #1e293b;
		margin: 0;
		line-height: 1.25;
	}

	.live-sub {
		margin: 0.375rem 0 0;
		font-size: 0.875rem;
		color: #64748b;
	}

	.live-stats {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 1rem;
		margin: 1.5rem 0 1.25rem;
	}

	.live-metric {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
	}

	.metric-value {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.5rem;
		font-weight: 700;
		color: #0f172a;
		line-height: 1.1;
	}

	.metric-of {
		font-size: 1rem;
		font-weight: 600;
		color: #94a3b8;
	}

	.metric-label {
		font-size: 0.6875rem;
		font-weight: 600;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: #64748b;
	}

	.live-progress {
		height: 8px;
		border-radius: 99px;
		background: #e2e8f0;
		overflow: hidden;
	}

	.live-fill {
		display: block;
		height: 100%;
		border-radius: 99px;
		transition: width 0.3s ease;
	}

	.live-actions {
		display: flex;
		gap: 0.75rem;
		margin-top: 1.5rem;
	}

	/* --- KPI row ------------------------------------------------------------- */

	.kpis {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 1rem;
	}

	.kpi {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		padding: 1.25rem;
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 8px;
	}

	.kpi-value {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.75rem;
		font-weight: 700;
		color: #1e293b;
		line-height: 1;
	}

	.kpi-label {
		font-size: 0.8125rem;
		color: #64748b;
	}

	.kpi-sub {
		font-size: 0.75rem;
		color: #94a3b8;
	}

	/* --- Quick actions ------------------------------------------------------- */

	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
	}

	/* --- Buttons ------------------------------------------------------------- */

	.btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		padding: 0.75rem 1.25rem;
		border-radius: 8px;
		font-size: 0.9375rem;
		font-weight: 600;
		font-family: inherit;
		cursor: pointer;
		white-space: nowrap;
		transition: background 0.15s ease, border-color 0.15s ease, transform 0.15s ease;
	}

	.btn:focus-visible {
		outline: 2px solid #2563eb;
		outline-offset: 2px;
	}

	.btn-primary {
		background: #1e3a5f;
		border: 1px solid #1e3a5f;
		color: white;
		box-shadow: 0 4px 14px rgba(30, 58, 95, 0.28);
	}

	.btn-primary:hover {
		background: #16324f;
		border-color: #16324f;
		transform: translateY(-1px);
	}

	.btn-secondary {
		background: white;
		border: 1px solid #cbd5e1;
		color: #0f172a;
	}

	.btn-secondary:hover:not(:disabled) {
		background: #f1f5f9;
	}

	.btn-secondary:disabled {
		color: #94a3b8;
		background: #f8fafc;
		cursor: not-allowed;
	}

	/* --- Today's sessions ---------------------------------------------------- */

	.card {
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 8px;
		padding: 2rem;
		box-shadow: 0 4px 16px rgba(15, 23, 42, 0.06);
		transition: box-shadow 0.15s ease;
	}

	.card:hover {
		box-shadow: 0 6px 24px rgba(15, 23, 42, 0.1);
	}

	.section-title {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.0625rem;
		font-weight: 700;
		color: #1e293b;
		margin: 0 0 1rem;
	}

	ul {
		list-style: none;
		padding: 0;
		margin: 0;
	}

	li {
		display: flex;
		align-items: center;
		gap: 0.875rem;
		padding: 0.875rem 0;
		border-bottom: 1px solid #f1f5f9;
	}

	li:first-child {
		padding-top: 0.25rem;
	}

	li:last-child {
		border-bottom: none;
		padding-bottom: 0;
	}

	.row-rail {
		width: 4px;
		height: 44px;
		border-radius: 99px;
		flex-shrink: 0;
	}

	.row-main {
		flex: 1 1 auto;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 0.1875rem;
	}

	/* Title leads, data follows beneath it. */
	.row-title {
		font-size: 0.9375rem;
		font-weight: 700;
		color: #0f172a;
	}

	.row-data {
		display: flex;
		align-items: center;
		gap: 0.4375rem;
		font-size: 0.8125rem;
		color: #64748b;
	}

	.row-dot {
		width: 7px;
		height: 7px;
		border-radius: 50%;
		flex-shrink: 0;
	}

	.row-tag {
		font-size: 0.75rem;
		font-weight: 600;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		color: #94a3b8;
		flex-shrink: 0;
	}

	.empty {
		color: #64748b;
		font-size: 0.9375rem;
		margin: 0;
	}

	@media (max-width: 640px) {
		.kpis,
		.live-stats {
			grid-template-columns: minmax(0, 1fr);
		}

		.actions .btn {
			flex: 1 1 auto;
		}

		.live-body,
		.card {
			padding: 1.25rem;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.live-dot {
			animation: none;
		}

		.btn,
		.live-fill {
			transition: none;
		}
	}
</style>
