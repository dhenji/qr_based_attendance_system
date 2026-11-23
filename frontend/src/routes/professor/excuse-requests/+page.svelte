<script lang="ts">
	import EmptyState from '$lib/components/EmptyState.svelte';
	import Pagination from '$lib/components/Pagination.svelte';
	import SkeletonTable from '$lib/components/SkeletonTable.svelte';
	import {
		editExcuse,
		EXCUSE_REASON_MIN_LENGTH,
		listExcuseRequests,
		quickExcuse,
		quickExcuseByIds,
		revokeExcuse,
		reviewExcuseRequest,
		type ExcuseFilters
	} from '$lib/features/excuse/service';
	import { listSessions } from '$lib/features/session/service';
	import { listOfferingStudents } from '$lib/features/professor/service';
	import type { AdminRosterItem } from '$lib/shared/types/admin';	import { isMockMode } from '$lib/api/client';
	import {
		ATTACHMENTS_MAX_FILES,
		uploadAttachments,
		validateAttachmentFiles,
	} from '$lib/features/excuse/attachments';
	import { PROFESSOR_COURSES } from '$lib/features/professor/mock';
	import {
		initProfessorCourses,
		professorState
	} from '$lib/features/professor/store.svelte';
	import type { ExcuseInitiatedVia, ExcuseOriginalStatus, ExcuseRequest, ExcuseStatus } from '$lib/shared/types/excuse';
	import { formatDate } from '$lib/shared/utils/format';
	import { debounce } from '$lib/shared/utils/debounce';
	import { describeError } from '$lib/shared/utils/errors';
	import { trapFocus } from '$lib/shared/actions/focusTrap';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { onMount } from 'svelte';

	type QueueRow = ExcuseRequest;

	const statusOptions: Array<'All' | ExcuseStatus> = ['All', 'pending', 'approved', 'rejected'];
	const originalOptions: ExcuseOriginalStatus[] = ['absent', 'late', 'rejected'];

	// Course directory: mock fixtures until the live assignments warm it. The
	// queue rows already join live course identity in excuse/service.ts, so the
	// filter options and quick-excuse lookup read the same source — a
	// professor whose real courses differ from the fixtures gets working
	// filters instead of options that match nothing.
	type DirectoryEntry = {
		courseCode: string;
		courseName: string;
		section: string;
		offeringId: number;
	};

	let directory = $state<DirectoryEntry[]>(PROFESSOR_COURSES);
	const courseOptions = $derived([...new Set(directory.map((c) => c.courseCode))].sort());

	$effect(() => {
		let cancelled = false;
		if (isMockMode()) return;
		void initProfessorCourses().then(() => {
			if (cancelled || professorState.coursesError) return;
			const warmed: DirectoryEntry[] = professorState.courses.map((c) => ({
				courseCode: c.courseCode,
				courseName: c.courseName,
				section: c.sections.length > 0 ? c.sections.join(', ') : '—',
				offeringId: c.offeringId
			}));
			if (warmed.length > 0) directory = warmed;
		});
		return () => {
			cancelled = true;
		};
	});

	let searchInput = $state('');
	let search = $state('');
	let course = $state('All');
	let section = $state('All');
	let initiatedVia = $state<'All' | ExcuseInitiatedVia>('All');
	let hasEvidence = $state<'All' | 'yes' | 'no'>('All');
	let originalStatus = $state<'All' | ExcuseOriginalStatus>('All');
	let reviewer = $state('');
	let status = $state<'All' | ExcuseStatus>('pending');
	let from = $state('');
	let to = $state('');
	let submittedFrom = $state('');
	let submittedTo = $state('');
	let reviewedFrom = $state('');
	let reviewedTo = $state('');
	let sortBy = $state<'requested_at' | 'reviewed_at' | 'status' | 'student_name' | 'id'>('requested_at');
	let sortDir = $state<'asc' | 'desc'>('desc');
	let pageSize = $state(10);
	let showAdvanced = $state(false);
	let currentPage = $state(1);
	let rows = $state<QueueRow[]>([]);
	let total = $state(0);
	let counts = $state({ pending: 0, approved: 0, rejected: 0 });
	let isLoading = $state(true);
	let loadError = $state<string | null>(null);
	let reloadToken = $state(0);

	let selected = $state<QueueRow | null>(null);
	let reviewNotes = $state('');
	let reviewBusy = $state(false);
	let reviewError = $state<string | null>(null);

	let quickOpen = $state(false);
	// Searchable student selection (replaces manual number/name entry).
	let quickStudentSearch = $state('');
	let quickSelectedStudent = $state<AdminRosterItem | null>(null);
	let quickEnrolledCourseCodes = $state<string[]>([]);
	let quickEnrolledLoading = $state(false);
	let quickEnrolledError = $state<string | null>(null);
	let quickRoster = $state<AdminRosterItem[]>([]);
	let quickRosterLoading = $state(false);
	let quickRosterError = $state<string | null>(null);
	let quickCourse = $state('CS101');
	let quickOriginal = $state<ExcuseOriginalStatus>('absent');
	let quickReason = $state('');
	let quickBusy = $state(false);
	let quickError = $state<string | null>(null);
	let quickFiles = $state<File[]>([]);
	let quickFileErrors = $state<string[]>([]);
	let quickUploading = $state(false);
	let quickUploadStatus = $state('');
	// Object urls already uploaded in a prior attempt — kept across retries
	// so a single failed file never discards the rest.
	let quickStagedUrls = $state<string[]>([]);
	// Real sessions for the quick-excuse picker (warmed when the modal
	// opens). Each carries its offering id so the roster can be loaded for
	// the selected session.
	let quickSessions = $state<Array<{ id: number; code: string; offeringId: number }>>([]);
	let quickSessionId = $state<number | null>(null);

	// Detail-modal edit/revoke for professor-issued rows (quick /
	// prof_with_evidence carry integer ids; student requests 404 on edit
	// server-side, so those buttons stay hidden for them).
	let editMode = $state(false);
	let editReason = $state('');
	let editNotes = $state('');
	let editBusy = $state(false);
	let editError = $state<string | null>(null);
	let revokeAsk = $state(false);
	let revokeBusy = $state(false);
	let revokeError = $state<string | null>(null);

	const canModify = (row: QueueRow): boolean =>
		row.status === 'approved' &&
		(row.initiatedVia === 'quick' || row.initiatedVia === 'prof_with_evidence');

	let notice = $state<string | null>(null);

	// Reset selections the warmed directory invalidates (same convention as
	// the reports page filters).
	$effect(() => {
		if (course !== 'All' && !courseOptions.includes(course)) course = 'All';
		if (!courseOptions.includes(quickCourse)) quickCourse = courseOptions[0] ?? 'CS101';
	});

	const searchDebounced = debounce((value: string) => {
		search = value.trim();
		currentPage = 1;
	});

	$effect(() => {
		searchDebounced(searchInput);
		return () => searchDebounced.cancel();
	});

	let urlReady = $state(false);

	onMount(() => {
		const p = $page.url.searchParams;
		if (p.get('status')) status = p.get('status') as 'All' | ExcuseStatus;
		if (p.get('course')) course = p.get('course')!;
		if (p.get('section')) section = p.get('section')!;
		if (p.get('initiated_via')) initiatedVia = p.get('initiated_via') as 'All' | ExcuseInitiatedVia;
		if (p.get('has_evidence')) hasEvidence = p.get('has_evidence') === 'true' ? 'yes' : 'no';
		if (p.get('original_status')) originalStatus = p.get('original_status') as 'All' | ExcuseOriginalStatus;
		if (p.get('reviewer')) reviewer = p.get('reviewer')!;
		if (p.get('search')) searchInput = p.get('search')!;
		if (p.get('from')) from = p.get('from')!;
		if (p.get('to')) to = p.get('to')!;
		if (p.get('submitted_from')) submittedFrom = p.get('submitted_from')!;
		if (p.get('submitted_to')) submittedTo = p.get('submitted_to')!;
		if (p.get('reviewed_from')) reviewedFrom = p.get('reviewed_from')!;
		if (p.get('reviewed_to')) reviewedTo = p.get('reviewed_to')!;
		if (p.get('sort_by')) sortBy = p.get('sort_by') as typeof sortBy;
		if (p.get('sort_dir')) sortDir = p.get('sort_dir') as 'asc' | 'desc';
		if (p.get('size')) pageSize = Number(p.get('size')) || pageSize;
		if (p.get('page')) currentPage = Number(p.get('page')) || currentPage;
		urlReady = true;
	});

	$effect(() => {
		if (!urlReady) return;
		const params = new URLSearchParams();
		if (status !== 'All') params.set('status', status);
		if (course !== 'All') params.set('course', course);
		if (section !== 'All') params.set('section', section);
		if (initiatedVia !== 'All') params.set('initiated_via', initiatedVia);
		if (hasEvidence !== 'All') params.set('has_evidence', hasEvidence === 'yes' ? 'true' : 'false');
		if (originalStatus !== 'All') params.set('original_status', originalStatus);
		if (reviewer) params.set('reviewer', reviewer);
		if (search) params.set('search', search);
		if (from) params.set('from', from);
		if (to) params.set('to', to);
		if (submittedFrom) params.set('submitted_from', submittedFrom);
		if (submittedTo) params.set('submitted_to', submittedTo);
		if (reviewedFrom) params.set('reviewed_from', reviewedFrom);
		if (reviewedTo) params.set('reviewed_to', reviewedTo);
		if (sortBy !== 'requested_at') params.set('sort_by', sortBy);
		if (sortDir !== 'desc') params.set('sort_dir', sortDir);
		if (pageSize !== 10) params.set('size', String(pageSize));
		if (currentPage > 1) params.set('page', String(currentPage));
		const query = params.toString();
		void goto(query ? `?${query}` : '?', { replaceState: true, keepFocus: true, noScroll: true });
	});

	const buildFilters = (): ExcuseFilters => {
		let start = from || undefined;
		let end = to || undefined;
		if (start && end && start > end) [start, end] = [end, start];
		let sStart = submittedFrom || undefined;
		let sEnd = submittedTo || undefined;
		if (sStart && sEnd && sStart > sEnd) [sStart, sEnd] = [sEnd, sStart];
		let rStart = reviewedFrom || undefined;
		let rEnd = reviewedTo || undefined;
		if (rStart && rEnd && rStart > rEnd) [rStart, rEnd] = [rEnd, rStart];
		return {
			status: status === 'All' ? undefined : status,
			course: course === 'All' ? undefined : course,
			section: section === 'All' ? undefined : section,
			initiatedVia: initiatedVia === 'All' ? undefined : initiatedVia,
			hasEvidence: hasEvidence === 'All' ? undefined : hasEvidence === 'yes',
			originalStatus: originalStatus === 'All' ? undefined : originalStatus,
			reviewer: reviewer || undefined,
			search: search || undefined,
			from: start,
			to: end,
			submittedFrom: sStart,
			submittedTo: sEnd,
			reviewedFrom: rStart,
			reviewedTo: rEnd,
			sortBy: sortBy,
			sortDir: sortDir,
			page: currentPage,
			size: pageSize
		};
	};

	$effect(() => {
		const query = buildFilters();
		reloadToken;

		let cancelled = false;
		isLoading = true;
		loadError = null;

		const load = async () => {
			try {
				const result = await listExcuseRequests(query);
				if (cancelled) return;
				rows = result.items;
				total = result.total;
				counts = result.counts;
				if (result.page !== currentPage) currentPage = result.page;
			} catch {
				if (!cancelled) loadError = 'Excuse requests could not be loaded.';
			} finally {
				if (!cancelled) isLoading = false;
			}
		};

		void load();
		return () => {
			cancelled = true;
		};
	});

	const pageCount = $derived(Math.max(1, Math.ceil(total / pageSize)));
	const rangeText = $derived.by(() => {
		if (total === 0) return '0 of 0 requests';
		const start = (currentPage - 1) * pageSize + 1;
		const end = Math.min(currentPage * pageSize, total);
		return `${start}–${end} of ${total} requests`;
	});

	const summaryText = $derived(
		`Pending ${counts.pending} · Approved ${counts.approved} · Rejected ${counts.rejected}`
	);

	const hasActiveFilters = $derived(
		status !== 'All' ||
			course !== 'All' ||
			section !== 'All' ||
			initiatedVia !== 'All' ||
			hasEvidence !== 'All' ||
			originalStatus !== 'All' ||
			reviewer !== '' ||
			search !== '' ||
			from !== '' ||
			to !== '' ||
			submittedFrom !== '' ||
			submittedTo !== '' ||
			reviewedFrom !== '' ||
			reviewedTo !== ''
	);

	const resetFilters = () => {
		search = '';
		course = 'All';
		section = 'All';
		initiatedVia = 'All';
		hasEvidence = 'All';
		originalStatus = 'All';
		reviewer = '';
		status = 'All';
		from = '';
		to = '';
		submittedFrom = '';
		submittedTo = '';
		reviewedFrom = '';
		reviewedTo = '';
		sortBy = 'requested_at';
		sortDir = 'desc';
		pageSize = 10;
		currentPage = 1;
	};

	const openDetail = (row: QueueRow) => {
		selected = row;
		reviewNotes = '';
		reviewError = null;
		editMode = false;
		editReason = row.reason;
		editNotes = row.reviewNotes ?? '';
		editError = null;
		revokeAsk = false;
		revokeError = null;
	};

	const closeDetail = () => {
		if (reviewBusy || editBusy || revokeBusy) return;
		selected = null;
		reviewNotes = '';
		reviewError = null;
		editMode = false;
		revokeAsk = false;
	};

	const doReview = async (decision: 'approved' | 'rejected') => {
		if (!selected || reviewBusy) return;
		reviewBusy = true;
		reviewError = null;
		try {
			const updated = await reviewExcuseRequest(selected.id, {
				status: decision,
				review_notes: reviewNotes || undefined
			});
			selected = updated;
			notice =
				decision === 'approved'
					? `Approved — ${updated.studentName} is now excused (was ${originalLabel(updated.originalStatus)}).`
					: `Rejected — ${updated.studentName} keeps ${originalLabel(updated.originalStatus)} status.`;
			reloadToken += 1;
		} catch (error) {
			reviewError = describeError(error, 'Review failed.');
		} finally {
			reviewBusy = false;
		}
	};

	const openQuick = () => {
		quickOpen = true;
		quickError = null;
		quickFiles = [];
		quickFileErrors = [];
		quickStagedUrls = [];
		quickUploadStatus = '';
		quickStudentSearch = '';
		quickSelectedStudent = null;
		quickRoster = [];
		quickEnrolledCourseCodes = [];
		quickEnrolledLoading = false;
		quickEnrolledError = null;
		quickRosterError = null;
		// Warm real sessions so the excuse attaches to an actual session id.
		// Each carries its offering id so the roster can be loaded for the
		// selected session (searchable student selector, no manual names).
		void listSessions({ size: 50 })
			.then(({ items }) => {
				if (items.length === 0) return;
				quickSessions = items.map((item) => ({
					id: item.id,
					code: item.sessionCode,
					offeringId: item.offeringId,
				}));
				if (quickSessionId === null || !quickSessions.some((s) => s.id === quickSessionId)) {
					quickSessionId = quickSessions[0].id;
				}
			})
			.catch(() => undefined);
	};

	// Load the offering roster whenever the selected session changes, so the
	// student selector never offers students outside that offering.
	$effect(() => {
		if (!quickOpen || quickSessionId === null) return;
		const session = quickSessions.find((s) => s.id === quickSessionId);
		if (!session) return;
		let cancelled = false;
		quickRosterLoading = true;
		quickRosterError = null;
		quickRoster = [];
		quickSelectedStudent = null;
		void listOfferingStudents(session.offeringId, { size: 100 })
			.then(({ items }) => {
				if (cancelled) return;
				quickRoster = items;
				if (items.length === 1) quickSelectedStudent = items[0];
			})
			.catch(() => {
				if (!cancelled) quickRosterError = 'Could not load students for this session.';
			})
			.finally(() => {
				if (!cancelled) quickRosterLoading = false;
			});
		return () => {
			cancelled = true;
		};
	});

	// Retrieve the selected student's enrolled courses from actual enrollment
	// records (one roster lookup per offering the professor is assigned to).
	// The result drives the grouped course picker (enrolled vs. other).
	$effect(() => {
		const student = quickSelectedStudent;
		if (!quickOpen) return;
		if (student === null || student.id === undefined) {
			quickEnrolledCourseCodes = [];
			quickEnrolledLoading = false;
			quickEnrolledError = null;
			return;
		}
		let cancelled = false;
		quickEnrolledLoading = true;
		quickEnrolledError = null;
		void (async () => {
			try {
				if (professorState.courses.length === 0 && !isMockMode()) {
					await initProfessorCourses();
				}
				if (cancelled) return;
				const courseList =
					professorState.courses.length > 0
						? professorState.courses.map((c) => ({
								offeringId: c.offeringId,
								courseCode: c.courseCode,
							}))
						: directory.map((c) => ({
								offeringId: c.offeringId,
								courseCode: c.courseCode,
							}));
				const offeringIds = [...new Set(courseList.map((c) => c.offeringId))];
				const enrolled = new Set<string>();
				await Promise.all(
					offeringIds.map(async (offeringId) => {
						try {
							const { items } = await listOfferingStudents(offeringId, { size: 100 });
							if (items.some((row) => row.id === student.id || row.studentId === student.studentId)) {
								const course = courseList.find((c) => c.offeringId === offeringId);
								if (course) enrolled.add(course.courseCode);
							}
						} catch {
							// Ignore per-offering failures; other offerings still resolve.
						}
					})
				);
				if (cancelled) return;
				const sorted = [...enrolled].sort();
				quickEnrolledCourseCodes = sorted;
				if (sorted.length > 0) {
					quickCourse = sorted[0];
				}
			} catch {
				if (!cancelled) quickEnrolledError = 'Could not load enrolled courses for this student.';
			} finally {
				if (!cancelled) quickEnrolledLoading = false;
			}
		})();
		return () => {
			cancelled = true;
		};
	});

	const quickCourseOfferingIds = $derived(
		new Set(
			(professorState.courses.length > 0
				? professorState.courses
				: directory.map((c) => ({ offeringId: c.offeringId, courseCode: c.courseCode }))
			)
				.filter((c) => c.courseCode === quickCourse)
				.map((c) => c.offeringId)
		)
	);
	const quickVisibleSessions = $derived(
		quickSessions.filter((s) =>
			quickCourseOfferingIds.size === 0 ? true : quickCourseOfferingIds.has(s.offeringId)
		)
	);

	$effect(() => {
		const sessions = quickVisibleSessions;
		if (sessions.length === 0) return;
		if (!sessions.some((s) => s.id === quickSessionId)) {
			quickSessionId = sessions[0].id;
		}
	});

	const closeQuick = () => {
		if (quickBusy) return;
		quickOpen = false;
		quickError = null;
	};

	const onQuickFiles = (list: FileList | null) => {
		if (!list) return;
		const { valid, errors } = validateAttachmentFiles([...quickFiles, ...Array.from(list)]);
		quickFiles = valid;
		quickFileErrors = errors;
	};

	const doQuickExcuse = async () => {
		if (quickBusy) return;
		quickBusy = true;
		quickError = null;
		try {
			const offering = directory.find((c) => c.courseCode === quickCourse);
			const picked = quickSessions.find((s) => s.id === quickSessionId) ?? null;
			if (quickSelectedStudent === null || quickSelectedStudent.id === undefined) {
				throw new Error('Select a student before submitting.');
			}
			// Files upload first via the D24 presigned flow; their object urls
			// ride along so the created row mirrors them (Path B). Reason-only
			// stays Path A. Partial failures keep prior successes staged and
			// leave only failed files for retry.
			let attachmentUrls = [...quickStagedUrls];
			if (quickFiles.length > 0) {
				quickUploading = true;
				quickUploadStatus = '';
				try {
					const result = await uploadAttachments(quickFiles, {
						onProgress: (done, total) => {
							quickUploadStatus = `Uploading evidence ${done}/${total}…`;
						},
					});
					attachmentUrls = [...attachmentUrls, ...result.ok];
					if (result.failed.length > 0) {
						quickStagedUrls = attachmentUrls;
						quickFiles = result.failed.map((f) => f.file);
						quickFileErrors = result.failed.map((f) => f.message);
						quickError =
							'Some files failed to upload — retry or remove them. Already-uploaded files are kept.';
						return;
					}
					quickFiles = [];
					quickFileErrors = [];
				} finally {
					quickUploading = false;
					quickUploadStatus = '';
				}
			}
			await quickExcuseByIds(
				picked?.id ?? offering?.offeringId ?? 1,
				quickSelectedStudent.id as number,
				quickReason,
				attachmentUrls,
				{
					studentNumber: quickSelectedStudent.studentId,
					studentName: quickSelectedStudent.name,
					section: quickSelectedStudent.section ?? undefined,
				}
			);
			const selectedName = quickSelectedStudent?.name ?? 'student';
			quickOpen = false;
			quickStudentSearch = '';
			quickSelectedStudent = null;
			quickReason = '';
			quickFiles = [];
			quickFileErrors = [];
			quickStagedUrls = [];
			notice = `Quick-excused ${selectedName} — approved immediately.`;
			status = 'approved';
			currentPage = 1;
			reloadToken += 1;
		} catch (error) {
			quickError = describeError(error, 'Quick-excuse failed.');
		} finally {
			quickBusy = false;
		}
	};

	const doEditExcuse = async () => {
		if (!selected || editBusy) return;
		editBusy = true;
		editError = null;
		try {
			const updated = await editExcuse(selected, {
				reason: editReason,
				reviewNotes: editNotes
			});
			selected = updated;
			editMode = false;
			notice = `Excuse #${updated.id} updated.`;
			reloadToken += 1;
		} catch (error) {
			editError = describeError(error, 'Edit failed.');
		} finally {
			editBusy = false;
		}
	};

	const doRevokeExcuse = async () => {
		if (!selected || revokeBusy) return;
		revokeBusy = true;
		revokeError = null;
		try {
			const result = await revokeExcuse(selected);
			selected = { ...selected, status: 'rejected' };
			revokeAsk = false;
			notice =
				result.revertedTo !== null
					? `Excuse #${selected.id} revoked — record reverted to ${result.revertedTo}.`
					: `Excuse #${selected.id} revoked.`;
			reloadToken += 1;
		} catch (error) {
			revokeError = describeError(error, 'Revoke failed.');
		} finally {
			revokeBusy = false;
		}
	};

	const typeLabel = (row: QueueRow): string =>
		row.initiatedVia === 'quick'
			? 'Quick'
			: row.initiatedVia === 'prof_with_evidence'
				? 'With evidence'
				: 'Student request';

	// Live rows carry no pre-excuse status (no professor-visible source), so
	// they read `unknown` — render an em dash rather than a guessed value.
	const originalLabel = (value: ExcuseOriginalStatus): string =>
		value === 'unknown' ? '—' : value;

	const truncated = (value: string, max = 64): string =>
		value.length > max ? `${value.slice(0, max - 1)}…` : value;
</script>

<div class="excuses">
	<header class="header">
		<div>
			<h1>Excuse Requests</h1>
			<p class="muted">Review queue for your courses · {rangeText}</p>
			<p class="muted">Student requests need your review — quick-excuses approve immediately (D21).</p>
		</div>
		<button class="btn btn-primary" type="button" onclick={openQuick}>New excuse</button>
	</header>

	{#if notice}
		<p class="notice" role="status">{notice}</p>
	{/if}

	<section class="summary-cards" aria-label="Excuse request summary">
		<div class="summary-card">
			<span class="summary-label">Total</span>
			<span class="summary-value">{counts.pending + counts.approved + counts.rejected}</span>
		</div>
		<div class="summary-card">
			<span class="summary-label">Pending</span>
			<span class="summary-value">{counts.pending}</span>
		</div>
		<div class="summary-card">
			<span class="summary-label">Approved</span>
			<span class="summary-value">{counts.approved}</span>
		</div>
		<div class="summary-card">
			<span class="summary-label">Rejected</span>
			<span class="summary-value">{counts.rejected}</span>
		</div>
	</section>

	<section class="card filters" aria-label="Excuse filters">
		<div class="filter-grid">
			<div class="field">
				<label class="form-label" for="search">Search</label>
				<input
					id="search"
					class="form-input"
					type="search"
					placeholder="Student, number, code…"
					bind:value={search}
					oninput={() => (currentPage = 1)}
				/>
			</div>
			<div class="field">
				<label class="form-label" for="course">Course</label>
				<select
					id="course"
					class="form-input"
					bind:value={course}
					onchange={() => (currentPage = 1)}
				>
					<option value="All">All courses</option>
					{#each courseOptions as option (option)}
						<option value={option}>{option}</option>
					{/each}
				</select>
			</div>
			<div class="field">
				<label class="form-label" for="status">Status</label>
				<select
					id="status"
					class="form-input"
					bind:value={status}
					onchange={() => (currentPage = 1)}
				>
					{#each statusOptions as option (option)}
						<option value={option}>{option === 'All' ? 'All statuses' : option}</option>
					{/each}
				</select>
			</div>
			<div class="field">
				<label class="form-label" for="from">From</label>
				<input
					id="from"
					class="form-input"
					type="date"
					bind:value={from}
					onchange={() => (currentPage = 1)}
				/>
			</div>
			<div class="field">
				<label class="form-label" for="to">To</label>
				<input
					id="to"
					class="form-input"
					type="date"
					bind:value={to}
					onchange={() => (currentPage = 1)}
				/>
			</div>
		</div>
		<div class="filter-actions">
			<button
				class="btn btn-ghost"
				type="button"
				aria-expanded={showAdvanced}
				aria-controls="advanced-filters"
				onclick={() => (showAdvanced = !showAdvanced)}
			>
				{showAdvanced ? 'Hide advanced filters' : 'Show advanced filters'}
			</button>
			<button class="btn btn-ghost" type="button" onclick={resetFilters}>Reset filters</button>
		</div>

		{#if showAdvanced}
			<div id="advanced-filters" class="advanced-filters">
				<div class="field">
					<label class="form-label" for="section">Section</label>
					<select
						id="section"
						class="form-input"
						bind:value={section}
						onchange={() => (currentPage = 1)}
					>
						<option value="All">All sections</option>
						{#each [...new Set(directory.map((c) => c.section))].filter((s) => s && s !== '—') as sec (sec)}
							<option value={sec}>{sec}</option>
						{/each}
					</select>
				</div>
				<div class="field">
					<label class="form-label" for="initiated-via">Type</label>
					<select
						id="initiated-via"
						class="form-input"
						bind:value={initiatedVia}
						onchange={() => (currentPage = 1)}
					>
						<option value="All">All types</option>
						<option value="quick">Quick</option>
						<option value="prof_with_evidence">With evidence</option>
						<option value="request">Student request</option>
					</select>
				</div>
				<div class="field">
					<label class="form-label" for="has-evidence">Has evidence</label>
					<select
						id="has-evidence"
						class="form-input"
						bind:value={hasEvidence}
						onchange={() => (currentPage = 1)}
					>
						<option value="All">All</option>
						<option value="yes">With attachments</option>
						<option value="no">Without attachments</option>
					</select>
				</div>
				<div class="field">
					<label class="form-label" for="original-status">Original status</label>
					<select
						id="original-status"
						class="form-input"
						bind:value={originalStatus}
						onchange={() => (currentPage = 1)}
					>
						<option value="All">All</option>
						<option value="absent">Absent</option>
						<option value="late">Late</option>
						<option value="rejected">Rejected</option>
						<option value="unknown">Unknown</option>
					</select>
				</div>
				<div class="field">
					<label class="form-label" for="reviewer">Reviewer</label>
					<input
						id="reviewer"
						class="form-input"
						type="search"
						placeholder="Name or email"
						bind:value={reviewer}
						oninput={() => (currentPage = 1)}
					/>
				</div>
				<div class="field">
					<label class="form-label" for="submitted-from">Submitted from</label>
					<input
						id="submitted-from"
						class="form-input"
						type="date"
						bind:value={submittedFrom}
						onchange={() => (currentPage = 1)}
					/>
				</div>
				<div class="field">
					<label class="form-label" for="submitted-to">Submitted to</label>
					<input
						id="submitted-to"
						class="form-input"
						type="date"
						bind:value={submittedTo}
						onchange={() => (currentPage = 1)}
					/>
				</div>
				<div class="field">
					<label class="form-label" for="reviewed-from">Reviewed from</label>
					<input
						id="reviewed-from"
						class="form-input"
						type="date"
						bind:value={reviewedFrom}
						onchange={() => (currentPage = 1)}
					/>
				</div>
				<div class="field">
					<label class="form-label" for="reviewed-to">Reviewed to</label>
					<input
						id="reviewed-to"
						class="form-input"
						type="date"
						bind:value={reviewedTo}
						onchange={() => (currentPage = 1)}
					/>
				</div>
				<div class="field">
					<label class="form-label" for="sort-by">Sort by</label>
					<select
						id="sort-by"
						class="form-input"
						bind:value={sortBy}
						onchange={() => (currentPage = 1)}
					>
						<option value="requested_at">Newest first</option>
						<option value="reviewed_at">Review date</option>
						<option value="student_name">Student name</option>
						<option value="status">Status</option>
						<option value="id">Request ID</option>
					</select>
				</div>
				<div class="field">
					<label class="form-label" for="sort-dir">Direction</label>
					<select
						id="sort-dir"
						class="form-input"
						bind:value={sortDir}
						onchange={() => (currentPage = 1)}
					>
						<option value="desc">Descending</option>
						<option value="asc">Ascending</option>
					</select>
				</div>
				<div class="field">
					<label class="form-label" for="page-size">Page size</label>
					<select
						id="page-size"
						class="form-input"
						bind:value={pageSize}
						onchange={() => (currentPage = 1)}
					>
						<option value={10}>10</option>
						<option value={25}>25</option>
						<option value={50}>50</option>
					</select>
				</div>
			</div>
		{/if}
	</section>

	{#if hasActiveFilters}
		<div class="filter-chips" aria-label="Active filters">
			{#if status !== 'All'}
				<button class="chip" type="button" onclick={() => { status = 'All'; currentPage = 1; }}>Status: {status} ×</button>
			{/if}
			{#if course !== 'All'}
				<button class="chip" type="button" onclick={() => { course = 'All'; currentPage = 1; }}>Course: {course} ×</button>
			{/if}
			{#if section !== 'All'}
				<button class="chip" type="button" onclick={() => { section = 'All'; currentPage = 1; }}>Section: {section} ×</button>
			{/if}
			{#if initiatedVia !== 'All'}
				<button class="chip" type="button" onclick={() => { initiatedVia = 'All'; currentPage = 1; }}>Type: {initiatedVia} ×</button>
			{/if}
			{#if hasEvidence !== 'All'}
				<button class="chip" type="button" onclick={() => { hasEvidence = 'All'; currentPage = 1; }}>Evidence: {hasEvidence} ×</button>
			{/if}
			{#if originalStatus !== 'All'}
				<button class="chip" type="button" onclick={() => { originalStatus = 'All'; currentPage = 1; }}>Original: {originalStatus} ×</button>
			{/if}
			{#if reviewer}
				<button class="chip" type="button" onclick={() => { reviewer = ''; currentPage = 1; }}>Reviewer: {reviewer} ×</button>
			{/if}
			{#if search}
				<button class="chip" type="button" onclick={() => { searchInput = ''; search = ''; currentPage = 1; }}>Search: {search} ×</button>
			{/if}
			{#if from || to}
				<button class="chip" type="button" onclick={() => { from = ''; to = ''; currentPage = 1; }}>Date: {from || '…'} → {to || '…'} ×</button>
			{/if}
			<button class="chip chip-clear" type="button" onclick={resetFilters}>Clear all ×</button>
		</div>
	{/if}

	{#if loadError}
		<section class="card">
			<p class="error">{loadError}</p>
			<button class="btn btn-secondary" type="button" onclick={() => (reloadToken += 1)}>
				Try again
			</button>
		</section>
	{:else if isLoading && rows.length === 0}
		<SkeletonTable rows={6} cols={6} label="Loading excuse requests…" />
	{:else if rows.length === 0}
		<section class="card">
			<EmptyState icon="file" title="No excuse requests match these filters" hint="Try widening the date range or clearing filters.">
				{#if hasActiveFilters}
					<button class="btn btn-ghost" type="button" onclick={resetFilters}>Clear all filters</button>
				{/if}
			</EmptyState>
		</section>
	{:else}
		<section class="card table-card" aria-label="Excuse requests table">
			<div class="table-wrap" role="region" aria-label="Excuse requests">
				<table>
					<thead>
						<tr>
							<th scope="col">Student</th>
							<th scope="col">Course</th>
							<th scope="col">Session</th>
							<th scope="col">Type</th>
							<th scope="col">Reason</th>
							<th scope="col">Status</th>
							<th scope="col"><span class="sr-only">Action</span></th>
						</tr>
					</thead>
					<tbody>
						{#each rows as row (row.id)}
							<tr>
								<td>
									<div class="student-name">{row.studentName}</div>
									<div class="student-sub">{row.studentNumber} · Section {row.section}</div>
								</td>
								<td>
									<div class="course-name">{row.courseCode}</div>
									<div class="course-sub">{row.courseName}</div>
								</td>
								<td>
									<div class="mono">{row.sessionCode}</div>
									<div class="course-sub">{formatDate(row.sessionDate)}</div>
								</td>
								<td>{typeLabel(row)}</td>
								<td class="reason">{truncated(row.reason)}</td>
								<td>
									<span class="status status-{row.status}">{row.status}</span>
									<div class="status-sub">was {originalLabel(row.originalStatus)}</div>
									{#if row.reviewedByName}
										<div class="status-sub">by {row.reviewedByName}</div>
									{/if}
								</td>
								<td>
									<button
										class="mini"
										type="button"
										onclick={() => openDetail(row)}
										aria-label={`Review excuse ${row.id} for ${row.studentName}`}
									>
										Review
									</button>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			<div class="table-foot">
				<p class="average">{summaryText}</p>
				<div class="no-print">
					<Pagination
						page={currentPage}
						totalPages={pageCount}
						onPageChange={(next) => (currentPage = next)}
						spacing={false}
						ariaLabel="Excuse pages"
					/>
				</div>
			</div>
		</section>
	{/if}
</div>

{#if selected}
	<div class="overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="excuse-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: closeDetail }}
		>
			<h2 id="excuse-title">Excuse #{selected.id} — {selected.studentName}</h2>
			<p class="modal-sub">
				{selected.studentNumber} · {selected.courseCode} · Session {selected.sessionCode} ·
				{formatDate(selected.sessionDate)}
			</p>
			<dl class="detail">
				<div>
					<dt>Type</dt>
					<dd>{typeLabel(selected)} (initiated via {selected.initiatedVia})</dd>
				</div>
				<div>
					<dt>Original status</dt>
					<dd>{originalLabel(selected.originalStatus)} → excused on approve (D22)</dd>
				</div>
				<div>
					<dt>Reason</dt>
					<dd>{selected.reason}</dd>
				</div>
				<div>
					<dt>Evidence</dt>
					<dd>
						{#if selected.attachmentNames.length === 0}
							None attached
						{:else}
							<ul class="files">
								{#each selected.attachmentNames as name (name)}
									<li>
										{#if /^(https?:|mock:|file:|\/)/i.test(name)}
											<a href={name} target="_blank" rel="noopener">{name.split('/').pop() ?? name}</a>
										{:else}
											{name}
										{/if}
									</li>
								{/each}
							</ul>
						{/if}
					</dd>
				</div>
				<div>
					<dt>Status</dt>
					<dd><span class="status status-{selected.status}">{selected.status}</span></dd>
				</div>
				{#if selected.reviewedByName}
					<div>
						<dt>Reviewed by</dt>
						<dd>
							{selected.reviewedByName}
							{#if selected.reviewedAt}
								· {formatDate(selected.reviewedAt)}
							{/if}
						</dd>
					</div>
				{/if}
				{#if selected.reviewNotes}
					<div>
						<dt>Review notes</dt>
						<dd>{selected.reviewNotes}</dd>
					</div>
				{/if}
			</dl>

			{#if selected.status === 'pending'}
				<label class="form-label" for="review-notes">Review notes (required to reject)</label>
				<textarea
					id="review-notes"
					class="form-input area"
					rows={3}
					placeholder="e.g. Legitimate medical reason / Insufficient evidence…"
					bind:value={reviewNotes}
				></textarea>
				{#if reviewError}
					<p class="error">{reviewError}</p>
				{/if}
				<div class="modal-actions">
					<button class="btn btn-ghost" type="button" disabled={reviewBusy} onclick={closeDetail}>
						Close
					</button>
					<button
						class="btn btn-danger"
						type="button"
						disabled={reviewBusy}
						onclick={() => void doReview('rejected')}
					>
						{reviewBusy ? 'Working…' : 'Reject'}
					</button>
					<button
						class="btn btn-primary"
						type="button"
						disabled={reviewBusy}
						onclick={() => void doReview('approved')}
					>
						{reviewBusy ? 'Working…' : 'Approve'}
					</button>
				</div>
			{:else}
				{#if canModify(selected)}
					{#if editMode}
						<label class="form-label" for="edit-reason">Reason (min {EXCUSE_REASON_MIN_LENGTH} chars)</label>
						<textarea
							id="edit-reason"
							class="form-input area"
							rows={3}
							bind:value={editReason}
						></textarea>
						<label class="form-label" for="edit-notes">Review notes</label>
						<textarea
							id="edit-notes"
							class="form-input area"
							rows={2}
							placeholder="Optional context for the change…"
							bind:value={editNotes}
						></textarea>
						{#if editError}
							<p class="error">{editError}</p>
						{/if}
						<div class="modal-actions">
							<button
								class="btn btn-ghost"
								type="button"
								disabled={editBusy}
								onclick={() => {
									editMode = false;
									editReason = selected?.reason ?? '';
									editNotes = selected?.reviewNotes ?? '';
									editError = null;
								}}
							>
								Cancel
							</button>
							<button
								class="btn btn-primary"
								type="button"
								aria-busy={editBusy}
								disabled={editBusy}
								onclick={() => void doEditExcuse()}
							>
								{editBusy ? 'Saving…' : 'Save'}
							</button>
						</div>
					{:else if revokeAsk}
						<p class="modal-sub">
							Revoke this excuse? The attendance record reverts to its original
							status. This cannot be undone from here.
						</p>
						{#if revokeError}
							<p class="error">{revokeError}</p>
						{/if}
						<div class="modal-actions">
							<button
								class="btn btn-ghost"
								type="button"
								disabled={revokeBusy}
								onclick={() => {
									revokeAsk = false;
									revokeError = null;
								}}
							>
								Cancel
							</button>
							<button
								class="btn btn-danger"
								type="button"
								disabled={revokeBusy}
								onclick={() => void doRevokeExcuse()}
							>
								{revokeBusy ? 'Revoking…' : 'Revoke excuse'}
							</button>
						</div>
					{:else}
						{#if revokeError}
							<p class="error">{revokeError}</p>
						{/if}
						<div class="modal-actions">
							<button class="btn btn-ghost" type="button" onclick={closeDetail}>Close</button>
							<button
								class="btn btn-secondary"
								type="button"
								onclick={() => {
									editMode = true;
									editError = null;
								}}
							>
								Edit
							</button>
							<button
								class="btn btn-danger"
								type="button"
								onclick={() => {
									revokeAsk = true;
									revokeError = null;
								}}
							>
								Revoke
							</button>
						</div>
					{/if}
				{:else}
					<div class="modal-actions">
						<button class="btn btn-ghost" type="button" onclick={closeDetail}>Close</button>
					</div>
				{/if}
			{/if}
		</div>
	</div>
{/if}

{#if quickOpen}
	<div class="overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="quick-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: closeQuick }}
		>
			<h2 id="quick-title">New quick-excuse (Path A)</h2>
			<p class="modal-sub">Approves immediately — for direct-knowledge cases. Min {EXCUSE_REASON_MIN_LENGTH}-char reason.</p>
			<div class="quick-grid">
				<div class="field">
					<label class="form-label" for="quick-student-search">Student</label>
					<input
						id="quick-student-search"
						class="form-input"
						type="search"
						placeholder="Search by name or student number"
						bind:value={quickStudentSearch}
						disabled={quickRosterLoading}
					/>
					{#if quickRosterLoading}
						<p class="modal-sub">Loading students…</p>
					{:else if quickRosterError}
						<p class="error">{quickRosterError}</p>
					{:else if quickRoster.length === 0}
						<p class="modal-sub">No students in this offering.</p>
					{:else}
						<select
							id="quick-student"
							class="form-input"
							size={Math.min(6, quickRoster.length)}
							onchange={(e) => {
								const id = Number(e.currentTarget.value);
								quickSelectedStudent =
									quickRoster.find((s) => s.id === id) ?? null;
							}}
						>
							{#each quickRoster.filter((s) => {
								const q = quickStudentSearch.trim().toLowerCase();
								if (!q) return true;
								return (
									s.name.toLowerCase().includes(q) ||
									s.studentId.toLowerCase().includes(q)
								);
							}) as student (student.id ?? student.studentId)}
								<option
									value={student.id}
									selected={quickSelectedStudent?.id === student.id}
								>
									{student.name} · {student.studentId}
									{student.section ? ` · ${student.section}` : ''}
								</option>
							{/each}
						</select>
						{#if quickSelectedStudent}
							<p class="modal-sub">
								Selected: {quickSelectedStudent.name} ({quickSelectedStudent.studentId})
								{quickSelectedStudent.section ? ` · Section ${quickSelectedStudent.section}` : ''}
							</p>
						{/if}
					{/if}
				</div>
				<div class="field">
					<label class="form-label" for="quick-course">Course</label>
					{#if quickEnrolledLoading}
						<p class="modal-sub" role="status">Loading enrolled courses…</p>
					{/if}
					{#if quickEnrolledError}
						<p class="error">{quickEnrolledError}</p>
					{/if}
					<select id="quick-course" class="form-input" bind:value={quickCourse}>
						{#each [...quickEnrolledCourseCodes, ...courseOptions.filter((c) => !quickEnrolledCourseCodes.includes(c))] as option (option)}
							<option value={option}>{option}</option>
						{/each}
					</select>
				</div>
			{#if quickSessions.length > 0}
				<div class="field">
					<label class="form-label" for="quick-session">Session</label>
					<select
						id="quick-session"
						class="form-input"
						bind:value={quickSessionId}
					>
						{#each quickVisibleSessions as session (session.id)}
							<option value={session.id}>#{session.id} · {session.code}</option>
						{/each}
					</select>
				</div>
			{/if}
			<div class="field">
				<label class="form-label" for="quick-original">Original status</label>
					<select id="quick-original" class="form-input" bind:value={quickOriginal}>
						{#each originalOptions as option (option)}
							<option value={option}>{option}</option>
						{/each}
					</select>
				</div>
			</div>
			<label class="form-label" for="quick-reason">Reason (min {EXCUSE_REASON_MIN_LENGTH} chars)</label>
			<textarea
				id="quick-reason"
				class="form-input area"
				rows={3}
				placeholder="e.g. Student informed me after class…"
				bind:value={quickReason}
			></textarea>
			<label class="form-label" for="quick-files">Evidence (optional — with files this files as with-evidence)</label>
			<input
				id="quick-files"
				class="form-input"
				type="file"
				multiple
				accept=".pdf,.jpg,.jpeg,.png,.heic"
				disabled={quickBusy}
				onchange={(e) => onQuickFiles(e.currentTarget.files)}
			/>
			{#if quickFiles.length > 0}
				<ul class="files">
					{#each quickFiles as file, i (file.name + file.size)}
						<li>
							<span>{file.name} · {(file.size / 1024).toFixed(0)} KB</span>
							<button
								class="link-btn"
								type="button"
								disabled={quickBusy}
								onclick={() => (quickFiles = quickFiles.filter((_, j) => j !== i))}
							>
								Remove
							</button>
						</li>
					{/each}
				</ul>
			{/if}
			{#each quickFileErrors as message (message)}
				<p class="error">{message}</p>
			{/each}
			{#if quickStagedUrls.length > 0 && quickFiles.length > 0}
				<p class="modal-sub" role="status">{quickStagedUrls.length} file{quickStagedUrls.length === 1 ? '' : 's'} uploaded — retry the remaining.</p>
			{/if}
			{#if quickUploading}
				<p class="modal-sub" role="status">{quickUploadStatus || 'Uploading evidence…'}</p>
			{/if}
			{#if quickError}
				<p class="error">{quickError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" type="button" disabled={quickBusy} onclick={closeQuick}>
					Cancel
				</button>
				<button
					class="btn btn-primary"
					type="button"
					aria-busy={quickBusy}
					disabled={quickBusy}
					onclick={() => void doQuickExcuse()}
				>
					{quickBusy ? 'Saving…' : 'Excuse now'}
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.excuses {
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
		gap: 1rem;
	}

	.header h1 {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.625rem;
		font-weight: 700;
		color: var(--text);
		margin: 0 0 0.25rem;
	}

	.muted {
		margin: 0;
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	.notice {
		margin: 0;
		padding: 0.75rem 1rem;
		border-radius: 8px;
		background: var(--success-bg);
		border: 1px solid var(--success-bg);
		color: var(--success);
		font-size: 0.875rem;
		font-weight: 600;
	}

	.summary-cards {
		display: grid;
		grid-template-columns: repeat(4, minmax(0, 1fr));
		gap: 1rem;
	}

	.summary-card {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 12px;
		padding: 1rem 1.25rem;
		box-shadow: var(--shadow-sm);
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.summary-label {
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	.summary-value {
		font-size: 1.5rem;
		font-weight: 700;
		color: var(--text);
	}

	@media (max-width: 640px) {
		.summary-cards {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}

	.card {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 12px;
		padding: 1.5rem;
		box-shadow: var(--shadow-sm);
	}

	.empty {
		margin: 0;
		color: var(--text-muted);
		font-size: 0.9375rem;
	}

	.error {
		margin: 0.75rem 0 0;
		color: var(--danger-strong);
		font-weight: 600;
		font-size: 0.875rem;
	}

	.filter-grid {
		display: grid;
		gap: 1rem;
		grid-template-columns: repeat(5, minmax(0, 1fr));
	}

	.advanced-filters {
		display: grid;
		gap: 1rem;
		grid-template-columns: repeat(4, minmax(0, 1fr));
		margin-top: 1rem;
		padding-top: 1rem;
		border-top: 1px solid var(--divider);
	}

	.field {
		display: flex;
		flex-direction: column;
		gap: 0.4375rem;
		min-width: 0;
	}

	.form-label {
		font-size: 0.8125rem;
		font-weight: 600;
		letter-spacing: 0.02em;
		color: var(--text-secondary);
	}

	.area {
		width: 100%;
		resize: vertical;
		margin-top: 0.5rem;
	}

	.filter-actions {
		margin-top: 1rem;
		display: flex;
		justify-content: flex-end;
		gap: 0.5rem;
		flex-wrap: wrap;
	}

	.filter-chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-top: 0.75rem;
	}

	.chip {
		border: 1px solid var(--border-strong);
		background: var(--bg-card);
		color: var(--text-secondary);
		border-radius: 999px;
		padding: 0.25rem 0.625rem;
		font-size: 0.8125rem;
		font-weight: 600;
		cursor: pointer;
	}

	.chip:hover {
		background: var(--bg-hover);
	}

	.chip-clear {
		border-color: var(--danger);
		color: var(--danger-strong);
	}

	.btn-ghost {
		background: var(--bg-card);
		border-color: var(--border-strong);
		color: var(--brand);
	}

	.btn-ghost:hover:not(:disabled) {
		background: var(--bg-hover);
	}

	.table-card {
		padding: 0;
		overflow: hidden;
	}

	.table-wrap {
		overflow-x: auto;
	}

	table {
		width: 100%;
		border-collapse: collapse;
		min-width: 760px;
	}

	th {
		text-align: left;
		padding: 0.75rem 1rem;
		background: var(--bg-page);
		border-bottom: 1px solid var(--border);
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-muted);
	}

	td {
		padding: 0.75rem 1rem;
		border-top: 1px solid var(--divider);
		font-size: 0.9375rem;
		color: var(--text);
		vertical-align: top;
	}

	tbody tr:first-child td {
		border-top: none;
	}

	.student-name,
	.course-name {
		font-weight: 600;
	}

	.student-sub,
	.course-sub,
	.status-sub {
		font-size: 0.8125rem;
		color: var(--text-muted);
	}

	.mono {
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.8125rem;
	}

	.reason {
		max-width: 220px;
	}

	.status {
		display: inline-block;
		padding: 0.125rem 0.625rem;
		border-radius: 999px;
		font-size: 0.8125rem;
		font-weight: 600;
		text-transform: capitalize;
	}

	.status-pending {
		color: var(--warning-text);
		background: var(--warning-bg);
		border: 1px solid var(--warning-bg);
	}

	.status-approved {
		color: var(--success);
		background: var(--success-bg);
		border: 1px solid var(--success-bg);
	}

	.status-rejected {
		color: var(--danger-strong);
		background: var(--danger-bg);
		border: 1px solid var(--danger-bg);
	}

	.mini {
		background: var(--bg-card);
		border: 1px solid var(--border-strong);
		border-radius: 6px;
		padding: 0.375rem 0.75rem;
		font-size: 0.8125rem;
		font-weight: 600;
		font-family: inherit;
		color: var(--brand);
		cursor: pointer;
	}

	.mini:hover {
		background: var(--bg-hover);
	}

	.table-foot {
		display: flex;
		flex-direction: column;
		gap: 1rem;
		padding: 1.25rem 1.5rem;
		border-top: 1px solid var(--divider);
	}

	.average {
		margin: 0;
		font-size: 0.9375rem;
		font-weight: 600;
		color: var(--text-secondary);
	}

	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0, 0, 0, 0);
	}

	.overlay {
		position: fixed;
		inset: 0;
		z-index: 100;
		background: var(--overlay);
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1rem;
	}

	.modal {
		width: 100%;
		max-width: 560px;
		max-height: 90vh;
		overflow-y: auto;
		background: var(--bg-card);
		border-radius: 12px;
		box-shadow: var(--shadow-lg);
		padding: 1.5rem;
	}

	.modal h2 {
		margin: 0 0 0.25rem;
		font-size: 1.125rem;
		color: var(--text);
	}

	.modal-sub {
		margin: 0 0 1rem;
		font-size: 0.875rem;
		color: var(--text-muted);
	}

	.detail {
		margin: 0 0 1rem;
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.detail div {
		display: grid;
		grid-template-columns: 140px 1fr;
		gap: 0.75rem;
	}

	.detail dt {
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-muted);
	}

	.detail dd {
		margin: 0;
		font-size: 0.9375rem;
		color: var(--text);
	}

	.files {
		margin: 0;
		padding-left: 1.25rem;
	}

	.files li {
		margin-bottom: 0.25rem;
	}

	.link-btn {
		border: 0;
		background: none;
		padding: 0;
		margin-left: 0.5rem;
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
		gap: 0.75rem;
		justify-content: flex-end;
		margin-top: 1rem;
		flex-wrap: wrap;
	}

	.quick-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 1rem;
		margin-bottom: 1rem;
	}

	@media (max-width: 900px) {
		.filter-grid {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}

	@media (max-width: 640px) {
		.header {
			flex-direction: column;
		}

		.filter-grid,
		.quick-grid {
			grid-template-columns: 1fr;
		}

		.detail div {
			grid-template-columns: 1fr;
		}
	}
</style>
