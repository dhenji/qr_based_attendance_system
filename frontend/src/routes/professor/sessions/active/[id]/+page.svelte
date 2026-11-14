<script lang="ts">
	import SkeletonCards from '$lib/components/SkeletonCards.svelte';
	import SkeletonTable from '$lib/components/SkeletonTable.svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { browser } from '$app/environment';
	import AppIcon from '$lib/components/AppIcon.svelte';
import ConfirmExportDialog from '$lib/components/ConfirmExportDialog.svelte';
	import {
		closeSession,
		getActiveSession
	} from '$lib/features/session/service';
	import { invalidateAttendanceDirectory } from '$lib/features/attendance/service';
	import {
		excuseAllAbsent,
		EXCUSE_REASON_MIN_LENGTH,
		EXCUSE_REASON_SHORT_MESSAGE,
		quickExcuse,
		quickExcuseByIds
	} from '$lib/features/excuse/service';
	import { buildCsv } from '$lib/features/report/service';
	import { APIError, isMockMode } from '$lib/api/client';
	import { Routes, professorSessionCreate } from '$lib/shared/constants/routes';
	import { trapFocus } from '$lib/shared/actions/focusTrap';

	type LiveSession = Awaited<ReturnType<typeof getActiveSession>>;

	const POLL_MS = 3000;
	const TICK_MS = 1000;
	const EXPIRING_SOON_SECONDS = 5 * 60;
	const PAGE_SIZE = 10;

	// Excuse actions: bulk excuse-all-absent hits the live backend (it needs
	// only the session id). Per-row quick-excuse is mock-mode only: the
	// per-record routes need integer student ids
	// (POST /professor/sessions/{sid}/attendance/{stid}/excuse), but the live
	// feed's ActiveStudentItem rows carry student numbers only, and no other
	// professor-accessible endpoint returns integer ids (the attendance
	// ledger's `id` is the attendance record id, not the student id; the admin
	// roster is role-gated). quickExcuseByIds in features/excuse/service.ts is
	// already wired to the live route and takes over as soon as a row carries
	// an id — until then no per-row button is rendered in real mode.
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
	let exporting = $state(false);
	let pendingExport = $state<null | {
		run: () => void | Promise<void>;
		details?: { label: string; value: string }[];
		title?: string;
		message?: string;
		confirmLabel?: string;
		busyLabel?: string;
	}>(null);

	let qrDataUrl = $state<string | null>(null);
	let qrError = $state<string | null>(null);
	let codeCopied = $state(false);

	// Server-first export (POST /professor/reports/export) scoped to the
	// session's course was abandoned on purpose: the server leg always
	// exports a whole course (no session filter exists), so the
	// session-<id>-attendance.csv filename disagreed with the contents — and
	// when the course lookup missed (stale profile cache), it degraded to
	// all courses. Feed rows here carry the full session record, so building
	// locally is the true per-session file.
	const saveExport = (text: string, filename: string) => {
		const blob = new Blob([text], { type: 'text/csv;charset=utf-8' });
		const url = URL.createObjectURL(blob);
		const link = document.createElement('a');
		link.href = url;
		link.download = filename;
		document.body.appendChild(link);
		link.click();
		link.remove();
		// Revoke late: immediate revoke can abort large downloads on Safari.
		setTimeout(() => URL.revokeObjectURL(url), 60_000);
	};
	const exportCurrent = () => {
		const current = session;
		if (!current || exporting) return;
		exporting = true;
		try {
			saveExport(
				buildCsv(
					['student_number', 'name', 'section', 'status', 'scanned_at', 'excuse_reason'],
					current.students.map((s) => [
						s.studentNumber,
						s.name,
						s.section ?? '',
						s.status,
						s.scannedAt ?? '',
						s.excuseReason ?? ''
					])
				),
				`session-${current.id}-attendance.csv`
			);
		} finally {
			exporting = false;
		}
	};

	// Excuse-action modal state. The modal opens in mock mode only (see note
	// above); bulk excuse-all-absent is live.
	let excuseTarget = $state<FeedRow | null>(null);
	let excuseReason = $state('');
	let excuseBusy = $state(false);
	let excuseError = $state<string | null>(null);
	let bulkOpen = $state(false);
	let bulkReason = $state('');
	let bulkBusy = $state(false);
	let bulkError = $state<string | null>(null);
	let bulkDone = $state<string | null>(null);

	const isExcusable = (status: FeedRow['status']) =>
		status === 'absent' || status === 'late' || status === 'rejected';

	const openExcuse = (row: FeedRow) => {
		excuseTarget = row;
		excuseReason = '';
		excuseError = null;
	};

	const submitExcuse = async () => {
		if (!excuseTarget || !session || excuseBusy) return;
		const reason = excuseReason.trim();
		if (reason.length < EXCUSE_REASON_MIN_LENGTH) {
			excuseError = EXCUSE_REASON_SHORT_MESSAGE;
			return;
		}
		excuseBusy = true;
		excuseError = null;
		try {
			if (isMockMode()) {
				await quickExcuse({
					studentNumber: excuseTarget.studentNumber,
					studentName: excuseTarget.name,
					section: excuseTarget.section ?? undefined,
					courseCode: session.offeringCode,
					courseName: session.offeringName,
					sessionId: session.id,
					sessionCode: session.sessionCode,
					originalStatus: excuseTarget.status as 'absent' | 'late' | 'rejected',
					reason
				});
			} else {
				await quickExcuseByIds(
					session.id,
					excuseTarget.studentId,
					reason,
					[],
					{
						studentNumber: excuseTarget.studentNumber,
						studentName: excuseTarget.name,
						section: excuseTarget.section ?? undefined,
					}
				);
			}
			excuseTarget = null;
			reloadToken += 1;
		} catch (error: unknown) {
			excuseError = error instanceof Error && error.message ? error.message : 'Excuse failed.';
		} finally {
			excuseBusy = false;
		}
	};

	const submitBulk = async () => {
		if (!session || bulkBusy) return;
		const reason = bulkReason.trim();
		if (reason.length < EXCUSE_REASON_MIN_LENGTH) {
			bulkError = EXCUSE_REASON_SHORT_MESSAGE;
			return;
		}
		bulkBusy = true;
		bulkError = null;
		try {
			const result = await excuseAllAbsent(session.id, reason);
			bulkDone =
				result.excusedCount === 0
					? 'No absent records to excuse — the session is already clear.'
					: `${result.excusedCount} absent record${result.excusedCount === 1 ? '' : 's'} excused.`;
			bulkOpen = false;
			bulkReason = '';
			reloadToken += 1;
		} catch (error: unknown) {
			bulkError = error instanceof Error && error.message ? error.message : 'Bulk excuse failed.';
		} finally {
			bulkBusy = false;
		}
	};

	// Fingerprint of a live snapshot for the no-op poll guard: if this is
	// unchanged between two polls, the session state (and table) need not be
	// replaced, avoiding a full re-render on idle 3s polls.
	const sessionFingerprint = (value: LiveSession): string =>
		`${value.status}|${value.enrolledCount}|${value.remaining}|${value.pendingSyncCount}|${value.scanWindowRemaining}|${value.expiresAt ?? ''}|` +
		value.students
			.map((row) => `${row.studentNumber}:${row.status}:${row.scannedAt ?? ''}:${row.excuseReason ?? ''}`)
			.join(',');

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
		const controller = new AbortController();
		let poll: number | undefined;
		let tick: number | undefined;
		currentPage = 1;

		const load = async (initial: boolean) => {
			// Skip background refreshes while the tab is hidden; the
			// visibilitychange handler below refreshes on return.
			if (!initial && document.visibilityState !== 'visible') return;
			if (initial) {
				isLoading = true;
				loadError = null;
			}

			try {
				const requestStartedAt = Date.now();
				const live = await getActiveSession(id, controller.signal);
				if (cancelled || controller.signal.aborted) return;

				// Equality guard: skip state replacement (and the resulting full
				// table re-render) when the snapshot is byte-equivalent to the
				// one we already hold. Common between scans on a 3s poll.
				if (session !== null && sessionFingerprint(session) === sessionFingerprint(live)) {
					now = Date.now();
					loadError = null;
					refreshError = null;
					return;
				}

				session = live;
				// Anchor the countdown to when the server snapshot was requested,
				// not when the promise resolved. Otherwise every poll adds fetch
				// latency back into the displayed timer. Seeding now here also
				// prevents the first paint from calculating against its zero value.
				const newExpiry =
					requestStartedAt + live.scanWindowRemaining * 1000;
				// Only re-anchor the countdown when it has drifted more than 2s
				// from the server's value. Re-anchoring on every poll (each with
				// its own request latency and integer-second rounding) made the
				// displayed timer jump backwards/forwards a second at a time.
				const currentExpiry =
					scanSnapshotAt === null || scanSnapshotRemaining === null
						? null
						: scanSnapshotAt + scanSnapshotRemaining * 1000;
				if (currentExpiry === null || Math.abs(newExpiry - currentExpiry) > 2000) {
					scanSnapshotAt = requestStartedAt;
					scanSnapshotRemaining = live.scanWindowRemaining;
				}
				now = Date.now();
				loadError = null;
				refreshError = null;
			} catch (error) {
				if (cancelled || controller.signal.aborted) return;
				if (error instanceof APIError && error.code === 'request_cancelled') return;
				if (session === null) loadError = 'The live session could not be loaded.';
				else refreshError = 'The live feed failed to refresh. Showing the last update.';
			} finally {
				if (!cancelled && initial) isLoading = false;
			}
		};

		void load(true);
		poll = window.setInterval(() => void load(false), POLL_MS);
		tick = window.setInterval(() => {
			// Frozen while hidden; resumes on visibilitychange refresh.
			// Stops ticking when the session is closed or not yet started.
			if (!cancelled && document.visibilityState === 'visible' && !isClosed) now = Date.now();
		}, TICK_MS);
		const handleVisible = () => {
			if (document.visibilityState === 'visible') void load(false);
		};
		document.addEventListener('visibilitychange', handleVisible);

		return () => {
			cancelled = true;
			controller.abort();
			window.clearInterval(poll);
			window.clearInterval(tick);
			document.removeEventListener('visibilitychange', handleVisible);
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
		// Prefer the server's absolute expiry when available — it is not
		// affected by request latency or client/server clock skew, so the
		// countdown ticks smoothly without the per-poll re-anchoring jumps.
		const expiryMs =
			session?.expiresAt != null
				? new Date(session.expiresAt).getTime()
				: scanExpiresAt;
		if (expiryMs === null || Number.isNaN(expiryMs)) return null;
		return Math.max(0, Math.floor((expiryMs - now) / 1000));
	});

	// The class end is the offering's plan (D93), so the countdown reads the
	// real end of the scheduled class rather than "when the professor clicked".
	const classEndsAt = $derived(session ? new Date(session.scheduledEndTime).getTime() : null);
	const classRemainingSeconds = $derived.by(() => {
		if (classEndsAt === null) return null;
		if (isClosed || isScheduled) return 0;
		return Math.max(0, Math.floor((classEndsAt - now) / 1000));
	});
	// A session opened after its class ended still runs, so the tile says so
	// rather than showing a zero countdown.
	const classEnded = $derived(
		classRemainingSeconds !== null && classRemainingSeconds <= 0
	);

	// Scan window and class end are the same instant in override mode (both =
	// start + duration). Detect that so the UI can collapse the duplicate
	// timer instead of showing two identical countdowns.
	const scanAndClassCoincide = $derived(
		scanExpiresAt !== null &&
			classEndsAt !== null &&
			Math.abs(scanExpiresAt - classEndsAt) <= 60_000
	);
	// Overtime: scanning stays open past the scheduled class end.
	const scanExtendsBeyondClass = $derived(
		scanExpiresAt !== null &&
			classEndsAt !== null &&
			scanExpiresAt > classEndsAt + 60_000
	);

	const isClosed = $derived(session?.status === 'closed');
	const isScheduled = $derived(session?.status === 'scheduled');
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
		// Precompute the per-row sort keys once instead of reparsing dates and
		// re-running localeCompare inside every comparator invocation.
		const rows = session.students.map((row) => ({
			row,
			timeMs: row.scannedAt ? new Date(row.scannedAt).getTime() : Number.NaN,
		}));

		const byName = (a: FeedRow, b: FeedRow): number =>
			a.name.localeCompare(b.name) || a.studentNumber.localeCompare(b.studentNumber);

		rows.sort((a, b) => {
			switch (sortKey) {
				case 'time': {
					const aMissing = Number.isNaN(a.timeMs) ? 1 : 0;
					const bMissing = Number.isNaN(b.timeMs) ? 1 : 0;
					if (aMissing !== bMissing) return aMissing - bMissing;
					if (aMissing === 1) return byName(a.row, b.row) * direction;
					return (
						(a.timeMs - b.timeMs ||
							a.row.studentNumber.localeCompare(b.row.studentNumber)) * direction
					);
				}
				case 'name':
					return byName(a.row, b.row) * direction;
				case 'status':
					return (
						(STATUS_SORT_ORDER[a.row.status] - STATUS_SORT_ORDER[b.row.status] ||
							a.timeMs - b.timeMs ||
							byName(a.row, b.row)) * direction
					);
			}
			return 0;
		});

		return rows.map((entry) => entry.row);
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

	$effect(() => {
		const code = session?.sessionCode;
		if (!browser || !code) {
			qrDataUrl = null;
			qrError = null;
			return;
		}
		let cancelled = false;
		qrDataUrl = null;
		qrError = null;
		void (async () => {
			try {
				const mod = (await import('qrcode')) as { default?: { toDataURL: (text: string, opts?: unknown) => Promise<string> }; toDataURL?: (text: string, opts?: unknown) => Promise<string> };
				const QRCode: any = mod.default ?? mod;
				const url = `${window.location.origin}/student/scan?code=${encodeURIComponent(code)}`;
				const dataUrl = await QRCode.toDataURL(url, { margin: 2, width: 280 });
				if (!cancelled) qrDataUrl = dataUrl;
			} catch {
				if (!cancelled) qrError = 'Could not generate QR code.';
			}
		})();
		return () => {
			cancelled = true;
		};
	});

	const copyCode = async () => {
		const code = session?.sessionCode;
		if (!code) return;
		try {
			await navigator.clipboard.writeText(code);
			codeCopied = true;
			setTimeout(() => {
				codeCopied = false;
			}, 2000);
		} catch {
			// swallow
		}
	};

	const downloadQr = () => {
		if (!qrDataUrl || !session) return;
		try {
			const link = document.createElement('a');
			link.href = qrDataUrl;
			link.download = `session-${session.id}-qr.png`;
			document.body.appendChild(link);
			link.click();
			link.remove();
		} catch {
			// swallow
		}
	};

	const handleClose = async () => {
		const id = sessionId;
		if (id === null || closing || isClosed) return;

		closing = true;
		refreshError = null;
		try {
			const requestStartedAt = Date.now();
			await closeSession(id);
			invalidateAttendanceDirectory();
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
				<h1>{session.status === 'scheduled' ? 'Scheduled' : session.status === 'closed' ? 'Closed' : 'Active'}: {session.offeringCode} — {session.offeringName}</h1>
			</div>
			<button
				class="btn btn-danger"
				type="button"
				aria-busy={closing}
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
	{:else if isLoading || !session || scanRemainingSeconds === null}
		<SkeletonCards count={3} label="Loading live session…" />
		<SkeletonTable rows={5} cols={5} />
	{:else}
		{#if refreshError}
			<p class="refresh-error" role="status">{refreshError}</p>
		{/if}
		{#if closedNotice}
			<p class="notice" role="status">Session closed. New scans are blocked.</p>
		{/if}

		<section class="card code-card" aria-label="Projector session code">
			<div class="code-main">
				<span class="code-label">Session Code · Show on projector</span>
				<span class="code">{session.sessionCode}</span>
				<div class="timers">
					<div class="timer" class:urgent={expiringSoon || scanExpired} aria-live="polite">
						<span class="timer-label">Scan window closes in</span>
						<span class="timer-value">{formatCountdown(scanRemainingSeconds)}</span>
						{#if scanExpiresAt !== null && scanSnapshotRemaining !== null}
							<div class="scan-progress" aria-hidden="true">
								<div
									class="scan-progress-bar"
									style="width: {Math.min(100, Math.max(0, ((scanSnapshotRemaining * 1000 - (scanExpiresAt - now)) / (scanSnapshotRemaining * 1000)) * 100))}%;"
								></div>
							</div>
						{/if}
						{#if scanExtendsBeyondClass}
							<span class="timer-sub">extended past class end</span>
						{:else if !scanAndClassCoincide && classEndsAt !== null && scanExpiresAt !== null && scanExpiresAt < classEndsAt}
							<span class="timer-sub">closes before class ends</span>
						{/if}
					</div>
					{#if isScheduled}
						<div class="timer" class:urgent={classEnded}>
							<span class="timer-label">Class starts in</span>
							<span class="timer-value">{formatCountdown(Math.max(0, Math.floor((new Date(session.scheduledStartTime).getTime() - now) / 1000)))}</span>
							<span class="timer-sub">at {formatClock(session.scheduledStartTime)}</span>
						</div>
					{:else if isClosed}
						<div class="timer" class:urgent={classEnded}>
							<span class="timer-label">
								{classEndsAt !== null && classEndsAt <= now ? 'Class ended' : 'Closed early'}
							</span>
							<span class="timer-value">{formatClock(session.scheduledEndTime)}</span>
						</div>
					{:else if scanAndClassCoincide}
						<div class="timer">
							<span class="timer-label">Class ends</span>
							<span class="timer-sub">when scanning closes</span>
						</div>
					{:else}
						<div class="timer" class:urgent={classEnded}>
							<span class="timer-label">{classEnded ? 'Class ended' : 'Class ends at'}</span>
							<span class="timer-value">{formatClock(session.scheduledEndTime)}</span>
						</div>
					{/if}
				</div>
			</div>
			<div class="qr-side">
				<span class="code-label">Scan to Join</span>
				{#if qrError}
					<p class="error">{qrError}</p>
				{:else if qrDataUrl}
					<img
						src={qrDataUrl}
						alt="QR code to join this session"
						width="180"
						height="180"
						class="qr-image"
					/>
				{:else}
					<div class="qr-placeholder">Generating…</div>
				{/if}
				<div class="qr-actions">
					<button class="btn btn-secondary" type="button" onclick={() => void copyCode()}>
						{codeCopied ? 'Copied' : 'Copy Session Code'}
					</button>
					<button class="btn btn-secondary" type="button" onclick={downloadQr} disabled={!qrDataUrl}>
						Export QR Code
					</button>
				</div>
			</div>
		</section>

		<details class="card details-card" aria-label="General session information">
			<summary class="details-summary">
				<h2 class="section-title">General session information</h2>
				<span class="details-meta">
					<span class="details-hint">Click to expand</span>
					<span class="details-arrow" aria-hidden="true">▸</span>
				</span>
			</summary>
			<dl class="detail-grid">
				<div>
					<dt>Course</dt>
					<dd>{session.offeringCode} — {session.offeringName}</dd>
				</div>
				<div>
					<dt>Program</dt>
					<dd>{session.offeringProgram ?? '—'}</dd>
				</div>
				<div>
					<dt>Year level</dt>
					<dd>{session.offeringYearLevel ?? '—'}</dd>
				</div>
				<div>
					<dt>Academic year</dt>
					<dd>{session.academicYear ?? '—'}</dd>
				</div>
				<div>
					<dt>Semester</dt>
					<dd>{session.semester ?? '—'}</dd>
				</div>
				<div>
					<dt>Session type</dt>
					<dd>{session.sessionType === 'lab' ? 'Laboratory' : 'Lecture'}</dd>
				</div>
				<div>
					<dt>Status</dt>
					<dd class="status status-{session.status}">{session.status}</dd>
				</div>
				<div>
					<dt>Duration</dt>
					<dd>{session.durationMinutes ?? 0} min</dd>
				</div>
				<div>
					<dt>Attendance attempt limit</dt>
					<dd>{session.attendanceAttemptLimit ? session.attendanceAttemptLimit : 'Unlimited'}</dd>
				</div>
				<div>
					<dt>Present window</dt>
					<dd>{session.presentWindowMinutes ?? 0} min</dd>
				</div>
				<div>
					<dt>Late window</dt>
					<dd>{session.lateWindowMinutes ?? 0} min</dd>
				</div>
			</dl>
		</details>

		<details class="card details-card" aria-label="Schedule and time information">
			<summary class="details-summary">
				<h2 class="section-title">Schedule and time</h2>
				<span class="details-meta">
					<span class="details-hint">Click to expand</span>
					<span class="details-arrow" aria-hidden="true">▸</span>
				</span>
			</summary>
			<dl class="detail-grid">
				<div>
					<dt>Scheduled start</dt>
					<dd>{formatDateTime(new Date(session.scheduledStartTime).getTime())}</dd>
				</div>
				<div>
					<dt>Scheduled end</dt>
					<dd>{formatDateTime(new Date(session.scheduledEndTime).getTime())}</dd>
				</div>
				<div>
					<dt>Actual opened at</dt>
					<dd>{session.actualStartTime ? formatDateTime(new Date(session.actualStartTime).getTime()) : '—'}</dd>
				</div>
				{#if session.scheduleOverridden}
					<div>
						<dt>Schedule override</dt>
						<dd>
							Yes — {session.originalScheduledStartTime ? formatDateTime(new Date(session.originalScheduledStartTime).getTime()) : '—'} → {formatDateTime(new Date(session.scheduledStartTime).getTime())}
						</dd>
					</div>
					<div>
						<dt>Override reason</dt>
						<dd>{session.overrideReason && session.overrideReason.trim() !== '' ? session.overrideReason : 'not provided'}</dd>
					</div>
				{:else}
					<div>
						<dt>Schedule override</dt>
						<dd>No</dd>
					</div>
				{/if}
				<div>
					<dt>Scan window expires</dt>
					<dd>
						{session.expiresAt ? formatDateTime(new Date(session.expiresAt).getTime()) : '—'}
						{#if session.expiresAt}
							<span class="detail-note">
								{#if new Date(session.expiresAt).getTime() > new Date(session.scheduledEndTime).getTime() + 60000}
									(extended past class end)
								{:else if new Date(session.expiresAt).getTime() < new Date(session.scheduledEndTime).getTime() - 60000}
									(closes before class ends)
								{:else}
									(matches class end)
								{/if}
							</span>
						{/if}
					</dd>
				</div>
				{#if !isClosed}
					<div>
						<dt>Remaining to scheduled end</dt>
						<dd>{classRemainingSeconds !== null ? formatCountdown(classRemainingSeconds) : '—'}</dd>
					</div>
				{/if}
				{#if isClosed}
					<div>
						<dt>Actual end</dt>
						<dd>{session.expiresAt ? formatDateTime(new Date(session.expiresAt).getTime()) : '—'}</dd>
					</div>
					<div>
						<dt>Actual duration</dt>
						<dd>
							{session.actualStartTime && session.expiresAt
								? formatCountdown(Math.max(0, Math.floor((new Date(session.expiresAt).getTime() - new Date(session.actualStartTime).getTime()) / 1000)))
								: '—'}
						</dd>
					</div>
				{/if}
			</dl>
		</details>

		<details class="card details-card" aria-label="Session location">
			<summary class="details-summary">
				<h2 class="section-title">Location</h2>
				<span class="details-meta">
					<span class="details-hint">Click to expand</span>
					<span class="details-arrow" aria-hidden="true">▸</span>
				</span>
			</summary>
			<dl class="detail-grid">
				<div>
					<dt>Classroom</dt>
					<dd>{session.classroomName ?? '—'}</dd>
				</div>
				{#if session.classroomName}
					<div>
						<dt>Latitude</dt>
						<dd>{session.classroomLat ?? '—'}</dd>
					</div>
					<div>
						<dt>Longitude</dt>
						<dd>{session.classroomLng ?? '—'}</dd>
					</div>
				{/if}
				<div>
					<dt>Geofence radius</dt>
					<dd>{session.classroomRadiusMeters ?? 0} m</dd>
				</div>
				<div>
					<dt>Remote / online</dt>
					<dd>{session.isRemote ? 'Yes' : 'No'}</dd>
				</div>
				<div>
					<dt>Geofence enforced</dt>
					<dd>{session.geofenceEnabled ? 'Yes' : 'No'}</dd>
				</div>
			</dl>
		</details>

		<details class="card details-card" aria-label="Attendance overview">
			<summary class="details-summary">
				<h2 class="section-title">Attendance overview</h2>
				<span class="details-meta">
					<span class="details-hint">Click to expand</span>
					<span class="details-arrow" aria-hidden="true">▸</span>
				</span>
			</summary>
			<dl class="detail-grid">
				<div>
					<dt>Total enrolled</dt>
					<dd>{session.enrolledCount}</dd>
				</div>
				<div>
					<dt>Scanned</dt>
					<dd>{scanned}</dd>
				</div>
				<div>
					<dt>Remaining</dt>
					<dd>{session.remaining}</dd>
				</div>
				<div>
					<dt>Present</dt>
					<dd>{session.counts.present}</dd>
				</div>
				<div>
					<dt>Late</dt>
					<dd>{session.counts.late}</dd>
				</div>
				<div>
					<dt>Excused</dt>
					<dd>{session.counts.excused}</dd>
				</div>
				<div>
					<dt>Pending</dt>
					<dd>{session.counts.pending}</dd>
				</div>
				<div>
					<dt>Absent</dt>
					<dd>{session.counts.absent}</dd>
				</div>
				<div>
					<dt>Rejected</dt>
					<dd>{session.counts.rejected ?? 0}</dd>
				</div>
				<div>
					<dt>Compliance rate</dt>
					<dd>{((session.complianceRate ?? 0) * 100).toFixed(2)}%</dd>
				</div>
				<div>
					<dt>Participation rate</dt>
					<dd>{((session.participationRate ?? 0) * 100).toFixed(2)}%</dd>
				</div>
			</dl>
		</details>

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
						<th scope="col"><span class="sr-only">Actions</span></th>
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
							<td class="row-action">
								{#if isExcusable(student.status)}
									{#if isMockMode()}
										<button class="link" type="button" onclick={() => openExcuse(student)}>
											Excuse
										</button>
									{/if}
								{:else if student.status === 'excused'}
									<span class="muted">Excused</span>
								{/if}
							</td>
						</tr>
					{:else}
						<tr>
							<td colspan="4" class="muted">No students are enrolled in this session yet.</td>
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
				{#if bulkDone}
					<p class="muted" role="status">{bulkDone}</p>
				{:else}
					<p class="muted">
						Excuse every absent record in this session at once (idempotent —
						re-running excuses nothing new).
						{#if isMockMode()}
							Per-row excuses use the mock preview; the review queue handles real per-student cases.
						{:else}
							Per-student excuses are handled in the excuse review queue.
						{/if}
					</p>
				{/if}
			</div>
			<button class="btn btn-secondary" type="button" onclick={() => { bulkOpen = true; bulkError = null; }}>
				Excuse all absent
			</button>
		</section>

		<div class="footer">
			<button
				class="btn btn-secondary"
				type="button"
				disabled={exporting || session === null}
				title="Download this session's attendance as CSV (server rows when reachable)"
				onclick={() => (pendingExport = { run: exportCurrent, details: [{ label: 'Dataset', value: 'Session attendance' }, { label: 'Format', value: 'CSV' }] })}
			>
				{exporting ? 'Exporting…' : 'Export Current'}
			</button>
			<button class="btn btn-secondary" type="button" onclick={() => (pendingExport = { run: () => window.print(), title: 'Confirm Print', message: 'Are you sure you want to print this data? Your browser’s print dialog will open after you confirm.', confirmLabel: 'Confirm Print', details: [{ label: 'Format', value: 'Print' }] })}>
				Print
			</button>
			<button class="btn btn-secondary" type="button" onclick={() => goto(Routes.PROFESSOR_SESSIONS_HISTORY)}>
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

		{#if excuseTarget}
			<div class="overlay" role="presentation">
				<div
					class="modal"
					role="dialog"
					aria-modal="true"
					aria-labelledby="excuse-title"
					tabindex="-1"
					use:trapFocus={{ onEscape: () => (excuseBusy ? undefined : (excuseTarget = null)) }}
				>
					<h3 class="modal-title" id="excuse-title">Excuse {excuseTarget.name}</h3>
					<p class="modal-desc">
						{excuseTarget.studentNumber} · Section {excuseTarget.section ?? '—'} ·
						currently {excuseTarget.status}
					</p>
					{#if excuseError}
						<p class="error" role="alert">{excuseError}</p>
					{/if}
					<label class="field">
						Reason (min {EXCUSE_REASON_MIN_LENGTH} characters)
						<textarea class="form-input" rows="3" bind:value={excuseReason}></textarea>
					</label>
					<div class="modal-actions">
						<button class="btn btn-ghost" type="button" onclick={() => (excuseTarget = null)}>
							Cancel
						</button>
						<button class="btn btn-primary" type="button" aria-busy={excuseBusy} disabled={excuseBusy} onclick={() => void submitExcuse()}>
							{excuseBusy ? 'Saving…' : 'Excuse'}
						</button>
					</div>
				</div>
			</div>
		{/if}

		{#if bulkOpen}
			<div class="overlay" role="presentation">
				<div
					class="modal"
					role="dialog"
					aria-modal="true"
					aria-labelledby="bulk-title"
					tabindex="-1"
					use:trapFocus={{ onEscape: () => (bulkBusy ? undefined : (bulkOpen = false)) }}
				>
					<h3 class="modal-title" id="bulk-title">Excuse all absent</h3>
					<p class="modal-desc">
						Every record currently marked absent in this session will be excused.
						Already-excused rows are untouched; running this twice excuses nothing new.
					</p>
					{#if bulkError}
						<p class="error" role="alert">{bulkError}</p>
					{/if}
					<label class="field">
						Reason (min {EXCUSE_REASON_MIN_LENGTH} characters)
						<textarea class="form-input" rows="3" bind:value={bulkReason}></textarea>
					</label>
					<div class="modal-actions">
						<button class="btn btn-ghost" type="button" onclick={() => (bulkOpen = false)}>
							Cancel
						</button>
						<button class="btn btn-primary" type="button" aria-busy={bulkBusy} disabled={bulkBusy} onclick={() => void submitBulk()}>
							{bulkBusy ? 'Saving…' : 'Excuse all absent'}
						</button>
					</div>
				</div>
			</div>
		{/if}
	{/if}
	{#if pendingExport}
		<ConfirmExportDialog
			title={pendingExport.title}
			message={pendingExport.message}
			confirmLabel={pendingExport.confirmLabel}
			busyLabel={pendingExport.busyLabel}
			details={pendingExport.details}
			onconfirm={pendingExport.run}
			onclose={() => (pendingExport = null)}
		/>
	{/if}
</div>

<style>
	.live {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
		max-width: 1000px;
		margin: 0 auto;
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
		color: var(--text);
	}

	.muted {
		margin: 0;
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	.card {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 12px;
		padding: 1.5rem;
		box-shadow: var(--shadow-sm);
	}

	.section-title {
		margin: 0;
		font-size: 1rem;
		font-weight: 700;
		color: var(--text);
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
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.btn-ghost {
		background: var(--bg-card);
		border-color: var(--border-strong);
		color: var(--text-strong);
	}

	.btn-primary {
		background: var(--brand);
		border-color: var(--brand);
		color: var(--on-brand);
	}

	.btn-secondary {
		background: var(--bg-card);
		border-color: var(--border-strong);
		color: var(--text-strong);
	}

	.btn-danger {
		background: var(--danger-strong);
		border-color: var(--danger-strong);
		color: var(--on-brand);
	}

	.btn:disabled {
		background: var(--bg-page);
		border-color: var(--border);
		color: var(--text-muted);
		cursor: not-allowed;
		box-shadow: none;
	}

	.error {
		margin: 0 0 1rem;
		color: var(--danger-strong);
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
		background: var(--danger-bg);
		border: 1px solid var(--danger-bg);
		color: var(--danger-strong);
	}

	.notice {
		background: var(--success-bg);
		border: 1px solid var(--success-bg);
		color: var(--success);
	}

	.code-card {
		display: flex;
		flex-direction: row;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 1.5rem;
		background: linear-gradient(135deg, var(--success-bg), var(--success-bg));
		border: 2px solid var(--success);
		text-align: center;
		container-type: inline-size;
	}

	.code-main {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 1rem;
		flex: 1 1 20rem;
	}

	.qr-side {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.75rem;
		flex: 0 0 auto;
	}

	.code-label {
		font-size: 0.75rem;
		font-weight: 700;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		color: var(--success);
	}

	.code {
		font-family: 'JetBrains Mono', monospace;
		font-size: min(3.5rem, 16cqw);
		font-weight: 700;
		letter-spacing: 0.12em;
		line-height: 1;
		color: var(--success);
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
		align-items: center;
		justify-content: center;
		text-align: center;
		gap: 0.125rem;
		min-width: 11rem;
		padding: 0.75rem 1rem;
		border-radius: 10px;
		background: color-mix(in srgb, var(--bg-card) 80%, transparent);
		border: 1px solid var(--success-bg);
	}

	.timer.urgent {
		border-color: var(--danger);
	}

	.timer-label {
		font-size: 0.75rem;
		font-weight: 700;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--success);
	}

	.timer.urgent .timer-label {
		color: var(--danger-strong);
	}

	.timer-value {
		font-variant-numeric: tabular-nums;
		font-size: 1.375rem;
		font-weight: 800;
		color: var(--success);
	}

	.scan-progress {
		width: 100%;
		height: 0.375rem;
		border-radius: 999px;
		background: var(--bg-page);
		border: 1px solid var(--border);
		overflow: hidden;
		margin-top: 0.25rem;
	}

	.scan-progress-bar {
		height: 100%;
		background: var(--success);
		border-radius: 999px;
		transition: width 0.3s linear;
	}

	.timer.urgent .scan-progress-bar {
		background: var(--danger);
	}

	.timer-sub {
		font-size: 0.8125rem;
		color: var(--text-muted);
	}

	.details-card {
		margin-bottom: 0.5rem;
	}

	.details-card > summary {
		list-style: none;
		cursor: pointer;
		user-select: none;
		border-radius: 8px;
		padding: 0.25rem 0.5rem;
		margin: -0.25rem -0.5rem;
		transition: background-color 0.15s ease;
	}

	.details-card > summary:hover {
		background: var(--bg-hover);
	}

	.details-card > summary:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.details-hint,
	.details-arrow {
		transition: color 0.15s ease;
	}

	.details-card > summary:hover .details-hint,
	.details-card > summary:hover .details-arrow {
		color: var(--text-strong);
	}

	.details-card > summary::-webkit-details-marker {
		display: none;
	}

	.details-summary {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
	}

	.details-summary h2 {
		margin: 0;
	}

	.details-meta {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		flex-shrink: 0;
	}

	.details-hint {
		font-size: 0.75rem;
		color: var(--text-muted);
		white-space: nowrap;
	}

	.details-arrow {
		color: var(--text-muted);
		transition: transform 0.15s ease;
	}

	.details-card[open] .details-arrow {
		transform: rotate(90deg);
	}

	.detail-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.75rem 1.5rem;
		margin: 1rem 0 0;
	}

	.detail-grid div {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.detail-grid dt {
		font-size: 0.75rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--text-muted);
	}

	.detail-grid dd {
		margin: 0;
		color: var(--text-strong);
		font-size: 0.9375rem;
		word-break: break-word;
	}

	.detail-note {
		margin-left: 0.375rem;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--text-muted);
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
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 12px;
	}

	.tile-value {
		font-size: 2rem;
		font-weight: 800;
		font-variant-numeric: tabular-nums;
		color: var(--brand);
	}

	.tile-label {
		font-size: 0.8125rem;
		font-weight: 600;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		color: var(--text-muted);
	}

	.legend {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem 1.5rem;
		list-style: none;
		margin: 1rem 0 0;
		padding: 0;
		color: var(--text-secondary);
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

	.dot-present { background: var(--success); }
	.dot-late { background: #f59e0b; }
	.dot-excused { background: #8b5cf6; }
	.dot-pending { background: var(--text-muted); }
	.dot-absent { background: var(--danger); }

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
		border: 1px solid var(--border);
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
		border-bottom: 1px solid var(--divider);
		vertical-align: top;
		color: var(--text-strong);
	}

	thead th {
		position: sticky;
		top: 0;
		z-index: 1;
		background: var(--bg-page);
		font-size: 0.75rem;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--text-muted);
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
		background: var(--bg-hover);
		color: var(--text-strong);
	}

	.sort:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
	}

	.sort-arrow {
		color: var(--text-muted);
		font-size: 0.6875rem;
	}

	.sort-arrow.active {
		color: var(--brand);
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
		border: 1px solid var(--border-strong);
		background: var(--bg-card);
		color: var(--text-strong);
		font: inherit;
		font-size: 0.8125rem;
		font-weight: 600;
		cursor: pointer;
	}

	.page:hover:not(:disabled) {
		background: var(--bg-hover);
	}

	.page:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
	}

	.page.current {
		background: var(--brand);
		border-color: var(--brand);
		color: var(--on-brand);
	}

	.page:disabled:not(.current) {
		color: var(--text-muted);
		background: var(--bg-page);
		border-color: var(--border);
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
		color: var(--text-muted);
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

	.status-present { background: var(--success-bg); color: var(--success); }
	.status-late { background: var(--warning-bg); color: var(--warning-text); }
	.status-excused { background: var(--info-bg); color: var(--info-text); }
	.status-pending { background: var(--bg-muted); color: var(--text-muted); }
	.status-absent { background: var(--danger-bg); color: var(--danger-strong); }

	.type-badge {
		display: inline-block;
		padding: 0.125rem 0.5rem;
		border-radius: 999px;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--success);
		background: var(--success-bg);
		white-space: nowrap;
	}

	.type-badge.is-lab {
		color: var(--warning-text);
		background: var(--warning-bg);
	}

	.mini {
		padding: 0.375rem 0.75rem;
		border-radius: 999px;
		border: 1px solid var(--border-strong);
		background: var(--bg-card);
		font: inherit;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-strong);
	}

	.mini:disabled {
		color: var(--text-muted);
		background: var(--bg-page);
		border-color: var(--border);
		cursor: not-allowed;
	}

	.sync {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		background: var(--warning-bg);
		border-color: var(--warning-text);
		color: var(--warning-text);
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
		border-color: var(--danger-bg);
		color: var(--danger-strong);
	}

	.form-label {
		font-size: 0.8125rem;
		font-weight: 600;
		letter-spacing: 0.02em;
		color: var(--text-secondary);
	}

	.hint {
		margin: 0;
		font-size: 0.8125rem;
		color: var(--text-muted);
	}

	.field-error {
		margin: 0;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--danger-strong);
	}

	.modal-overlay {
		position: fixed;
		inset: 0;
		z-index: 100;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1rem;
		background: var(--overlay);
	}

	.modal {
		width: 100%;
		max-width: 28rem;
		background: var(--bg-card);
		border-radius: 12px;
		box-shadow: var(--shadow-lg);
		padding: 1.5rem;
	}

	.modal-title {
		margin: 0 0 0.375rem;
		font-size: 1.25rem;
		font-weight: 700;
		color: var(--text);
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
		border: 1px solid var(--border-strong);
		border-radius: 8px;
		font: inherit;
		font-size: 0.9375rem;
		color: var(--text-strong);
		background: var(--bg-card);
		resize: vertical;
	}

	.modal-input:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
		border-color: var(--accent);
	}

	.modal-actions {
		display: flex;
		flex-wrap: wrap;
		justify-content: flex-end;
		gap: 0.75rem;
		margin-top: 1.25rem;
	}

	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
	}

	.row-action {
		white-space: nowrap;
	}

	.link {
		background: none;
		border: none;
		padding: 0;
		color: var(--accent);
		font-size: 0.8125rem;
		font-weight: 600;
		cursor: pointer;
	}

	.link:hover {
		text-decoration: underline;
	}

	.overlay {
		position: fixed;
		inset: 0;
		z-index: 100;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1rem;
		background: var(--overlay);
	}

	.modal-desc {
		margin: 0 0 1rem;
		font-size: 0.9375rem;
		color: var(--text-secondary);
	}

	.field {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-secondary);
	}

	.form-input {
		width: 100%;
		padding: 0.625rem 0.75rem;
		border: 1px solid var(--border-strong);
		border-radius: 8px;
		font: inherit;
		font-size: 0.9375rem;
		color: var(--text-strong);
		background: var(--bg-card);
		resize: vertical;
	}

	.form-input:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
		border-color: var(--accent);
	}

	.footer {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
	}

	.qr-card {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 1rem;
		text-align: center;
		max-width: 320px;
		margin-inline: auto;
	}

	.qr-image {
		background: #fff;
		padding: 0.5rem;
		border-radius: 8px;
		margin-inline: auto;
		display: block;
	}

	.qr-placeholder {
		width: 180px;
		height: 180px;
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--bg-muted);
		border-radius: 8px;
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	.qr-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		justify-content: center;
	}

	@media (max-width: 720px) {
		.code-card {
			padding: 1.25rem 0.75rem;
			flex-direction: column;
		}

		.code {
			letter-spacing: 0.06em;
		}

		.timer {
			flex: 1 1 10rem;
		}

	.qr-card {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 1rem;
		text-align: center;
		max-width: 320px;
		margin-inline: auto;
	}

	.qr-card {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 1rem;
		text-align: center;
		max-width: 320px;
		margin-inline: auto;
	}

	.qr-image {
		background: #fff;
		padding: 0.5rem;
		border-radius: 8px;
		margin-inline: auto;
		display: block;
	}

	.qr-code {
		font-family: 'JetBrains Mono', monospace;
		font-size: 1.25rem;
		font-weight: 700;
		letter-spacing: 0.12em;
		color: var(--text-strong);
		margin: 0;
	}

	.qr-placeholder {
		width: 180px;
		height: 180px;
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--bg-muted);
		border-radius: 8px;
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	.qr-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		justify-content: center;
	}

	.tiles,
	.detail-grid {
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
