<script lang="ts">
	import SkeletonCards from '$lib/components/SkeletonCards.svelte';
	import SkeletonTable from '$lib/components/SkeletonTable.svelte';
	import { goto } from '$app/navigation';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import { formatLocalDateTime, formatPercentage } from '$lib/shared/utils/format';
	import { Routes, professorActiveSession } from '$lib/shared/constants/routes';
	import type { ProfessorDashboardResponse } from '$lib/shared/types';

	import { onMount } from 'svelte';
	import { listSessions } from '$lib/features/session/service';
	import { getDashboard } from '$lib/features/professor/service';

	// Two calls, not four.
	//
	// GET /professor/dashboard supplies the KPI row and the per-session
	// scanned/enrolled counts. GET /professor/sessions still supplies the
	// session list itself, because the dashboard summary carries no course
	// identity — no code, name, section, or clock time — so the table cannot be
	// built from it alone. Counts are joined onto rows by `session_id`.
	//
	// Two figures genuinely improve by coming from the summary rather than being
	// computed here: `total_students` is the distinct active roster across the
	// professor's offerings (summing per-offering enrollments double-counts
	// anyone in two of their courses), and `avg_rate` is term-wide compliance
	// taken from the same report figure the Reports page shows.
	type SessionStatus = 'scheduled' | 'active' | 'closed';

	type DashboardSession = {
		id: number;
		offeringId: number;
		code: string;
		name: string;
		section: string;
		endsAt: string;
		scanned: number;
		enrolled: number;
		status: SessionStatus;
		createdAt: string;
	};

	// Status colours follow the wireframe status palette (docs/design/wireframes.md).
	const STATUS_COLORS: Record<SessionStatus, string> = {
		scheduled: '#2563eb',
		active: '#16a34a',
		closed: 'var(--text-muted)'
	};

	// "Today" is UTC on both endpoints — the dashboard summary anchors on
	// Session.created_at within the UTC day, and the session list is asked for
	// the same window so the two sets line up and every row finds its counts.
	// Deriving this key in local time would drift by a day either side of
	// midnight and leave rows with no matching tile.
	const toUtcDayKey = (date: Date): string => date.toISOString().slice(0, 10);

	const formatClock = (iso: string | null): string =>
		iso ? formatLocalDateTime(iso, { time: { hour: 'numeric', minute: '2-digit' } }) : '—';

	let sessions = $state<DashboardSession[]>([]);
	let summary = $state<ProfessorDashboardResponse | null>(null);
	let loading = $state(true);
	let loadError = $state<string | null>(null);

	const today = $derived(
		formatLocalDateTime(new Date(), {
			date: {
				weekday: 'long',
				year: 'numeric',
				month: 'long',
				day: 'numeric'
			}
		})
	);

	const load = async () => {
		loading = true;
		loadError = null;
		try {
			const [dashboard, list] = await Promise.all([
				getDashboard(),
				listSessions({ from: toUtcDayKey(new Date()), to: toUtcDayKey(new Date()), size: 100 })
			]);
			summary = dashboard;

		// Tile counts are authoritative — the backend builds them in one
		// batched query over the same window — so they win over anything
		// derivable from the list row. The list fallback only covers a tile
		// the summary did not return. List rows carry present/late/absent
		// only (no excused/pending on the contract), so the fallback is a
		// lower bound, not an exact enrollment.
		const tiles = new Map(dashboard.today_sessions.map((t) => [t.session_id, t]));
		sessions = list.items
			.map((item) => {
				const tile = tiles.get(item.id);
				const seats =
					tile?.enrolled ?? item.presentCount + item.lateCount + item.absentCount;
				return {
					id: item.id,
					offeringId: item.offeringId,
					code: item.courseCode,
					name: item.courseName,
					section: item.section,
					endsAt: formatClock(item.scheduledEndTime),
					scanned: tile?.scanned ?? item.presentCount + item.lateCount,
					enrolled: seats,
					status: item.status,
					createdAt: item.createdAt
				};
			})
			.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
		} catch (e) {
			loadError = e instanceof Error ? e.message : 'Unable to load dashboard.';
			sessions = [];
			summary = null;
		} finally {
			loading = false;
		}
	};

	onMount(() => {
		void load();
	});

	// The live session gets its own hero card, so everything else drops into the
	// compact list. At most one session is live at a time per offering; the
	// first active one takes the hero.
	const liveSession = $derived(sessions.find((s) => s.status === 'active'));
	const otherSessions = $derived(
		sessions.filter((s) => s.status !== 'active' || s.id !== liveSession?.id)
	);

	const scanPercent = (session: DashboardSession) =>
		session.enrolled === 0 ? 0 : Math.round((session.scanned / session.enrolled) * 100);

	// `sessions_completed / sessions_today` reads as "N of M done" for today.
	// The backend decides what counts as completed (a session reads closed once
	// expires_at has passed), so this is not the client-side status count the
	// list rows use.
	const kpis = $derived([
		{
			label: 'Sessions Today',
			value: loading || !summary ? '—' : `${summary.sessions_completed}/${summary.sessions_today}`,
			sub: 'Completed'
		},
		{
			label: 'Students',
			value: loading || !summary ? '—' : String(summary.total_students),
			sub: 'Distinct enrolled'
		},
		{
			label: 'Avg Compliance',
			// avg_rate arrives as a 0-1 fraction (backend `_rates`), so it needs
			// scaling before formatting — same as the Reports page.
			value: loading || !summary ? '—' : formatPercentage(summary.avg_rate * 100),
			sub: 'This term'
		}
	]);

	const statusText = (session: DashboardSession) => {
		if (session.status === 'active') return `Open · ${session.scanned}/${session.enrolled} scanned`;
		return `Closed · ${session.scanned}/${session.enrolled} scanned`;
	};
</script>

<div class="dashboard page-enter">
	<header class="header">
		<div>
			<h1>Professor Dashboard</h1>
			<p class="muted">{today}</p>
		</div>
	</header>

	{#if loadError}
		<section class="card">
			<p class="error">{loadError}</p>
			<button class="btn btn-secondary" type="button" onclick={() => void load()}>Try again</button>
		</section>
	{:else if loading}
		<SkeletonCards count={3} label="Loading today's sessions…" />
		<SkeletonTable rows={4} cols={6} />
	{:else if liveSession}
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
						Section {liveSession.section}
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

	{#if !loadError && !loading}
		<section class="kpis">
			{#each kpis as kpi (kpi.label)}
				<div class="kpi">
					<span class="kpi-value">{kpi.value}</span>
					<span class="kpi-label">{kpi.label}</span>
					<span class="kpi-sub">{kpi.sub}</span>
				</div>
			{/each}
		</section>
	{/if}

	<section class="actions">
		<button
			class="btn btn-primary"
			data-testid="new-session"
			onclick={() => goto(Routes.PROFESSOR_SESSIONS_CREATE)}
		>
			<AppIcon name="plus" size={18} />
			New Session
		</button>
		<button
			class="btn btn-secondary"
			data-testid="view-reports"
			onclick={() => goto(Routes.PROFESSOR_REPORTS)}
		>
			<AppIcon name="file" size={18} />
			View Reports
		</button>
	</section>

	{#if !loadError && !loading}
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
									{statusText(session)} · Section {session.section}
								</span>
							</div>
							{#if session.status === 'active'}
								<button
									class="btn btn-secondary"
									onclick={() => goto(professorActiveSession(session.id))}
								>
									View Live
								</button>
							{:else}
								<span class="row-tag">Closed</span>
							{/if}
						</li>
					{/each}
				</ul>
			{:else if !liveSession}
				<p class="empty">No sessions today. Open one to start taking attendance.</p>
			{:else}
				<p class="empty">No other sessions today.</p>
			{/if}
		</section>
	{/if}
</div>

<style>
	.dashboard {
		display: flex;
		flex-direction: column;
		gap: 2rem;
	}

	.header h1 {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.625rem;
		font-weight: 700;
		color: var(--text);
		margin: 0 0 0.25rem;
	}

	.muted {
		color: var(--text-muted);
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
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		box-shadow: var(--shadow-sm);
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
		background: var(--success-bg);
		border: 1px solid var(--success-bg);
		color: var(--success);
		font-size: 0.75rem;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
	}

	.live-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--success);
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
		color: var(--text);
		margin: 0;
		line-height: 1.25;
	}

	.live-sub {
		margin: 0.375rem 0 0;
		font-size: 0.875rem;
		color: var(--text-muted);
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
		color: var(--text-strong);
		line-height: 1.1;
	}

	.metric-of {
		font-size: 1rem;
		font-weight: 600;
		color: var(--text-muted);
	}

	.metric-label {
		font-size: 0.6875rem;
		font-weight: 600;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--text-muted);
	}

	.live-progress {
		height: 8px;
		border-radius: 99px;
		background: var(--border);
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
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
	}

	.kpi-value {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.75rem;
		font-weight: 700;
		color: var(--text);
		line-height: 1;
	}

	.kpi-label {
		font-size: 0.8125rem;
		color: var(--text-muted);
	}

	.kpi-sub {
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	/* --- Quick actions ------------------------------------------------------- */

	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
	}

	/* --- Buttons ------------------------------------------------------------- */

	/* Intentional dashboard CTA: shared colors plus a raised shadow. */
	.btn-primary {
		box-shadow: 0 4px 14px rgba(30, 58, 95, 0.28);
		transition:
			background 0.15s ease,
			border-color 0.15s ease,
			transform 0.15s ease;
	}

	.btn-primary:hover {
		transform: translateY(-1px);
	}

	.btn-secondary:disabled {
		/* Shared .btn:disabled adds opacity; keep the grey state solid. */
		opacity: 1;
		color: var(--text-muted);
		background: var(--bg-page);
		cursor: not-allowed;
	}

	/* --- Today's sessions ---------------------------------------------------- */

	.card {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 2rem;
		box-shadow: var(--shadow-sm);
		transition: box-shadow 0.15s ease;
	}

	.card:hover {
		box-shadow: var(--shadow-sm);
	}

	.section-title {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.0625rem;
		font-weight: 700;
		color: var(--text);
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
		border-bottom: 1px solid var(--divider);
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
		color: var(--text-strong);
	}

	.row-data {
		display: flex;
		align-items: center;
		gap: 0.4375rem;
		font-size: 0.8125rem;
		color: var(--text-muted);
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
		color: var(--text-muted);
		flex-shrink: 0;
	}

	.empty {
		color: var(--text-muted);
		font-size: 0.9375rem;
		margin: 0;
	}

	.error {
		color: var(--danger-strong);
		font-size: 0.9375rem;
		margin: 0 0 1rem;
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
