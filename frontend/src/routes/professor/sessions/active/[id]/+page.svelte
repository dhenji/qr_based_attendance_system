<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import {
		closeSession,
		getActiveSession
	} from '$lib/features/session/service';
	import { Routes, professorSessionCreate } from '$lib/shared/constants/routes';

	type LiveSession = Awaited<ReturnType<typeof getActiveSession>>;

	const POLL_MS = 3000;
	const TICK_MS = 1000;
	const EXPIRING_SOON_SECONDS = 5 * 60;
	const PAGE_SIZE = 10;

	// No excuse actions: there are no excuse endpoints on the backend yet, so
	// the feed is read-only and the Action column is gone with them.
	type SortKey = 'time' | 'name' | 'status';
	type SortDirection = 'asc' | 'desc';
	type FeedRow = LiveSession['students'][number];

	const STATUS_SORT_ORDER: Record<FeedRow['status'], number> = {
		present: 0,
		late: 1,
		excused: 2,
		pending: 3,
		absent: 4,
		rejected: 5
	};

	const sessionId = $derived.by(() => {
		const raw = page.params.id;
		if (!raw) return null;
		const parsed = Number(raw);
		return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
	});

	let session = $state<LiveSession | null>(null);
	let scanSnapshotAt = $state<number | null>(null);
	let scanSnapshotRemaining = $state<number | null>(null);
	let now = $state(0);
	let isLoading = $state(true);
	let loadError = $state<string | null>(null);
	let refreshError = $state<string | null>(null);
	let closing = $state(false);
	let closedNotice = $state(false);
	let reloadToken = $state(0);
	let sortKey = $state<SortKey>('time');
	let sortDirection = $state<SortDirection>('asc');
	let currentPage = $state(1);
	let tableScroller = $state<HTMLDivElement | undefined>(undefined);

	$effect(() => {
		const id = sessionId;
		reloadToken;

		if (id === null) {
			session = null;
			isLoading = false;
			loadError = 'That live session link is not valid. Open it from a generated session instead.';
			return;
		}

		let cancelled = false;
		let poll: number | undefined;
		let tick: number | undefined;
		currentPage = 1;

		const load = async (initial: boolean) => {
			if (initial) {
				isLoading = true;
				loadError = null;
			}

			try {
				const requestStartedAt = Date.now();
				const live = await getActiveSession(id);
				if (cancelled) return;

				session = live;
				// Anchor the countdown to when the server snapshot was requested,
				// not when the promise resolved. Otherwise every poll adds fetch
				// latency back into the displayed timer. Seeding now here also
				// prevents the first paint from calculating against its zero value.
				scanSnapshotAt = requestStartedAt;
				scanSnapshotRemaining = live.scanWindowRemaining;
				now = Date.now();
				loadError = null;
				refreshError = null;
			} catch {
				if (cancelled) return;
				if (session === null) loadError = 'The live session could not be loaded.';
				else refreshError = 'The live feed failed to refresh. Showing the last update.';
			} finally {
				if (!cancelled && initial) isLoading = false;
			}
		};

		void load(true);
		poll = window.setInterval(() => void load(false), POLL_MS);
		tick = window.setInterval(() => {
			if (!cancelled) now = Date.now();
		}, TICK_MS);

		return () => {
			cancelled = true;
			window.clearInterval(poll);
			window.clearInterval(tick);
		};
	});

	// scanWindowRemaining is a server-computed snapshot rather than an absolute
	// expiry. Rebuild the absolute expiry from the moment the snapshot was
	// requested, then count down from the current clock every second. This keeps
	// the visible timer monotonic between polls and correct after tab throttling.
	const scanExpiresAt = $derived(
		scanSnapshotAt === null || scanSnapshotRemaining === null
			? null
			: scanSnapshotAt + scanSnapshotRemaining * 1000
	);
	const scanRemainingSeconds = $derived.by(() => {
		if (scanExpiresAt === null) return null;
		return Math.max(0, Math.floor((scanExpiresAt - now) / 1000));
	});

	const classEndsAt = $derived(session ? new Date(session.scheduledEndTime).getTime() : null);
	const classRemainingSeconds = $derived.by(() => {
		if (classEndsAt === null) return null;
		return Math.max(0, Math.floor((classEndsAt - now) / 1000));
	});

	const isClosed = $derived(session?.status === 'closed');
	const closedSession = $derived(isClosed ? session : null);
	const scanExpired = $derived(scanRemainingSeconds !== null && scanRemainingSeconds <= 0);
	const expiredSession = $derived(!isClosed && scanExpired);
	const scanned = $derived(session ? session.counts.present + session.counts.late : 0);
	const expiringSoon = $derived(
		scanRemainingSeconds !== null &&
			scanRemainingSeconds > 0 &&
			scanRemainingSeconds <= EXPIRING_SOON_SECONDS
	);

	const formatCountdown = (totalSeconds: number): string => {
		const hours = Math.floor(totalSeconds / 3600);
		const minutes = Math.floor((totalSeconds % 3600) / 60);
		const seconds = totalSeconds % 60;
		return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
	};

	const formatClock = (iso: string): string =>
		new Date(iso).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });

	const formatDateTime = (timestamp: number): string => {
		const date = new Date(timestamp);
		const today = new Date();
		const day =
			date.toDateString() === today.toDateString()
				? 'Today'
				: date.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
		return `${day}, ${date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}`;
	};

	const scanEndedText = $derived(scanExpiresAt === null ? null : formatDateTime(scanExpiresAt));

	const sortedStudents = $derived.by<FeedRow[]>(() => {
		if (!session) return [];
		const direction = sortDirection === 'asc' ? 1 : -1;
		const rows = [...session.students];

		const byTime = (row: FeedRow): number =>
			row.scannedAt ? new Date(row.scannedAt).getTime() : Number.NaN;
		const byName = (a: FeedRow, b: FeedRow): number =>
			a.name.localeCompare(b.name) || a.studentNumber.localeCompare(b.studentNumber);

		rows.sort((a, b) => {
			switch (sortKey) {
				case 'time': {
					const aMissing = Number.isNaN(byTime(a)) ? 1 : 0;
					const bMissing = Number.isNaN(byTime(b)) ? 1 : 0;
					if (aMissing !== bMissing) return aMissing - bMissing;
					if (aMissing === 1) return byName(a, b) * direction;
					return (byTime(a) - byTime(b) || a.studentNumber.localeCompare(b.studentNumber)) * direction;
				}
				case 'name':
					return byName(a, b) * direction;
			case 'status':
				return (
					(STATUS_SORT_ORDER[a.status] - STATUS_SORT_ORDER[b.status] ||
						byTime(a) - byTime(b) ||
						byName(a, b)) * direction
				);
		}
	});

		return rows;
	});

	const pageCount = $derived(Math.max(1, Math.ceil(sortedStudents.length / PAGE_SIZE)));
	const safePage = $derived(Math.min(Math.max(1, currentPage), pageCount));
	const pagedStudents = $derived(
		sortedStudents.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE)
	);
	const pageNumbers = $derived(Array.from({ length: pageCount }, (_, index) => index + 1));
	const rangeText = $derived.by(() => {
		if (sortedStudents.length === 0) return '0 of 0 students';
		const start = (safePage - 1) * PAGE_SIZE + 1;
		const end = Math.min(safePage * PAGE_SIZE, sortedStudents.length);
		return `${start}–${end} of ${sortedStudents.length} students`;
	});

	const scrollFeedToTop = () => {
		tableScroller?.scrollTo({ top: 0 });
	};

	const setSort = (key: SortKey) => {
		if (sortKey === key) sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
		else {
			sortKey = key;
			sortDirection = 'asc';
		}
		currentPage = 1;
		scrollFeedToTop();
	};

	const gotoPage = (pageNumber: number) => {
		currentPage = Math.min(Math.max(1, pageNumber), pageCount);
		scrollFeedToTop();
	};

	const sortArrow = (key: SortKey): string => {
		if (sortKey !== key) return '↕';
		return sortDirection === 'asc' ? '▲' : '▼';
	};

	const sortLabel = (key: SortKey, label: string): string => {
		if (sortKey !== key) return `Sort by ${label.toLowerCase()} ascending`;
		return `Sort by ${label.toLowerCase()} ${sortDirection === 'asc' ? 'descending' : 'ascending'}`;
	};

	const ariaSort = (key: SortKey): 'ascending' | 'descending' | 'none' => {
		if (sortKey !== key) return 'none';
		return sortDirection === 'asc' ? 'ascending' : 'descending';
	};

	const refreshSession = async (): Promise<boolean> => {
		const id = sessionId;
		if (id === null) return false;

		try {
			const requestStartedAt = Date.now();
			const live = await getActiveSession(id);
			session = live;
			scanSnapshotAt = requestStartedAt;
			scanSnapshotRemaining = live.scanWindowRemaining;
			now = Date.now();
			loadError = null;
			refreshError = null;
			return true;
		} catch {
			refreshError = 'The live feed failed to refresh. Showing the last update.';
			return false;
		}
	};

	const goBack = () => {
		if (window.history.length > 1) window.history.back();
		else void goto(Routes.PROFESSOR_DASHBOARD);
	};

	const retry = () => {
		reloadToken += 1;
	};

	const handleClose = async () => {
		const id = sessionId;
		if (id === null || closing || isClosed) return;

		closing = true;
		refreshError = null;
		try {
			const requestStartedAt = Date.now();
			await closeSession(id);
			closedNotice = true;
			const live = await getActiveSession(id);
			session = live;
			scanSnapshotAt = requestStartedAt;
			scanSnapshotRemaining = live.scanWindowRemaining;
			now = Date.now();
		} catch {
			refreshError = 'The session could not be closed.';
		} finally {
			closing = false;
		}
	};
</script>

<div class="live">
	<header class="header">
		<button class="btn btn-ghost" type="button" onclick={goBack}>Back</button>
		{#if session}
			<div class="title">
				<h1>Active: {session.offeringCode} — {session.offeringName}</h1>
				<p class="muted">
					Section {session.offeringSections} · Code {session.sessionCode}
				</p>
			</div>
			<button
				class="btn btn-danger"
				type="button"
				disabled={closing || isClosed}
				onclick={handleClose}
			>
				{closing ? 'Closing…' : isClosed ? 'Closed' : 'Close'}
			</button>
		{:else}
			<div class="title">
				<h1>Live Session</h1>
				<p class="muted">Projector view for the active attendance session.</p>
			</div>
		{/if}
	</header>

	{#if loadError}
		<section class="card">
			<p class="error">{loadError}</p>
			{#if sessionId !== null}
				<button class="btn btn-secondary" type="button" onclick={retry}>Try again</button>
			{/if}
		</section>
	{:else if isLoading || !session || scanRemainingSeconds === null || classRemainingSeconds === null}
		<section class="card">
			<p class="muted">Loading live session…</p>
		</section>
	{:else}
		{#if refreshError}
			<p class="refresh-error" role="status">{refreshError}</p>
		{/if}
		{#if closedNotice}
			<p class="notice" role="status">Session closed. New scans are blocked.</p>
		{/if}

		<section class="card code-card" aria-label="Projector session code">
			<span class="code-label">Session Code · Show on projector</span>
			<span class="code">{session.sessionCode}</span>
			<div class="timers">
				<div class="timer" class:urgent={expiringSoon || scanExpired}>
					<span class="timer-label">Scan window</span>
					<span class="timer-value">{formatCountdown(scanRemainingSeconds)}</span>
				</div>
				<div class="timer">
					<span class="timer-label">Class ends in</span>
					<span class="timer-value">{formatCountdown(classRemainingSeconds)}</span>
					<span class="timer-sub">at {formatClock(session.scheduledEndTime)}</span>
				</div>
			</div>
		</section>

		<section class="tiles" aria-label="Session totals">
			<article class="tile">
				<span class="tile-value">{session.enrolledCount}</span>
				<span class="tile-label">Enrolled</span>
			</article>
			<article class="tile">
				<span class="tile-value">{scanned}</span>
				<span class="tile-label">Scanned</span>
			</article>
			<article class="tile">
				<span class="tile-value">{session.remaining}</span>
				<span class="tile-label">Remaining</span>
			</article>
		</section>

		<section class="card">
			<h2 class="section-title">Status</h2>
			<ul class="legend">
				<li><span class="dot dot-present" aria-hidden="true"></span>Present <strong>{session.counts.present}</strong></li>
				<li><span class="dot dot-late" aria-hidden="true"></span>Late <strong>{session.counts.late}</strong></li>
				<li><span class="dot dot-excused" aria-hidden="true"></span>Excused <strong>{session.counts.excused}</strong></li>
				<li><span class="dot dot-pending" aria-hidden="true"></span>Pending <strong>{session.counts.pending}</strong></li>
				<li><span class="dot dot-absent" aria-hidden="true"></span>Absent <strong>{session.counts.absent}</strong></li>
			</ul>
		</section>

		<section class="card">
			<div class="feed-head">
				<h2 class="section-title">Live Feed</h2>
				<span class="muted">Auto-refreshes every 3 seconds · {rangeText}</span>
			</div>
			<div class="table-wrap" role="region" aria-label="Live attendance feed" bind:this={tableScroller}>
				<table>
					<thead>
						<tr>
							<th scope="col" aria-sort={ariaSort('time')}>
								<button class="sort" type="button" onclick={() => setSort('time')} aria-label={sortLabel('time', 'Time')}>
									<span>Time</span>
									<span class="sort-arrow" class:active={sortKey === 'time'} aria-hidden="true">{sortArrow('time')}</span>
								</button>
							</th>
							<th scope="col" aria-sort={ariaSort('name')}>
								<button class="sort" type="button" onclick={() => setSort('name')} aria-label={sortLabel('name', 'Name')}>
									<span>Name</span>
									<span class="sort-arrow" class:active={sortKey === 'name'} aria-hidden="true">{sortArrow('name')}</span>
								</button>
							</th>
						<th scope="col" aria-sort={ariaSort('status')}>
							<button class="sort" type="button" onclick={() => setSort('status')} aria-label={sortLabel('status', 'Status')}>
								<span>Status</span>
								<span class="sort-arrow" class:active={sortKey === 'status'} aria-hidden="true">{sortArrow('status')}</span>
							</button>
						</th>
					</tr>
				</thead>
				<tbody>
					{#each pagedStudents as student (student.studentNumber)}
						<tr>
							<td>{student.scannedAt ? formatClock(student.scannedAt) : '—'}</td>
							<td>
								<div class="student-name">{student.name}</div>
								<div class="student-id">{student.studentNumber} · Section {student.section ?? '—'}</div>
								{#if student.excuseReason}
									<div class="student-id">{student.excuseReason}</div>
								{/if}
							</td>
							<td><span class="status status-{student.status}">{student.status}</span></td>
						</tr>
					{/each}
				</tbody>
				</table>
			</div>
			<nav class="pages" aria-label="Live feed pages">
				<button
					class="page"
					type="button"
					disabled={safePage <= 1}
					onclick={() => gotoPage(safePage - 1)}
					aria-label="Go to previous feed page"
				>
					Previous
				</button>
				{#each pageNumbers as pageNumber (pageNumber)}
					<button
						class="page"
						class:current={pageNumber === safePage}
						type="button"
						disabled={pageNumber === safePage}
						onclick={() => gotoPage(pageNumber)}
						aria-label={`Go to feed page ${pageNumber}`}
						aria-current={pageNumber === safePage ? 'page' : undefined}
					>
						{pageNumber}
					</button>
				{/each}
				<button
					class="page"
					type="button"
					disabled={safePage >= pageCount}
					onclick={() => gotoPage(safePage + 1)}
					aria-label="Go to next feed page"
				>
					Next
				</button>
			</nav>
		</section>

		{#if scanExpired}
			<section class="card sync" role="status">
				<AppIcon name="offline" size={18} />
				<div>
					<strong>{isClosed ? 'Session closed' : expiredSession ? 'Session expired' : 'Scanning closed'}</strong>
					<span>
						{#if expiredSession && scanEndedText}
							Scan window ended at {scanEndedText} ·
						{/if}
						Waiting for offline syncs · {session.pendingSyncCount} records pending sync
					</span>
				</div>
			</section>
		{/if}

		<section class="card excuse-all">
			<div>
				<h2 class="section-title">Excuse actions</h2>
				<p class="muted">
					Quick-excuse, editing, revoking, and bulk excuse need excuse endpoints,
					which the backend does not expose yet. The feed above stays read-only
					until that slice lands.
				</p>
			</div>
		</section>

		<div class="footer">
			<button class="btn btn-secondary" type="button" disabled title="Export is the next slice">
				Export Current
			</button>
			<button class="btn btn-secondary" type="button" disabled title="Print is the next slice">
				Print
			</button>
			<button class="btn btn-secondary" type="button" disabled title="History is the next slice">
				View All
			</button>
			{#if closedSession}
				<button
					class="btn btn-primary"
					type="button"
					onclick={() => goto(professorSessionCreate(closedSession.offeringId))}
				>
					Open another session
				</button>
			{/if}
		</div>
	{/if}
</div>

<style>
	.live {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
		max-width: 1000px;
		margin: 0 auto;
		font-family: system-ui, sans-serif;
	}

	.header {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		flex-wrap: wrap;
		gap: 1rem;
	}

	.title h1 {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.5rem;
		margin: 0 0 0.25rem;
		color: #1e293b;
	}

	.muted {
		margin: 0;
		color: #64748b;
		font-size: 0.875rem;
	}

	.card {
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 12px;
		padding: 1.5rem;
		box-shadow: 0 4px 16px rgba(15, 23, 42, 0.06);
	}

	.section-title {
		margin: 0;
		font-size: 1rem;
		font-weight: 700;
		color: #1e293b;
	}

	.btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		padding: 0.7rem 1.2rem;
		border-radius: 8px;
		border: 1px solid transparent;
		font: inherit;
		font-size: 0.9375rem;
		font-weight: 600;
		cursor: pointer;
	}

	.btn:focus-visible,
	.mini:focus-visible {
		outline: 2px solid #2563eb;
		outline-offset: 2px;
	}

	.btn-ghost {
		background: white;
		border-color: #cbd5e1;
		color: #0f172a;
	}

	.btn-primary {
		background: #1e3a5f;
		border-color: #1e3a5f;
		color: white;
	}

	.btn-secondary {
		background: white;
		border-color: #cbd5e1;
		color: #0f172a;
	}

	.btn-danger {
		background: #b91c1c;
		border-color: #b91c1c;
		color: white;
	}

	.btn:disabled {
		background: #f8fafc;
		border-color: #e2e8f0;
		color: #94a3b8;
		cursor: not-allowed;
		box-shadow: none;
	}

	.error {
		margin: 0 0 1rem;
		color: #b91c1c;
		font-weight: 600;
	}

	.refresh-error,
	.notice {
		margin: 0;
		border-radius: 8px;
		padding: 0.75rem 1rem;
		font-size: 0.875rem;
	}

	.refresh-error {
		background: #fef2f2;
		border: 1px solid #fecaca;
		color: #b91c1c;
	}

	.notice {
		background: #f0fdf4;
		border: 1px solid #bbf7d0;
		color: #15803d;
	}

	.code-card {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 1rem;
		background: linear-gradient(135deg, #f0fdf4, #dcfce7);
		border: 2px solid #22c55e;
		text-align: center;
		container-type: inline-size;
	}

	.code-label {
		font-size: 0.75rem;
		font-weight: 700;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		color: #15803d;
	}

	.code {
		font-family: 'JetBrains Mono', monospace;
		font-size: min(3.5rem, 16cqw);
		font-weight: 700;
		letter-spacing: 0.12em;
		line-height: 1;
		color: #14532d;
		max-width: 100%;
		overflow-wrap: anywhere;
	}

	.timers {
		display: flex;
		flex-wrap: wrap;
		justify-content: center;
		gap: 0.75rem;
	}

	.timer {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
		min-width: 11rem;
		padding: 0.75rem 1rem;
		border-radius: 10px;
		background: rgba(255, 255, 255, 0.78);
		border: 1px solid #bbf7d0;
	}

	.timer.urgent {
		border-color: #fca5a5;
	}

	.timer-label {
		font-size: 0.75rem;
		font-weight: 700;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: #15803d;
	}

	.timer.urgent .timer-label {
		color: #b91c1c;
	}

	.timer-value {
		font-variant-numeric: tabular-nums;
		font-size: 1.375rem;
		font-weight: 800;
		color: #14532d;
	}

	.timer-sub {
		font-size: 0.8125rem;
		color: #4d7c62;
	}

	.tiles {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 1rem;
	}

	.tile {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.25rem;
		padding: 1.25rem 1rem;
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 12px;
	}

	.tile-value {
		font-size: 2rem;
		font-weight: 800;
		font-variant-numeric: tabular-nums;
		color: #1e3a5f;
	}

	.tile-label {
		font-size: 0.8125rem;
		font-weight: 600;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		color: #64748b;
	}

	.legend {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem 1.5rem;
		list-style: none;
		margin: 1rem 0 0;
		padding: 0;
		color: #334155;
		font-size: 0.9375rem;
	}

	.legend li {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
	}

	.dot {
		width: 0.75rem;
		height: 0.75rem;
		border-radius: 999px;
	}

	.dot-present { background: #16a34a; }
	.dot-late { background: #f59e0b; }
	.dot-excused { background: #8b5cf6; }
	.dot-pending { background: #94a3b8; }
	.dot-absent { background: #dc2626; }

	.feed-head {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-bottom: 1rem;
	}

	.table-wrap {
		overflow: auto;
		max-height: 24rem;
		border: 1px solid #e2e8f0;
		border-radius: 8px;
	}

	table {
		width: 100%;
		min-width: 620px;
		border-collapse: collapse;
		font-size: 0.9375rem;
	}

	th,
	td {
		padding: 0.75rem;
		text-align: left;
		border-bottom: 1px solid #f1f5f9;
		vertical-align: top;
		color: #0f172a;
	}

	thead th {
		position: sticky;
		top: 0;
		z-index: 1;
		background: #f8fafc;
		font-size: 0.75rem;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: #64748b;
	}

	.sort {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		padding: 0.25rem 0.375rem;
		margin: -0.25rem -0.375rem;
		border: 0;
		border-radius: 6px;
		background: transparent;
		color: inherit;
		font: inherit;
		letter-spacing: inherit;
		text-transform: inherit;
		cursor: pointer;
		white-space: nowrap;
	}

	.sort:hover {
		background: #eef2f7;
		color: #0f172a;
	}

	.sort:focus-visible {
		outline: 2px solid #2563eb;
		outline-offset: 1px;
	}

	.sort-arrow {
		color: #94a3b8;
		font-size: 0.6875rem;
	}

	.sort-arrow.active {
		color: #1e3a5f;
	}

	.pages {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.375rem;
		margin-top: 1rem;
	}

	.page {
		min-width: 2.375rem;
		padding: 0.4375rem 0.625rem;
		border-radius: 8px;
		border: 1px solid #cbd5e1;
		background: white;
		color: #0f172a;
		font: inherit;
		font-size: 0.8125rem;
		font-weight: 600;
		cursor: pointer;
	}

	.page:hover:not(:disabled) {
		background: #f1f5f9;
	}

	.page:focus-visible {
		outline: 2px solid #2563eb;
		outline-offset: 1px;
	}

	.page.current {
		background: #1e3a5f;
		border-color: #1e3a5f;
		color: white;
	}

	.page:disabled:not(.current) {
		color: #94a3b8;
		background: #f8fafc;
		border-color: #e2e8f0;
		cursor: not-allowed;
	}

	tbody tr:last-child td {
		border-bottom: none;
	}

	.student-name {
		font-weight: 600;
	}

	.student-id {
		font-size: 0.8125rem;
		color: #64748b;
	}

	.status {
		display: inline-block;
		padding: 0.125rem 0.625rem;
		border-radius: 999px;
		font-size: 0.75rem;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
	}

	.status-present { background: #dcfce7; color: #15803d; }
	.status-late { background: #fef3c7; color: #b45309; }
	.status-excused { background: #ede9fe; color: #6d28d9; }
	.status-pending { background: #f1f5f9; color: #64748b; }
	.status-absent { background: #fee2e2; color: #b91c1c; }

	.mini {
		padding: 0.375rem 0.75rem;
		border-radius: 999px;
		border: 1px solid #cbd5e1;
		background: white;
		font: inherit;
		font-size: 0.8125rem;
		font-weight: 600;
		color: #0f172a;
	}

	.mini:disabled {
		color: #94a3b8;
		background: #f8fafc;
		border-color: #e2e8f0;
		cursor: not-allowed;
	}

	.sync {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		background: #fffbeb;
		border-color: #fcd34d;
		color: #92400e;
	}

	.sync strong {
		display: block;
	}

	.sync span {
		font-size: 0.875rem;
	}

	.excuse-all {
		display: flex;
		align-items: center;
		justify-content: space-between;
		flex-wrap: wrap;
		gap: 1rem;
	}

	.action-buttons {
		display: flex;
		flex-wrap: wrap;
		gap: 0.375rem;
	}

	.mini-danger {
		border-color: #fecaca;
		color: #b91c1c;
	}

	.form-label {
		font-size: 0.8125rem;
		font-weight: 600;
		letter-spacing: 0.02em;
		color: #334155;
	}

	.hint {
		margin: 0;
		font-size: 0.8125rem;
		color: #64748b;
	}

	.field-error {
		margin: 0;
		font-size: 0.8125rem;
		font-weight: 600;
		color: #b91c1c;
	}

	.modal-overlay {
		position: fixed;
		inset: 0;
		z-index: 100;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1rem;
		background: rgba(15, 23, 42, 0.5);
	}

	.modal {
		width: 100%;
		max-width: 28rem;
		background: white;
		border-radius: 12px;
		box-shadow: 0 20px 40px rgba(15, 23, 42, 0.25);
		padding: 1.5rem;
	}

	.modal-title {
		margin: 0 0 0.375rem;
		font-size: 1.25rem;
		font-weight: 700;
		color: #1e293b;
	}

	.modal-field {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
		margin-top: 1rem;
	}

	.modal-input {
		width: 100%;
		min-height: 3rem;
		padding: 0.625rem 0.75rem;
		border: 1px solid #cbd5e1;
		border-radius: 8px;
		font: inherit;
		font-size: 0.9375rem;
		color: #0f172a;
		background: white;
		resize: vertical;
	}

	.modal-input:focus-visible {
		outline: 2px solid #2563eb;
		outline-offset: 1px;
		border-color: #2563eb;
	}

	.modal-actions {
		display: flex;
		flex-wrap: wrap;
		justify-content: flex-end;
		gap: 0.75rem;
		margin-top: 1.25rem;
	}

	.footer {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
	}

	@media (max-width: 720px) {
		.code-card {
			padding: 1.25rem 0.75rem;
		}

		.code {
			letter-spacing: 0.06em;
		}

		.timer {
			flex: 1 1 10rem;
		}

		.tiles {
			grid-template-columns: 1fr;
		}

		.footer .btn {
			flex: 1 1 auto;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.btn,
		.mini {
			transition: none;
		}
	}
</style>
