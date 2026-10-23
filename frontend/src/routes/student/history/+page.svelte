<script lang="ts">
	import Skeleton from '$lib/components/Skeleton.svelte';
	import { onMount } from 'svelte';
	import { APIError } from '$lib/api/client';
	import {
		exportSessionHistoryCsvWithFallback,
		getSchedule,
		getSessionHistory,
		listStudentExcuses,
		STUDENT_EXCUSE_REASON_MIN_LENGTH,
		STUDENT_EXCUSE_REASON_SHORT_MESSAGE,
		submitStudentExcuse,
		type StudentExcuseRequest,
		type StudentHistoryRow,
		type StudentHistoryStatus,
	} from '$lib/features/student/service';
	import type { ScheduledClass } from '$lib/shared/types';
	import { flushQueue, queue, type QueuedScan } from '$lib/features/sync/service';
	import {
		ATTACHMENTS_MAX_FILES,
		uploadAttachments,
		validateAttachmentFiles,
	} from '$lib/features/excuse/attachments';
	import { formatDate, formatTime } from '$lib/shared/utils/format';
	import { trapFocus } from '$lib/shared/actions/focusTrap';
import ConfirmExportDialog from '$lib/components/ConfirmExportDialog.svelte';

	type Status = StudentHistoryStatus;
	type Row = {
		id: number;
		sessionId: number;
		date: string;
		course: string;
		courseName: string;
		status: Status;
		time: string;
		scannedAt: string;
		excuseReason?: string;
	};
	type SortKey = 'date' | 'course' | 'status' | 'time';

	let rows: Row[] = $state([]);
	let loading = $state(true);
	let loadError: string | null = $state(null);
	let total = $state(0);
	let summary: {
		compliance_rate: number;
		participation_rate: number;
		counts: Record<Status, number> | Record<string, number>;
	} | null = $state(null);

	// Course filter options: the full enrollment list from GET
	// /student/schedule (code + name), so every enrolled course is
	// selectable even before its rows load. Falls back to the codes seen on
	// the loaded rows when the schedule call fails (offline/mock).
	let scheduleCourses = $state<ScheduledClass[]>([]);
	const courseOptions = $derived.by(() => {
		const seen = new Map<string, string>();
		for (const c of scheduleCourses) {
			if (!seen.has(c.courseCode)) seen.set(c.courseCode, c.courseName);
		}
		if (seen.size > 0) {
			return [...seen].map(([code, name]) => ({ code, name }));
		}
		return [...new Set(rows.map((r) => r.course))].map((code) => ({
			code,
			name: rows.find((r) => r.course === code)?.courseName ?? '',
		}));
	});
	const STATUSES: Status[] = ['present', 'late', 'absent', 'excused', 'pending', 'rejected'];

	let sortKey: SortKey = $state('date');
	let sortAsc = $state(false);
	let filterCourse = $state('All');
	let filterStatus = $state('All');
	let search = $state('');
	let page = $state(1);

	const PER_PAGE = 5;

	const toRow = (item: StudentHistoryRow): Row => ({
		id: item.id,
		sessionId: item.sessionId,
		date: formatDate(item.scannedAt),
		course: item.courseCode,
		courseName: item.courseName,
		status: item.status,
		time: formatTime(item.scannedAt),
		scannedAt: item.scannedAt,
		excuseReason: item.excuseReason,
	});

	// Monotonic sequence token shared by both fetch paths: control changes can
	// fire fetches out of order, and the older response resolving last would
	// otherwise overwrite rows/total/summary with the wrong page (sort glyph
	// then disagreement with the data). A superseded response is dropped in
	// both success and error paths, and only the latest run owns `loading`.
	let loadSeq = 0;

	const load = async () => {
		const seq = ++loadSeq;
		loading = true;
		loadError = null;
		try {
			const res = await getSessionHistory({
				status: filterStatus !== 'All' ? (filterStatus.toLowerCase() as Status) : undefined,
				sortBy: sortKey,
				sortDir: sortAsc ? 'asc' : 'desc',
				page,
				size: PER_PAGE,
			});
			if (seq !== loadSeq) return;
			// Clamp the page when the server total shrank under it — otherwise
			// the paginator points past the last page and the table renders
			// empty until a control changes. The effect refires on the write.
			const pageCount = Math.max(1, Math.ceil(res.total / PER_PAGE));
			if (page > pageCount) {
				page = pageCount;
				return;
			}
			rows = res.items.map(toRow);
			total = res.total;
			summary = res.summary;
			void loadMyRequests();
		} catch (e) {
			if (seq !== loadSeq) return;
			loadError =
				e instanceof APIError
					? e.message
					: e instanceof Error
						? e.message
						: 'Unable to load attendance history';
			rows = [];
		} finally {
			if (seq === loadSeq) loading = false;
		}
	};

	// Offline queue strip: actionable local scans (pending/syncing/rejected)
	// render above the server table and never merge into it, so the server
	// total, pagination, and summary math stay exact. Synced rows are
	// excluded — the server history picks them up after the flush.
	type QueueRow = {
		id: string;
		sessionCode: string;
		date: string;
		time: string;
		status: 'pending' | 'rejected';
		reason: string | null;
	};

	let queueRows = $state<QueueRow[]>([]);
	let queueBusy = $state(false);

	const toQueueRow = (item: QueuedScan): QueueRow => ({
		id: item.id,
		sessionCode: item.payload.sessionCode,
		date: formatDate(item.payload.scannedAt),
		time: formatTime(item.payload.scannedAt),
		status: item.status === 'rejected' ? 'rejected' : 'pending',
		reason: item.lastError
	});

	const refreshQueue = async () => {
		try {
			const [pending, rejected] = await Promise.all([queue.getPending(), queue.getRejected()]);
			queueRows = [...pending, ...rejected].map(toQueueRow);
		} catch {
			queueRows = [];
		}
	};

	const syncNow = async () => {
		if (queueBusy) return;
		queueBusy = true;
		try {
			await flushQueue();
		} finally {
			await refreshQueue();
			queueBusy = false;
		}
	};

	const retryQueued = async (id: string) => {
		await queue.updateStatus(id, 'pending').catch(() => undefined);
		await syncNow();
	};

	const discardQueued = async (id: string) => {
		await queue.remove(id).catch(() => undefined);
		await refreshQueue();
	};

	onMount(() => {
		// Server rows load via the $effect below (sort/status/page), so no
		// explicit load() here — otherwise mount fires two identical GETs.
		void refreshQueue();
		void getSchedule()
			.then((courses) => {
				scheduleCourses = courses;
			})
			.catch(() => {
				scheduleCourses = [];
			});
		const handleVisible = () => {
			if (document.visibilityState === 'visible') void refreshQueue();
		};
		document.addEventListener('visibilitychange', handleVisible);
		return () => {
			document.removeEventListener('visibilitychange', handleVisible);
		};
	});

	// Reload server page when the server-side controls change. rows/total/
	// loading are written by load() but never read here, so no reload loop.
	// Excuse list refreshes alongside history so sort/page never show stale requests.
	$effect(() => {
		const key = sortKey;
		const asc = sortAsc;
		const status = filterStatus;
		const p = page;
		// Same sequence token as load() so effect-driven and Retry-driven
		// fetches cannot interleave out of order.
		const seq = ++loadSeq;
		void (async () => {
			loading = true;
			loadError = null;
			try {
				const res = await getSessionHistory({
					status: status !== 'All' ? (status.toLowerCase() as Status) : undefined,
					sortBy: key,
					sortDir: asc ? 'asc' : 'desc',
					page: p,
					size: PER_PAGE,
				});
				if (seq !== loadSeq) return;
				// Same shrink clamp as load(): a stale page taller than the new
				// total must step back rather than showing an empty table.
				const pageCount = Math.max(1, Math.ceil(res.total / PER_PAGE));
				if (page > pageCount) {
					page = pageCount;
					return;
				}
				rows = res.items.map(toRow);
				total = res.total;
				summary = res.summary;
				void loadMyRequests();
			} catch (e) {
				if (seq !== loadSeq) return;
				loadError =
					e instanceof APIError
						? e.message
						: e instanceof Error
							? e.message
							: 'Unable to load attendance history';
				rows = [];
			} finally {
				if (seq === loadSeq) loading = false;
			}
		})();
	});

	const reload = () => {
		void load();
	};

	const handleSort = (key: SortKey) => {
		if (sortKey === key) {
			sortAsc = !sortAsc;
		} else {
			sortKey = key;
			sortAsc = true;
		}
	};

	const sortGlyph = (key: SortKey): string =>
		sortKey === key ? (sortAsc ? '▲' : '▼') : '⇅';

	const badgeLabel = (status: Status): string =>
		status.charAt(0).toUpperCase() + status.slice(1);

	const excuseLabel = (status: StudentExcuseRequest['status']): string =>
		status.charAt(0).toUpperCase() + status.slice(1);

	// Server owns status/sort/page; course + search filter the fetched rows
	// client-side by course code (the filter options above come from the live
	// schedule, with row-derived codes as the offline fallback).
	const matchesFilters = (r: Row): boolean => {
		if (filterCourse !== 'All' && r.course !== filterCourse) return false;
		if (
			search &&
			!r.course.toLowerCase().includes(search.toLowerCase()) &&
			!r.date.toLowerCase().includes(search.toLowerCase()) &&
			!r.courseName.toLowerCase().includes(search.toLowerCase())
		) {
			return false;
		}
		return true;
	};

	const filtered = $derived(rows.filter(matchesFilters));

	const pages = $derived(Math.max(1, Math.ceil(total / PER_PAGE)));
	const paged = $derived(filtered);

	let exporting = $state(false);
	let exportError: string | null = $state(null);
	let exportNote: string | null = $state(null);

	let pendingExport = $state<null | {
		run: () => void | Promise<void>;
		details?: { label: string; value: string }[];
		title?: string;
		message?: string;
		confirmLabel?: string;
		busyLabel?: string;
	}>(null);

	// Export is server-side (GET /student/attendance/history/export), so the
	// file holds every matching row — the old client path paged through the list
	// endpoint and stopped at 2000.
	//
	// The tradeoff: the export route only knows the filters the server knows.
	// Status and course id go over the wire; the course dropdown and the search
	// box are client-side on this page (see matchesFilters), so they do not
	// unless they can be expressed server-side. Rather than silently returning
	// more rows than the screen shows, `droppedFilters` names whatever is being
	// left behind and the page surfaces it next to the button.
	//
	// The course dropdown holds codes, the route takes an id, so the code is
	// resolved through the schedule enrollments. A student can hold the same
	// course code in more than one offering, in which case there is no single
	// correct id and the filter is reported as dropped rather than guessed.
	const courseIdForExport = $derived.by(() => {
		if (filterCourse === 'All') return undefined;
		const ids = [
			...new Set(scheduleCourses.filter((c) => c.courseCode === filterCourse).map((c) => c.courseId)),
		];
		return ids.length === 1 ? ids[0] : undefined;
	});

	const droppedFilters = $derived.by(() => {
		const dropped: string[] = [];
		if (search.trim()) dropped.push('the search box');
		if (filterCourse !== 'All' && courseIdForExport === undefined) dropped.push('the course filter');
		return dropped;
	});

	const exportCsv = async () => {
		if (exporting) return;
		exporting = true;
		exportError = null;
		exportNote = null;
		try {
			const status = filterStatus !== 'All' ? (filterStatus.toLowerCase() as Status) : undefined;
			const { csv, fromFallback } = await exportSessionHistoryCsvWithFallback(
				{
					status,
					courseId: courseIdForExport,
					sortBy: sortKey,
					sortDir: sortAsc ? 'asc' : 'desc',
				},
				filtered
			);
			if (fromFallback) {
				exportNote =
					'Mock mode: exported the rows on screen (server CSV is unavailable without a backend).';
			}

			// Header-only means the filter matched nothing, which is worth saying
			// rather than handing over an empty file.
			const lines = csv.split('\n').filter((line) => line.trim().length > 0);
			if (lines.length <= 1) {
				exportError = 'No records to export.';
				return;
			}

			const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			const stamp = new Date().toISOString().slice(0, 10);
			const scope = filterStatus !== 'All' ? filterStatus.toLowerCase() : 'all';
			a.download = `attendance-history-${scope}-${stamp}.csv`.replace(/[^a-z0-9._-]+/gi, '-');
			document.body.appendChild(a);
			a.click();
			a.remove();
			setTimeout(() => URL.revokeObjectURL(url), 60_000);

			if (droppedFilters.length > 0 && !exportNote) {
				exportNote = `Exported every matching row. ${droppedFilters.join(' and ')} ${
					droppedFilters.length === 1 ? 'is' : 'are'
				} applied on screen only, so ${droppedFilters.length === 1 ? 'it is' : 'they are'} not in the file.`;
			}
		} catch (e) {
			exportError = e instanceof Error ? e.message : 'Export failed. Please try again.';
		} finally {
			exporting = false;
		}
	};

	const doPrint = () => {
		window.print();
	};

	// Student excuse requests (Path C submit side). Only absent/late/rejected
	// rows are excusable server-side (422 excuse_not_eligible otherwise); a
	// second submit while one is pending fails with 409 duplicate_excuse.
	// Reason floor is STUDENT_EXCUSE_REASON_MIN_LENGTH. Evidence files (up to
	// ATTACHMENTS_MAX_FILES) upload via the D24 presigned flow before submit.
	const canRequestExcuse = (status: Status): boolean =>
		status === 'absent' || status === 'late' || status === 'rejected';

	const EXCUSE_ERROR_MESSAGES: Record<string, string> = {
		duplicate_excuse: 'You already have a pending request for this session.',
		excuse_not_eligible: 'Only absent, late, or rejected records can be excused.',
		already_excused: 'This record is already excused.',
		not_enrolled: 'You are not enrolled in this course offering.',
		attendance_not_found: 'No attendance record found for this session.',
		session_not_found: 'Session not found.',
		student_not_found: 'No student record found for your account. Contact an administrator.',
		invalid_attachment: 'One of the files was rejected. Only PDF, JPG, PNG, or HEIC up to 5 MiB each.',
		file_too_large: 'One of the files exceeds the 5 MiB limit.',
		storage_unconfigured: 'File uploads are unavailable right now — submit without files or try again later.',
	};

	const toExcuseMessage = (error: unknown, fallback: string): string => {
		if (error instanceof APIError && error.code && EXCUSE_ERROR_MESSAGES[error.code]) {
			return EXCUSE_ERROR_MESSAGES[error.code];
		}
		return error instanceof Error && error.message ? error.message : fallback;
	};

	let excuseTarget = $state<Row | null>(null);
	let excuseReason = $state('');
	let excuseBusy = $state(false);
	let excuseError: string | null = $state(null);
	let excuseNotice: string | null = $state(null);
	let excuseFiles = $state<File[]>([]);
	let excuseFileErrors = $state<string[]>([]);
	let excuseUploading = $state(false);
	let excuseUploadStatus = $state('');
	// Object urls already uploaded in a prior attempt — kept across retries
	// so a single failed file never discards the rest.
	let excuseStagedUrls = $state<string[]>([]);

	let myRequests = $state<StudentExcuseRequest[]>([]);
	let myRequestsError: string | null = $state(null);

	const loadMyRequests = async () => {
		try {
			const result = await listStudentExcuses({ page: 1, size: 20 });
			myRequests = result.items;
			myRequestsError = null;
		} catch {
			myRequestsError = 'Excuse requests could not be loaded.';
		}
	};

	const openExcuse = (row: Row) => {
		excuseTarget = row;
		excuseReason = '';
		excuseError = null;
		excuseFiles = [];
		excuseFileErrors = [];
		excuseStagedUrls = [];
		excuseUploadStatus = '';
	};

	const onExcuseFiles = (list: FileList | null) => {
		if (!list) return;
		const { valid, errors } = validateAttachmentFiles([...excuseFiles, ...Array.from(list)]);
		excuseFiles = valid;
		excuseFileErrors = errors;
	};

	const removeExcuseFile = (index: number) => {
		excuseFiles = excuseFiles.filter((_, i) => i !== index);
	};

	const submitExcuse = async () => {
		if (!excuseTarget || excuseBusy) return;
		const reason = excuseReason.trim();
		if (reason.length < STUDENT_EXCUSE_REASON_MIN_LENGTH) {
			excuseError = STUDENT_EXCUSE_REASON_SHORT_MESSAGE;
			return;
		}
		excuseBusy = true;
		excuseError = null;
		try {
			let attachmentUrls = [...excuseStagedUrls];
			if (excuseFiles.length > 0) {
				excuseUploading = true;
				excuseUploadStatus = '';
				try {
					const result = await uploadAttachments(excuseFiles, {
						onProgress: (done, total) => {
							excuseUploadStatus = `Uploading evidence ${done}/${total}…`;
						},
					});
					attachmentUrls = [...attachmentUrls, ...result.ok];
					if (result.failed.length > 0) {
						// Keep successes staged; leave only failed files for retry.
						excuseStagedUrls = attachmentUrls;
						excuseFiles = result.failed.map((f) => f.file);
						excuseFileErrors = result.failed.map((f) => f.message);
						excuseError =
							'Some files failed to upload — retry or remove them. Already-uploaded files are kept.';
						return;
					}
					excuseFiles = [];
					excuseFileErrors = [];
				} finally {
					excuseUploading = false;
					excuseUploadStatus = '';
				}
			}
			await submitStudentExcuse({ sessionId: excuseTarget.sessionId, reason, attachmentUrls });
			excuseTarget = null;
			excuseFiles = [];
			excuseFileErrors = [];
			excuseStagedUrls = [];
			excuseNotice = 'Excuse request submitted — your professor will review it.';
			await loadMyRequests();
		} catch (error) {
			excuseError = toExcuseMessage(error, 'Could not submit the excuse request.');
		} finally {
			excuseBusy = false;
		}
	};
</script>

<div class="page page-enter">
	<header class="header">
		<h1>Attendance History</h1>
		<p class="subtitle">
			{#if summary}
				Compliance {Math.round(summary.compliance_rate * 100)}% · Participation
				{Math.round(summary.participation_rate * 100)}% · {total} records
			{:else}
				Semester: 1st Sem 2026
			{/if}
		</p>
	</header>

	<div class="card filters">
		<div class="search-wrap">
			<input
				class="form-input search-input"
				placeholder="Search..."
				aria-label="Search history"
				value={search}
				oninput={(e) => {
					search = (e.target as HTMLInputElement).value;
				}}
			/>
		</div>

		<select
			class="form-input select-input"
			aria-label="Filter by course"
			value={filterCourse}
			onchange={(e) => {
				filterCourse = (e.target as HTMLSelectElement).value;
				page = 1;
			}}
		>
			<option value="All">All Courses</option>
			{#each courseOptions as course}
				<option value={course.code}>{course.name ? `${course.code} — ${course.name}` : course.code}</option>
			{/each}
		</select>

		<select
			class="form-input select-input"
			aria-label="Filter by status"
			value={filterStatus}
			onchange={(e) => {
				filterStatus = (e.target as HTMLSelectElement).value;
				page = 1;
			}}
		>
			<option value="All">All Statuses</option>
			{#each STATUSES as status}
				<option value={status}>{badgeLabel(status)}</option>
			{/each}
		</select>

		<div class="actions">
			<button class="btn-ghost" onclick={() => (pendingExport = { run: doPrint, title: 'Confirm Print', message: 'Are you sure you want to print this data? Your browser’s print dialog will open after you confirm.', confirmLabel: 'Confirm Print', details: [{ label: 'Format', value: 'Print' }] })}>Print</button>
			<button class="btn-ghost" onclick={() => (pendingExport = { run: exportCsv, details: [{ label: 'Format', value: 'CSV' }, { label: 'Rows', value: String(filtered.length) }] })} disabled={exporting}>
				{exporting ? 'Exporting…' : 'Export CSV'}
			</button>
		</div>
		{#if exportError}
			<p class="export-error" role="status">{exportError}</p>
		{:else if exportNote}
			<p class="export-note" role="status">{exportNote}</p>
		{/if}
	</div>

	{#if queueRows.length > 0}
		<section class="card queue-card" aria-label="Pending sync">
			<div class="queue-head">
				<h2 class="section-title">Pending sync ({queueRows.length})</h2>
				<button class="btn-ghost" disabled={queueBusy} onclick={() => void syncNow()}>
					{queueBusy ? 'Syncing…' : 'Sync now'}
				</button>
			</div>
			<p class="muted">These scans live on this device only — they are not attendance records yet.</p>
			<ul class="queue-list">
				{#each queueRows as item (item.id)}
					<li class="queue-row">
						<span
							class="badge"
							class:pending={item.status === 'pending'}
							class:rejected={item.status === 'rejected'}
							title={item.reason ?? undefined}
						>
							{item.status === 'pending' ? 'Queued' : 'Rejected'}
						</span>
						<span class="mono">{item.date}</span>
						<span class="mono">{item.time}</span>
						<span class="course" title={item.reason ?? 'Session scan awaiting upload'}>
							Session {item.sessionCode}
						</span>
						{#if item.status === 'rejected'}
							<span class="queue-actions">
								<button class="btn-ghost btn-small" onclick={() => void retryQueued(item.id)}>Retry</button>
								<button class="btn-ghost btn-small" onclick={() => void discardQueued(item.id)}>Discard</button>
							</span>
						{/if}
					</li>
				{/each}
			</ul>
		</section>
	{/if}

	<div class="card table-card">
		<div class="scroll">
			<table>
				<thead>
					<tr>
						<th scope="col"><button class="th-btn" onclick={() => handleSort('date')}>Date<span class="sort-glyph">{sortGlyph('date')}</span></button></th>
						<th scope="col"><button class="th-btn" onclick={() => handleSort('course')}>Course<span class="sort-glyph">{sortGlyph('course')}</span></button></th>
						<th scope="col"><button class="th-btn" onclick={() => handleSort('status')}>Status<span class="sort-glyph">{sortGlyph('status')}</span></button></th>
						<th scope="col"><button class="th-btn" onclick={() => handleSort('time')}>Time<span class="sort-glyph">{sortGlyph('time')}</span></button></th>
						<th scope="col"><span class="sr-only">Actions</span></th>
					</tr>
				</thead>
				<tbody>
					{#if loading}
						<tr>
							<td class="empty-row" colspan="5">
								<div class="skeleton-stack" role="status" aria-busy="true">
									<span class="sr-only">Loading attendance history…</span>
									<Skeleton height={12} width="70%" />
									<Skeleton height={12} width="55%" />
								</div>
							</td>
						</tr>
					{:else if loadError}
						<tr>
							<td class="empty-row" colspan="5">
								{loadError}
								<button class="btn-ghost retry-btn" onclick={reload}>Retry</button>
							</td>
						</tr>
					{:else if filtered.length === 0}
						<tr>
							<td class="empty-row" colspan="5">No matching records</td>
						</tr>
					{:else}
						{#each paged as r (r.id)}
							<tr>
								<td class="mono">{r.date}</td>
								<td><span class="course" title={r.courseName}>{r.course}</span></td>
								<td>
									<span
										class="badge"
										class:present={r.status === 'present'}
										class:late={r.status === 'late'}
										class:absent={r.status === 'absent'}
										class:excused={r.status === 'excused'}
										class:pending={r.status === 'pending'}
										class:rejected={r.status === 'rejected'}
									>
										{badgeLabel(r.status)}
									</span>
								</td>
								<td class="mono">{r.time}</td>
								<td>
									{#if canRequestExcuse(r.status)}
										<button
											class="btn-ghost btn-small"
											title={r.excuseReason ? `Previously: ${r.excuseReason}` : 'Request an excuse for this session'}
											onclick={() => openExcuse(r)}
										>
											Request Excuse
										</button>
									{/if}
								</td>
							</tr>
						{/each}
					{/if}
				</tbody>
			</table>
		</div>

		<div class="pagination">
			<button
				class="page-btn"
				onclick={() => (page = Math.max(1, page - 1))}
				disabled={page === 1}
				aria-label="Previous page"
			>
				‹
			</button>
			{#each Array.from({ length: pages }, (_, i) => i + 1) as p (p)}
				<button class="page-btn" class:active={p === page} onclick={() => (page = p)} aria-current={p === page ? 'page' : undefined}>
					{p}
				</button>
			{/each}
			<button
				class="page-btn"
				onclick={() => (page = Math.min(pages, page + 1))}
				disabled={page === pages}
				aria-label="Next page"
			>
				›
			</button>
		</div>
	</div>

	{#if excuseNotice}
		<p class="notice" role="status">{excuseNotice}</p>
	{/if}

	<div class="card table-card">
		<div class="requests-head">
			<h2 class="requests-title">My excuse requests</h2>
			<span class="muted">{myRequests.length} shown</span>
		</div>
		{#if myRequestsError}
			<p class="error">{myRequestsError}</p>
		{:else if myRequests.length === 0}
			<p class="muted">No excuse requests yet. Use Request Excuse on an absent, late, or rejected row above.</p>
		{:else}
			<ul class="requests">
				{#each myRequests as request (request.id)}
					<li class="request-row">
						<span
							class="badge"
							class:present={request.status === 'approved'}
							class:pending={request.status === 'pending'}
							class:rejected={request.status === 'rejected'}
						>
							{excuseLabel(request.status)}
						</span>
						<span class="request-text">
							Session #{request.sessionId} · {request.reason}
							{#if request.attachmentUrls.length > 0}
								<span class="muted"> · {request.attachmentUrls.length} file{request.attachmentUrls.length === 1 ? '' : 's'}</span>
							{/if}
							{#if request.reviewNotes}
								<span class="muted"> — Professor note: {request.reviewNotes}</span>
							{/if}
						</span>
					</li>
				{/each}
			</ul>
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
				use:trapFocus={{ onEscape: () => (excuseTarget = null) }}
			>
				<h2 id="excuse-title">Request excuse</h2>
				<p class="modal-sub">
					{excuseTarget.course} · {excuseTarget.date} {excuseTarget.time} · currently {excuseTarget.status}
				</p>
				<label class="form-label" for="excuse-reason">Reason (min {STUDENT_EXCUSE_REASON_MIN_LENGTH} characters)</label>
				<textarea
					id="excuse-reason"
					class="form-input area"
					rows={4}
					placeholder="Explain why you missed or were late to this session…"
					bind:value={excuseReason}
				></textarea>
				<p class="hint">{excuseReason.trim().length}/2000 · up to {ATTACHMENTS_MAX_FILES} files (PDF/JPG/PNG/HEIC, 5 MiB each)</p>
				<label class="form-label" for="excuse-files">Evidence (optional)</label>
				<input
					id="excuse-files"
					class="form-input"
					type="file"
					multiple
					accept=".pdf,.jpg,.jpeg,.png,.heic"
					disabled={excuseBusy}
					onchange={(e) => onExcuseFiles(e.currentTarget.files)}
				/>
				{#if excuseFiles.length > 0}
					<ul class="files">
						{#each excuseFiles as file, i (file)}
							<li>
								<span>{file.name} · {(file.size / 1024).toFixed(0)} KB</span>
								<button class="link-btn" type="button" disabled={excuseBusy} onclick={() => removeExcuseFile(i)}>
									Remove
								</button>
							</li>
						{/each}
					</ul>
				{/if}
				{#each excuseFileErrors as message (message)}
					<p class="error">{message}</p>
				{/each}
				{#if excuseStagedUrls.length > 0 && excuseFiles.length > 0}
					<p class="hint" role="status">{excuseStagedUrls.length} file{excuseStagedUrls.length === 1 ? '' : 's'} uploaded — retry the remaining.</p>
				{/if}
				{#if excuseUploading}
					<p class="hint" role="status">{excuseUploadStatus || 'Uploading evidence…'}</p>
				{/if}
				{#if excuseError}
					<p class="error">{excuseError}</p>
				{/if}
				<div class="modal-actions">
					<button class="btn-ghost" type="button" disabled={excuseBusy} onclick={() => (excuseTarget = null)}>
						Cancel
					</button>
					<button
						class="btn-primary"
						type="button"
						aria-busy={excuseBusy}
						disabled={excuseBusy}
						onclick={() => void submitExcuse()}
					>
						{excuseBusy ? 'Submitting…' : 'Submit request'}
					</button>
				</div>
			</div>
		</div>
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
	.page {
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
		width: 100%;
		min-width: 0;
	}

	.header h1 {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.625rem;
		font-weight: 700;
		color: var(--text);
		margin: 0 0 0.25rem;
	}

	.subtitle {
		color: var(--text-muted);
		font-size: 0.875rem;
		margin: 0;
	}

	.card {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		box-shadow: var(--shadow-sm);
		min-width: 0;
	}

	.filters {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
		align-items: center;
		padding: 1rem 1.25rem;
		min-width: 0;
	}

	.search-wrap {
		flex: 0 0 auto;
		max-width: 100%;
	}

	.search-input {
		width: 200px;
	}

	.select-input {
		width: auto;
	}

	.filters .select-input {
		min-width: 0;
	}

	.form-input {
		padding: 0.625rem 0.875rem;
		border: 1.5px solid var(--border-strong);
		border-radius: 8px;
		font-size: 0.9375rem;
		font-family: inherit;
		color: var(--text-strong);
		outline: none;
		transition: border-color 0.15s;
		background: var(--bg-card);
	}

	.form-input:focus {
		border-color: var(--accent);
	}

	.actions {
		display: flex;
		gap: 0.5rem;
		margin-left: auto;
	}

	.btn-ghost {
		background: var(--bg-card);
		border: 1px solid var(--border-strong);
		border-radius: 8px;
		padding: 0.5rem 1rem;
		font-size: 0.875rem;
		font-weight: 600;
		font-family: inherit;
		color: var(--brand);
		cursor: pointer;
		transition: background 0.15s ease;
	}

	.btn-ghost:hover {
		background: var(--bg-hover);
	}

	.table-card {
		overflow: hidden;
		min-width: 0;
	}

	.scroll {
		overflow-x: auto;
		max-width: 100%;
	}

	table {
		width: 100%;
		border-collapse: collapse;
		min-width: 560px;
	}

	th {
		text-align: left;
		padding: 0;
		border-bottom: 1px solid var(--border);
		background: var(--bg-page);
	}

	.th-btn {
		display: inline-flex;
		align-items: center;
		padding: 0.75rem 1rem;
		width: 100%;
		border: none;
		background: none;
		font-family: inherit;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-muted);
		cursor: pointer;
	}

	.th-btn:hover {
		color: var(--brand);
	}

	.sort-glyph {
		margin-left: 4px;
	}

	td {
		padding: 0.75rem 1rem;
		border-top: 1px solid var(--divider);
		font-size: 0.9375rem;
		color: var(--text);
	}

	.mono {
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.8125rem;
	}

	.course {
		font-weight: 600;
	}

	.badge {
		display: inline-block;
		padding: 0.125rem 0.625rem;
		border-radius: 999px;
		font-size: 0.8125rem;
		font-weight: 600;
	}

	.badge.present {
		color: var(--success);
		background: var(--success-bg);
		border: 1px solid var(--success-bg);
	}

	.badge.absent {
		color: var(--danger-strong);
		background: var(--danger-bg);
		border: 1px solid var(--danger-bg);
	}

	.badge.pending {
		color: var(--warning-text);
		background: var(--warning-bg);
		border: 1px solid var(--warning-bg);
	}

	.badge.late {
		color: var(--warning-text);
		background: var(--warning-bg);
		border: 1px solid var(--warning-bg);
	}

	.badge.excused {
		color: var(--accent-hover);
		background: var(--info-bg);
		border: 1px solid var(--info-bg);
	}

	.badge.rejected {
		color: var(--text-muted);
		background: var(--bg-muted);
		border: 1px solid var(--border);
	}

	.retry-btn {
		margin-left: 0.75rem;
	}

	.export-error {
		flex-basis: 100%;
		margin: 0;
		color: var(--danger);
		font-size: 0.875rem;
	}

	/* Not a failure — the download succeeded, this just says what the server
	   could not filter on. Muted so it does not read as an error. */
	.export-note {
		flex-basis: 100%;
		margin: 0;
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	.queue-card {
		padding: 1rem 1.25rem;
	}

	.queue-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
	}

	.section-title {
		font-size: 1.125rem;
		font-weight: 700;
		color: var(--text-strong);
		margin: 0;
	}

	.muted {
		color: var(--text-muted);
		font-size: 0.875rem;
		margin: 0.5rem 0 0;
	}

	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
	}

	.notice {
		background: var(--success-bg);
		border: 1px solid var(--success-bg);
		border-radius: 8px;
		padding: 0.625rem 1rem;
		color: var(--success);
		font-size: 0.875rem;
		margin: 0;
	}

	.error {
		color: var(--danger);
		font-size: 0.875rem;
		margin: 0.5rem 0 0;
	}

	.requests-head {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 1rem;
		padding: 1rem 1.25rem 0;
	}

	.requests-title {
		font-size: 1.125rem;
		font-weight: 700;
		color: var(--text-strong);
		margin: 0;
	}

	.requests {
		list-style: none;
		margin: 0.75rem 0 0;
		padding: 0 1.25rem 1.25rem;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.request-row {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		flex-wrap: wrap;
		padding: 0.625rem 0.875rem;
		border: 1px solid var(--divider);
		border-radius: 8px;
		background: var(--bg-muted);
		font-size: 0.9375rem;
		color: var(--text);
	}

	.request-text {
		flex: 1 1 16rem;
	}

	.overlay {
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
		background: var(--bg-card);
		border-radius: 12px;
		box-shadow: var(--shadow-lg);
		padding: 1.5rem;
	}

	.modal h2 {
		margin: 0 0 0.375rem;
		font-size: 1.25rem;
		font-weight: 700;
		color: var(--text);
	}

	.modal-sub {
		margin: 0 0 1rem;
		font-size: 0.9375rem;
		color: var(--text-secondary);
	}

	.form-label {
		display: block;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-secondary);
		margin-bottom: 0.375rem;
	}

	.area {
		width: 100%;
		resize: vertical;
	}

	.hint {
		font-size: 0.75rem;
		color: var(--text-muted);
		margin: 0.375rem 0 0;
	}

	.files {
		list-style: none;
		margin: 0.5rem 0 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
		font-size: 0.8125rem;
	}

	.files li {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
	}

	.link-btn {
		border: 0;
		background: none;
		padding: 0;
		color: var(--accent);
		font: inherit;
		font-weight: 600;
		cursor: pointer;
		text-decoration: underline;
	}

	.link-btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.modal-actions {
		display: flex;
		flex-wrap: wrap;
		justify-content: flex-end;
		gap: 0.75rem;
		margin-top: 1.25rem;
	}

	.btn-primary {
		background: var(--brand);
		border: 1px solid var(--brand);
		border-radius: 8px;
		padding: 0.5rem 1rem;
		font-size: 0.875rem;
		font-weight: 600;
		font-family: inherit;
color: var(--on-brand);
	}

	.btn-primary:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.queue-list {
		list-style: none;
		margin: 0.75rem 0 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.queue-row {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		flex-wrap: wrap;
		padding: 0.625rem 0.875rem;
		border: 1px solid var(--divider);
		border-radius: 8px;
		background: var(--bg-muted);
		font-size: 0.9375rem;
		color: var(--text);
	}

	.queue-actions {
		display: flex;
		gap: 0.375rem;
		margin-left: auto;
	}

	.btn-small {
		padding: 0.25rem 0.625rem;
		font-size: 0.8125rem;
	}

	.empty-row {
		text-align: center;
		color: var(--text-muted);
		padding: 2rem 1rem;
	}

	.pagination {
		padding: 0.75rem 1rem;
		border-top: 1px solid var(--border);
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.page-btn {
		background: none;
		border: 1px solid var(--border);
		border-radius: 6px;
		padding: 0.25rem 0.625rem;
		font-family: inherit;
		font-size: 0.875rem;
		color: var(--brand);
		cursor: pointer;
	}

	.page-btn:hover:not(:disabled) {
		background: var(--bg-hover);
	}

	.page-btn.active {
		background: var(--brand);
		color: var(--on-brand);
		font-weight: 700;
		border-color: var(--brand);
	}

	.page-btn:disabled {
		color: var(--text-muted);
		cursor: not-allowed;
	}

	:global(.page :is(button, input, select):focus-visible) {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	@media (max-width: 640px) {
		.select-input {
			width: 100%;
		}

		.search-input {
			width: 100%;
		}

		.search-wrap {
			flex: 1 1 100%;
		}

		.actions {
			margin-left: 0;
			width: 100%;
		}

		.btn-ghost {
			flex: 1;
		}
	}
</style>