<script lang="ts">
	import EmptyState from '$lib/components/EmptyState.svelte';
	import Pagination from '$lib/components/Pagination.svelte';
	import SkeletonTable from '$lib/components/SkeletonTable.svelte';
	import SkeletonCards from '$lib/components/SkeletonCards.svelte';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import ConfirmExportDialog from '$lib/components/ConfirmExportDialog.svelte';
	import {
		listRecords,
		type AttendanceLedgerSortBy,
		type AttendanceLedgerSortDir,
		type ProfessorAttendanceStatus
	} from '$lib/features/attendance/service';
	import {
		initProfessorCourses,
		professorState
	} from '$lib/features/professor/store.svelte';
	import {
		buildCsv,
		defaultReportRange
	} from '$lib/features/report/service';
	import { professorActiveSession } from '$lib/shared/constants/routes';
	import { formatDate, formatTime } from '$lib/shared/utils/format';
	import { downloadTextFile } from '$lib/shared/utils/file';
	import { debounce } from '$lib/shared/utils/debounce';

	type LedgerRow = Awaited<ReturnType<typeof listRecords>>['items'][number];

	const PAGE_SIZE = 10;
	const EXPORT_PAGE_SIZE = 100;
	const EXPORT_MAX_PAGES = 100;
	const EXPORT_MAX_ROWS = EXPORT_PAGE_SIZE * EXPORT_MAX_PAGES;

	const initialRange = defaultReportRange();

	onMount(() => {
		initProfessorCourses();
	});

	const statusOptions: Array<'All' | ProfessorAttendanceStatus> = [
		'All',
		'present',
		'late',
		'absent',
		'excused',
		'pending',
		'rejected'
	];

	// Filters
	let academicYear = $state('');
	let semester = $state('');
	let programFilter = $state('');
	let yearFilter = $state('');
	let section = $state('');
	let course = $state('');
	let classOfferingId = $state('');
	let status = $state<'All' | ProfessorAttendanceStatus>('All');
	let sessionType = $state<'All' | 'lecture' | 'lab'>('All');
	let searchInput = $state('');
	let search = $state('');
	let from = $state(initialRange.from);
	let to = $state(initialRange.to);
	let sortBy = $state<AttendanceLedgerSortBy>('date');
	let sortDir = $state<AttendanceLedgerSortDir>('desc');
	let currentPage = $state(1);
	let rows = $state<LedgerRow[]>([]);
	let total = $state(0);
	let totalStudents = $state(0);
	let totalSessions = $state(0);
	let counts = $state({ present: 0, late: 0, absent: 0, excused: 0, pending: 0, rejected: 0 });
	let isLoading = $state(true);
	let loadError = $state<string | null>(null);
	let reloadToken = $state(0);
	let exporting = $state(false);
	let exportError = $state<string | null>(null);
	let exportWarning = $state<string | null>(null);
	let exportProgress = $state<string | null>(null);
	let exportCapped = $state(false);
	let exportToken = $state(0);
	let pendingExport = $state<null | {
		run: () => void | Promise<void>;
		details?: { label: string; value: string }[];
		title?: string;
		message?: string;
		confirmLabel?: string;
		busyLabel?: string;
		onabort?: () => void;
	}>(null);
	let directoryIncomplete = $state(false);
	let missingCount = $state(0);
	let syncingFromOffering = $state(false);
	let loadingFromUrl = $state(false);
	let showAdvanced = $state(false);

	// Debounce search
	const searchDebounced = debounce((value: string) => {
		search = value.trim();
		currentPage = 1;
	});

	$effect(() => {
		searchDebounced(searchInput);
		return () => searchDebounced.cancel();
	});

	const byAcademicYear = $derived(
		professorState.courses.filter((item) => (academicYear ? item.academicYear === academicYear : true))
	);
	const bySemester = $derived(
		byAcademicYear.filter((item) => (semester ? item.semester === semester : true))
	);
	const byProgram = $derived(
		bySemester.filter((item) => (programFilter ? String(item.programId) === programFilter : true))
	);
	const byYear = $derived(
		byProgram.filter((item) => (yearFilter ? String(item.yearLevelId) === yearFilter : true))
	);
	const bySection = $derived(
		byYear.filter((item) => (section ? item.sections.includes(section) : true))
	);
	const higherFilteredCourses = $derived(byYear);
	const baseFilteredCourses = $derived(bySection);
	const filteredCourses = $derived(
		baseFilteredCourses.filter((item) => (course ? item.courseCode === course : true))
	);

	const academicYearOptions = $derived(
		[...new Set(professorState.courses.map((item) => item.academicYear))].sort()
	);
	const semesterOptions = $derived(
		[...new Set(byAcademicYear.map((item) => item.semester))].sort()
	);
	const programOptions = $derived(
		[...new Map(bySemester.map((item) => [String(item.programId), item.programCode])).entries()]
			.map(([id, code]) => ({ id, code }))
			.filter((item) => item.id !== 'undefined')
	);
	const yearOptions = $derived(
		[...new Map(
			byProgram.map((item) => [String(item.yearLevelId), item.yearLevelLabel])
		).entries()]
			.map(([id, label]) => ({ id, label }))
			.filter((item) => item.id !== 'undefined')
	);
	const sectionOptions = $derived(
		[...new Set(byYear.flatMap((item) => item.sections))].sort()
	);
	const courseOptions = $derived(
		[...new Map(bySection.map((item) => [item.courseCode, item.courseName])).entries()].map(
			([code, name]) => ({ code, name })
		)
	);
	const classOptions = $derived.by(() => {
		const base = professorState.courses.map((item) => ({
			id: item.offeringId,
			label: `${item.programCode} · ${item.yearLevelLabel} · ${item.courseCode} — ${item.courseName}${item.sections.length ? ` (${item.sections.join(', ')})` : ''}`
		}));
		const selectedId = classOfferingId ? Number(classOfferingId) : null;
		if (selectedId && !base.some((option) => option.id === selectedId)) {
			const item = professorState.courses.find((course) => course.offeringId === selectedId);
			if (item) {
				base.unshift({
					id: item.offeringId,
					label: `${item.programCode} · ${item.yearLevelLabel} · ${item.courseCode} — ${item.courseName}${item.sections.length ? ` (${item.sections.join(', ')})` : ''}`
				});
			}
		}
		return base;
	});

	$effect(() => {
		if (availableSessionTypes.size === 1) {
			const only = [...availableSessionTypes][0] as 'lecture' | 'lab';
			if (sessionType === 'All' || !availableSessionTypes.has(sessionType)) {
				sessionType = only;
			}
		} else if (sessionType !== 'All' && !availableSessionTypes.has(sessionType)) {
			sessionType = 'All';
		}
	});

	const availableSessionTypes = $derived.by(() => {
		const source =
			classOfferingId
				? professorState.courses.filter((item) => item.offeringId === Number(classOfferingId))
				: filteredCourses;
		const types = new Set<string>();
		for (const item of source) {
			for (const type of item.sessionTypes ?? []) types.add(type);
			for (const component of item.components ?? []) types.add(component.session_type);
		}
		// Fallback: if metadata missing, mirror backend (lecture only).
		if (types.size === 0) {
			types.add('lecture');
		}
		return types;
	});

	// Clear selections that become invalid after a parent change.
	$effect(() => {
		if (programFilter && !programOptions.some((o) => o.id === programFilter)) programFilter = '';
	});
	$effect(() => {
		if (yearFilter && !yearOptions.some((o) => o.id === yearFilter)) yearFilter = '';
	});
	$effect(() => {
		if (section && !sectionOptions.includes(section)) section = '';
	});
	$effect(() => {
		if (course && !courseOptions.some((item) => item.code === course)) course = '';
	});

	const selectedOffering = $derived(
		classOfferingId
			? professorState.courses.find((item) => item.offeringId === Number(classOfferingId)) ?? null
			: course
				? (filteredCourses[0] ?? null)
				: null
	);

	const canQuery = $derived(true);

	$effect(() => {
		const query = {
			programId: programFilter ? Number(programFilter) : undefined,
			yearLevelId: yearFilter ? Number(yearFilter) : undefined,
			academicYear: academicYear || undefined,
			semester: semester || undefined,
			course: course || undefined,
			section: section || undefined,
			offeringId: classOfferingId ? Number(classOfferingId) : undefined,
			status: status === 'All' ? undefined : status,
			sessionType: sessionType === 'All' ? undefined : sessionType,
			search: search || undefined,
			from: from || undefined,
			to: to || undefined,
			sortBy,
			sortDir,
			page: currentPage,
			size: PAGE_SIZE
		};
		// Note: program/year level filters are applied through the class selector;
		// backend program_id/year_level_id are not resolved from labels here.
		reloadToken;

		let cancelled = false;
		isLoading = true;
		loadError = null;

		const load = async () => {
			try {
				const result = await listRecords(query);
				if (cancelled) return;
				rows = result.items;
				total = result.total;
				totalStudents = result.total_students ?? 0;
				totalSessions = result.total_sessions;
				counts = result.counts;
				directoryIncomplete = result.directoryIncomplete;
				missingCount = result.missingCount;
				if (result.page !== currentPage) currentPage = result.page;
			} catch (e) {
				if (!cancelled)
					loadError =
						e instanceof Error && e.message
							? `Attendance records could not be loaded: ${e.message}`
							: 'Attendance records could not be loaded.';
			} finally {
				if (!cancelled) isLoading = false;
			}
		};

		void load();
		return () => {
			cancelled = true;
		};
	});

	const pageCount = $derived(Math.max(1, Math.ceil(total / PAGE_SIZE)));
	const rangeText = $derived.by(() => {
		if (total === 0) return '0 of 0 records';
		const start = (currentPage - 1) * PAGE_SIZE + 1;
		const end = Math.min(currentPage * PAGE_SIZE, total);
		return `${start}–${end} of ${total} records`;
	});

	const attendanceRate = $derived(
		total > 0 ? Math.round((counts.present / total) * 1000) / 10 : 0
	);

	const summaryText = $derived(
		`This page: Present ${counts.present} · Late ${counts.late} · Excused ${counts.excused} · Absent ${counts.absent} across ${totalSessions} ${totalSessions === 1 ? 'session' : 'sessions'}`
	);

	const directoryWarning = $derived(
		directoryIncomplete
			? `${missingCount} ${missingCount === 1 ? 'row shows' : 'rows show'} scanned time because ${missingCount === 1 ? 'its' : 'their'} session is outside the warmed window — narrow the date range for exact session dates.`
			: null
	);

	const setSort = (key: AttendanceLedgerSortBy) => {
		if (sortBy === key) sortDir = sortDir === 'asc' ? 'desc' : 'asc';
		else {
			sortBy = key;
			sortDir = key === 'date' ? 'desc' : 'asc';
		}
		currentPage = 1;
	};

	const sortArrow = (key: AttendanceLedgerSortBy): string => {
		if (sortBy !== key) return '↕';
		return sortDir === 'asc' ? '▲' : '▼';
	};

	const sortLabel = (key: AttendanceLedgerSortBy, label: string): string => {
		if (sortBy !== key) return `Sort by ${label.toLowerCase()} ascending`;
		return `Sort by ${label.toLowerCase()} ${sortDir === 'asc' ? 'descending' : 'ascending'}`;
	};

	const ariaSort = (key: AttendanceLedgerSortBy): 'ascending' | 'descending' | 'none' => {
		if (sortBy !== key) return 'none';
		return sortDir === 'asc' ? 'ascending' : 'descending';
	};

	const resetFilters = () => {
		academicYear = '';
		semester = '';
		programFilter = '';
		yearFilter = '';
		section = '';
		course = '';
		classOfferingId = '';
		status = 'All';
		sessionType = 'All';
		searchInput = '';
		search = '';
		from = initialRange.from;
		to = initialRange.to;
		currentPage = 1;
		exportWarning = null;
		exportProgress = null;
		exportCapped = false;
	};

	const toLocalIsoDate = (value: Date): string =>
		`${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`;

	const setToday = () => {
		const today = toLocalIsoDate(new Date());
		from = today;
		to = today;
		currentPage = 1;
	};

	const setYesterday = () => {
		const date = new Date();
		date.setDate(date.getDate() - 1);
		const value = toLocalIsoDate(date);
		from = value;
		to = value;
		currentPage = 1;
	};

	const setThisWeek = () => {
		const now = new Date();
		const day = now.getDay();
		const diff = day === 0 ? 6 : day - 1;
		const monday = new Date(now);
		monday.setDate(now.getDate() - diff);
		from = toLocalIsoDate(monday);
		to = toLocalIsoDate(now);
		currentPage = 1;
	};

	const setAllTime = () => {
		from = '';
		to = '';
		currentPage = 1;
	};

	const viewDetail = (sessionId: number) => void goto(professorActiveSession(sessionId));

	const scannedText = (row: LedgerRow): string =>
		row.scanned_at ? formatTime(row.scanned_at) : '—';

	const scannedSub = (row: LedgerRow): string | null => {
		if (!row.scanned_at) return null;
		const via = row.scanned_via ? row.scanned_via.toUpperCase() : null;
		const score =
			row.face_match_score === undefined ? null : `${Math.round(row.face_match_score)}%`;
		return [via, score].filter(Boolean).join(' · ') || null;
	};

	const excuseSub = (row: LedgerRow): string | null => {
		if (row.status !== 'excused') return null;
		const was = row.original_status ? `was ${row.original_status}` : null;
		return [row.excuse_reason, was].filter(Boolean).join(' · ') || null;
	};

	const exportCsv = async () => {
		if (exporting) return;
		const token = exportToken + 1;
		exportToken = token;
		exporting = true;
		exportError = null;
		exportWarning = null;
		exportCapped = false;
		exportProgress = 'Starting export…';
		try {
			const baseQuery = {
				academicYear: academicYear || undefined,
				semester: semester || undefined,
				course: course || undefined,
				section: section || undefined,
				offeringId: classOfferingId ? Number(classOfferingId) : undefined,
				status: status === 'All' ? undefined : status,
				sessionType: sessionType === 'All' ? undefined : sessionType,
				search: search || undefined,
				from: from || undefined,
				to: to || undefined,
				sortBy,
				sortDir
			};
			const first = await listRecords({ ...baseQuery, page: 1, size: EXPORT_PAGE_SIZE });
			if (exportToken !== token) return;
			const all = [...first.items];
			let unknownRows = first.missingCount;
			const totalPages = Math.max(1, Math.ceil(first.total / EXPORT_PAGE_SIZE));
			const cappedPages = Math.min(totalPages, EXPORT_MAX_PAGES);
			exportProgress = `Exporting page 1 of ~${totalPages}…`;
			for (let page = 2; page <= cappedPages; page += 1) {
				if (exportToken !== token) return;
				exportProgress = `Exporting page ${page} of ~${totalPages}…`;
				const next = await listRecords({ ...baseQuery, page, size: EXPORT_PAGE_SIZE });
				if (exportToken !== token) return;
				all.push(...next.items);
				unknownRows += next.missingCount;
				if (all.length >= EXPORT_MAX_ROWS) break;
			}
			if (exportToken !== token) return;
			exportCapped = totalPages > EXPORT_MAX_PAGES;
			const warnings: string[] = [];
			if (exportCapped)
				warnings.push(
					`Export capped at ${EXPORT_MAX_ROWS.toLocaleString()} rows — narrow the date range for the full set.`
				);
			if (unknownRows > 0)
				warnings.push(
					`${unknownRows} ${unknownRows === 1 ? 'row uses' : 'rows use'} scanned time because ${unknownRows === 1 ? 'its' : 'their'} session is outside the warmed window.`
				);
			exportWarning = warnings.length > 0 ? warnings.join(' ') : null;
			exportProgress = null;
			const csv = buildCsv(
				[
					'Date',
					'Session code',
					'Type',
					'Course',
					'Section',
					'Student number',
					'Student name',
					'Status',
					'Original status',
					'Scanned at',
					'Via',
					'Face score',
					'Excuse reason'
				],
				all.map((row) => [
					row.created_at.slice(0, 10),
					row.session_code,
					row.session_type,
					row.course_code,
					row.section,
					row.student_number,
					row.student_name,
					row.status,
					row.original_status ?? '',
					row.scanned_at ?? '',
					row.scanned_via ?? '',
					row.face_match_score ?? '',
					row.excuse_reason ?? ''
				])
			);
			downloadTextFile(csv, `attendance-${to || initialRange.to}.csv`);
		} catch (e: unknown) {
			if (exportToken === token)
				exportError = e instanceof Error && e.message ? e.message : 'Export failed. Please try again.';
		} finally {
			if (exportToken === token || exportToken === token + 1) {
				exporting = false;
				exportProgress = null;
			}
		}
	};

	const cancelExport = () => {
		exportToken += 1;
	};

	const print = () => window.print();
</script>

<div class="attendance">
	<header class="header">
		<div>
			<h1>Attendance</h1>
			<p class="muted">Cross-session roster across your classes · {rangeText}</p>
			<p class="muted">Read-only ledger — excuse actions live on the session page.</p>
		</div>
	</header>

	{#if professorState.courses.length === 0 && !professorState.coursesLoading}
		<section class="card">
			<EmptyState
				icon="file"
				title="No course assignments"
				hint="You have no assigned classes yet. Contact your administrator."
			/>
		</section>
	{:else}
	<section class="summary-cards" aria-label="Attendance summary">
		<div class="stat-card">
			<span class="stat-label">Total students</span>
			<span class="stat-value">{totalStudents}</span>
		</div>
		<div class="stat-card">
			<span class="stat-label">Present</span>
			<span class="stat-value">{counts.present}</span>
		</div>
		<div class="stat-card">
			<span class="stat-label">Late</span>
			<span class="stat-value">{counts.late}</span>
		</div>
		<div class="stat-card">
			<span class="stat-label">Absent</span>
			<span class="stat-value">{counts.absent}</span>
		</div>
		<div class="stat-card">
			<span class="stat-label">Excused</span>
			<span class="stat-value">{counts.excused}</span>
		</div>
		<div class="stat-card">
			<span class="stat-label">Attendance rate</span>
			<span class="stat-value">{attendanceRate}%</span>
		</div>
	</section>

	<section class="card filters no-print" aria-label="Attendance filters">
		<div class="filter-grid refine">
			<div class="field">
				<label class="form-label" for="class">Class</label>
				<select
	id="class"
	class="form-input"
	bind:value={classOfferingId}
	onchange={() => {
		const item = professorState.courses.find((course) => course.offeringId === Number(classOfferingId));
		if (!item) return;
		academicYear = item.academicYear;
		semester = item.semester;
		programFilter = String(item.programId ?? '');
		yearFilter = String(item.yearLevelId ?? '');
		section = item.sections[0] ?? '';
		course = item.courseCode;
	}}
>
					<option value="">All classes</option>
					{#each classOptions as option (option.id)}
						<option value={option.id}>{option.label}</option>
					{/each}
				</select>
			</div>
			<div class="field">
				<label class="form-label" for="status">Status</label>
				<select id="status" class="form-input" bind:value={status} onchange={() => (currentPage = 1)}>
					{#each statusOptions as option (option)}
						<option value={option}>{option === 'All' ? 'All statuses' : option}</option>
					{/each}
				</select>
			</div>
			<div class="field">
				<label class="form-label" for="search">Search student</label>
				<input id="search" class="form-input" type="search" bind:value={searchInput} placeholder="Name or student number" />
			</div>
			<div class="field">
				<label class="form-label" for="from">From</label>
				<input id="from" class="form-input" type="date" bind:value={from} onchange={() => (currentPage = 1)} />
			</div>
			<div class="field">
				<label class="form-label" for="to">To</label>
				<input id="to" class="form-input" type="date" bind:value={to} onchange={() => (currentPage = 1)} />
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
			<button class="btn btn-ghost" type="button" onclick={setToday}>Today</button>
			<button class="btn btn-ghost" type="button" onclick={setYesterday}>Yesterday</button>
			<button class="btn btn-ghost" type="button" onclick={setThisWeek}>This week</button>
			<button class="btn btn-ghost" type="button" onclick={setAllTime}>All time</button>
			<button class="btn btn-ghost" type="button" onclick={resetFilters}>Reset filters</button>
		</div>

		{#if showAdvanced}
			<div id="advanced-filters" class="filter-grid wide advanced-filters">
				<div class="field">
					<label class="form-label" for="academic-year">Academic year</label>
					<select id="academic-year" class="form-input" bind:value={academicYear} onchange={() => { semester = ""; programFilter = ""; yearFilter = ""; section = ""; course = ""; classOfferingId = ""; currentPage = 1; }}>
						<option value="">All</option>
						{#each academicYearOptions as option (option)}
							<option value={option}>{option}</option>
						{/each}
					</select>
				</div>
				<div class="field">
					<label class="form-label" for="semester">Semester</label>
					<select id="semester" class="form-input" bind:value={semester} onchange={() => { programFilter = ""; yearFilter = ""; section = ""; course = ""; classOfferingId = ""; currentPage = 1; }}>
						<option value="">All</option>
						{#each semesterOptions as option (option)}
							<option value={option}>{option}</option>
						{/each}
					</select>
				</div>
				<div class="field">
					<label class="form-label" for="program">Program</label>
					<select id="program" class="form-input" bind:value={programFilter} onchange={() => { yearFilter = ""; section = ""; course = ""; classOfferingId = ""; currentPage = 1; }} disabled={!!classOfferingId}>
						<option value="">All</option>
						{#each programOptions as option (option.id)}
							<option value={option.id}>{option.code}</option>
						{/each}
					</select>
				</div>
				<div class="field">
					<label class="form-label" for="year-level">Year level</label>
					<select id="year-level" class="form-input" bind:value={yearFilter} onchange={() => { section = ""; course = ""; classOfferingId = ""; currentPage = 1; }} disabled={!!classOfferingId}>
						<option value="">All</option>
						{#each yearOptions as option (option.id)}
							<option value={option.id}>{option.label}</option>
						{/each}
					</select>
				</div>
				<div class="field">
					<label class="form-label" for="section">Section</label>
					<select id="section" class="form-input" bind:value={section} onchange={() => { course = ""; classOfferingId = ""; currentPage = 1; }} disabled={!!classOfferingId}>
						<option value="">All</option>
						{#each sectionOptions as option (option)}
							<option value={option}>{option}</option>
						{/each}
					</select>
				</div>
				<div class="field">
					<label class="form-label" for="course">Course</label>
					<select id="course" class="form-input" bind:value={course} onchange={() => { classOfferingId = ""; currentPage = 1; }} disabled={!!classOfferingId}>
						<option value="">All</option>
						{#each courseOptions as option (option.code)}
							<option value={option.code}>{option.code} — {option.name}</option>
						{/each}
					</select>
				</div>
				<div class="field">
					<label class="form-label" for="session-type">Type</label>
					<select id="session-type" class="form-input" bind:value={sessionType} onchange={() => (currentPage = 1)}>
						{#if availableSessionTypes.size > 1}
							<option value="All">All types</option>
						{/if}
						{#if availableSessionTypes.has('lecture')}
							<option value="lecture">Lecture</option>
						{/if}
						{#if availableSessionTypes.has('lab')}
							<option value="lab">Laboratory</option>
						{/if}
					</select>
				</div>
			</div>
		{/if}
	</section>

	{#if loadError}
		<section class="card">
			<p class="error">{loadError}</p>
			<button class="btn btn-secondary" type="button" onclick={() => (reloadToken += 1)}>
				Try again
			</button>
		</section>
	{:else if isLoading && rows.length === 0}
		<SkeletonCards count={6} label="Loading attendance summary…" />
		<SkeletonTable rows={8} cols={6} label="Loading attendance records…" />
	{:else if rows.length === 0}
		<section class="card">
			<EmptyState
				icon="file"
				title="No attendance records match these filters"
				hint="Try widening the date range or clearing filters."
			/>
		</section>
	{:else}
		<section class="card table-card" aria-label="Attendance ledger table">
			<div class="table-wrap" role="region" aria-label="Attendance ledger">
				<table>
					<thead>
						<tr>
							<th scope="col" aria-sort={ariaSort('date')}>
								<button class="sort" type="button" onclick={() => setSort('date')} aria-label={sortLabel('date', 'Date')}>
									<span>Date</span>
									<span class="sort-arrow" class:active={sortBy === 'date'} aria-hidden="true">{sortArrow('date')}</span>
								</button>
							</th>
							<th scope="col" aria-sort={ariaSort('student')}>
								<button class="sort" type="button" onclick={() => setSort('student')} aria-label={sortLabel('student', 'Student')}>
									<span>Student</span>
									<span class="sort-arrow" class:active={sortBy === 'student'} aria-hidden="true">{sortArrow('student')}</span>
								</button>
							</th>
							<th scope="col" aria-sort={ariaSort('section')}>
								<button class="sort" type="button" onclick={() => setSort('section')} aria-label={sortLabel('section', 'Course')}>
									<span>Course</span>
									<span class="sort-arrow" class:active={sortBy === 'section'} aria-hidden="true">{sortArrow('section')}</span>
								</button>
							</th>
							<th scope="col">Session</th>
							<th scope="col">Type</th>
							<th scope="col" aria-sort={ariaSort('status')}>
								<button class="sort" type="button" onclick={() => setSort('status')} aria-label={sortLabel('status', 'Status')}>
									<span>Status</span>
									<span class="sort-arrow" class:active={sortBy === 'status'} aria-hidden="true">{sortArrow('status')}</span>
								</button>
							</th>
							<th scope="col" aria-sort={ariaSort('time')}>
								<button class="sort" type="button" onclick={() => setSort('time')} aria-label={sortLabel('time', 'Time')}>
									<span>Scanned</span>
									<span class="sort-arrow" class:active={sortBy === 'time'} aria-hidden="true">{sortArrow('time')}</span>
								</button>
							</th>
							<th scope="col"><span class="sr-only">Action</span></th>
						</tr>
					</thead>
					<tbody>
						{#each rows as row (row.id)}
							<tr>
								<td>{formatDate(row.created_at)}</td>
								<td>
									<div class="student-name">{row.student_name}</div>
									<div class="student-sub">{row.student_number} · Section {row.section}</div>
								</td>
								<td>
									<div class="course-name">{row.course_code}</div>
									<div class="course-sub">{row.course_name}</div>
								</td>
								<td class="mono">{row.session_code}</td>
								<td>
									<span class="type-badge" class:is-lab={row.session_type === 'lab'}>
										{row.session_type === 'lab' ? 'Lab' : 'Lecture'}
									</span>
								</td>
								<td>
									<span class="status status-{row.status}">{row.status}</span>
									{#if excuseSub(row)}
										<div class="status-sub">{excuseSub(row)}</div>
									{/if}
								</td>
								<td>
									<div class="numeric">{scannedText(row)}</div>
									{#if scannedSub(row)}
										<div class="course-sub">{scannedSub(row)}</div>
									{/if}
								</td>
								<td>
									<button class="mini" type="button" onclick={() => viewDetail(row.session_id)} aria-label={`View session ${row.session_code} for ${row.student_name}`}>
										View
									</button>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			<div class="table-foot">
				<p class="average">{summaryText}</p>
				{#if directoryWarning}
					<p class="warning" role="status">{directoryWarning}</p>
				{/if}
				<div class="no-print">
					<Pagination
						page={currentPage}
						totalPages={pageCount}
						onPageChange={(next) => (currentPage = next)}
						spacing={false}
						ariaLabel="Attendance pages"
					/>
				</div>
				<div class="table-actions no-print">
					<button class="btn btn-secondary" type="button" onclick={() => (pendingExport = { run: print, title: 'Confirm Print', message: 'Are you sure you want to print this data? Your browser’s print dialog will open after you confirm.', confirmLabel: 'Confirm Print', details: [{ label: 'Format', value: 'Print' }] })}>
						<AppIcon name="file" size={18} />
						Print
					</button>
					<button class="btn btn-secondary" type="button" disabled={exporting || total === 0} onclick={() => (pendingExport = { run: exportCsv, details: [{ label: 'Format', value: 'CSV' }, { label: 'Rows', value: total ? String(total) : '0' }], onabort: cancelExport })}>
						<AppIcon name="file" size={18} />
						{exporting ? 'Exporting…' : 'Export CSV'}
					</button>
					{#if exporting}
						<button class="btn btn-ghost" type="button" onclick={cancelExport}>
							Cancel
						</button>
					{/if}
				</div>
				{#if exportProgress}
					<p class="muted" role="status" aria-live="polite">{exportProgress}</p>
				{/if}
				{#if exportWarning}
					<p class="warning" role="status">{exportWarning}</p>
				{/if}
				{#if exportError}
					<p class="error" role="alert">{exportError}</p>
				{/if}
			</div>
		</section>
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
			onabort={pendingExport.onabort}
			onclose={() => (pendingExport = null)}
		/>
	{/if}
</div>

<style>
	.attendance {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
		max-width: 1400px;
		margin: 0 auto;
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

	.card {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 12px;
		padding: 1.5rem;
		box-shadow: var(--shadow-sm);
	}

	.error {
		margin: 0 0 1rem;
		color: var(--danger-strong);
		font-weight: 600;
	}

	.warning {
		margin: 0;
		color: var(--warning-text);
		font-size: 0.875rem;
		font-weight: 600;
	}

	.summary-cards {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
		gap: 1rem;
	}

	.stat-card {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 12px;
		padding: 1rem 1.25rem;
		box-shadow: var(--shadow-sm);
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.stat-label {
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--text-muted);
		font-weight: 600;
	}

	.stat-value {
		font-size: 1.5rem;
		font-weight: 700;
		color: var(--text-strong);
	}

	.filter-grid {
		display: grid;
		gap: 1rem;
	}

	.wide {
		grid-template-columns: repeat(3, minmax(0, 1fr));
	}

	.refine {
		grid-template-columns: repeat(3, minmax(0, 1fr));
		margin-top: 1rem;
	}

	.advanced-filters {
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

	.filter-actions {
		display: flex;
		justify-content: flex-end;
		margin-top: 1rem;
	}

	.table-card {
		padding: 0;
		overflow: hidden;
	}

	.table-wrap {
		overflow: auto;
	}

	table {
		width: 100%;
		min-width: 760px;
		border-collapse: collapse;
		font-size: 0.9375rem;
	}

	th,
	td {
		padding: 0.75rem 1rem;
		text-align: left;
		border-bottom: 1px solid var(--divider);
		vertical-align: middle;
		color: var(--text-strong);
	}

	thead th {
		background: var(--bg-page);
		font-size: 0.75rem;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--text-muted);
	}

	tbody tr:last-child td {
		border-bottom: none;
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

	.sort:focus-visible,
	.mini:focus-visible {
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

	.mono {
		font-family: 'JetBrains Mono', monospace;
		font-weight: 600;
		letter-spacing: 0.06em;
	}

	.numeric {
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
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
	.status-rejected { background: var(--danger-bg); color: var(--danger-strong); }

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

	.table-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
	}

	.btn-ghost {
		background: var(--bg-card);
		border-color: var(--border-strong);
		color: var(--text-strong);
		padding: 0.5rem 0.9rem;
		font-size: 0.875rem;
	}

	.btn:disabled {
		/* Shared .btn:disabled adds opacity; keep the grey state solid. */
		opacity: 1;
		background: var(--bg-page);
		border-color: var(--border);
		color: var(--text-muted);
		cursor: not-allowed;
	}

	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
		white-space: nowrap;
	}

	@media (max-width: 860px) {
		.filter-grid {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
		.wide {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}

	@media (max-width: 560px) {
		.filter-grid {
			grid-template-columns: minmax(0, 1fr);
		}
		.wide {
			grid-template-columns: minmax(0, 1fr);
		}
		.refine {
			grid-template-columns: minmax(0, 1fr);
		}
		.table-actions .btn {
			flex: 1 1 auto;
		}
	}

	@media print {
		.no-print {
			display: none;
		}

		.attendance {
			max-width: none;
		}

		.card {
			box-shadow: none;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.btn,
		.mini {
			transition: none;
		}
	}
</style>