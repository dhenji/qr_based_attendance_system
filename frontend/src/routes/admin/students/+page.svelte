<script lang="ts">
	import EmptyState from '$lib/components/EmptyState.svelte';
	import Skeleton from '$lib/components/Skeleton.svelte';
	import SkeletonTable from '$lib/components/SkeletonTable.svelte';
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import TempPasswordModal from '$lib/components/TempPasswordModal.svelte';
	import FaceEnrollmentCamera from '$lib/features/admin/enrollment/FaceEnrollmentCamera.svelte';
	import { validateFacePhoto } from '$lib/features/admin/enrollment/quality';
	import {
		adminStudentsState,
		deleteArchivedStudent,
		initAdminStudents,
		refreshAdminStudents,
		toggleStudentActive,
	} from '$lib/features/admin/store.svelte';
	import {
		createStudent,
		getFaceEnrollmentStatus,
		resetStudentPassword,
		revokeFaceEnrollment,
		updateStudent,
		uploadFaceEnrollment,
		type FaceEnrollmentStatus,
	} from '$lib/features/admin/service';
	import {
		adminStudentCreateSchema,
		adminStudentUpdateSchema,
		facePhotoSchema,
	} from '$lib/features/admin/schema';
	import { APIError } from '$lib/api/client';
	import type { AdminStudent, Program, YearLevel } from '$lib/shared/types';
	import { listPrograms, listYearLevels } from '$lib/features/admin/programs/service';
	import { notifyEntityChanged, subscribeEntity } from '$lib/shared/utils/entityEvents';
	import { onFocusRevalidate } from '$lib/shared/utils/revalidateOnFocus';
	import { Routes, adminStudent } from '$lib/shared/constants/routes';
	import { trapFocus } from '$lib/shared/actions/focusTrap';
	import { initFaceModel } from '$lib/features/liveness/model';
	import { friendlyActionError } from '$lib/shared/utils/deleteErrors';

	// Student Management (wireframe 4.2): search + sortable table + pagination
	// over GET /admin/students. Active roster only; deactivated rows live in the
	// Archive. Deactivate flips is_active (soft); permanent delete is only
	// offered on inactive rows and goes to DELETE /{id}/archive with its
	// 409 has-records guard.

	let search = $state('');
	let sectionFilter = $state('');
	let programFilter = $state('');
	// Year filter is label-based (1st-6th Year) so it works with AND without
	// a program picked: year_level_ids are per-program, so with no program
	// there is no single id to send and the label narrows the page locally.
	let yearLabel = $state('');
	const YEAR_LABELS = ['1st Year', '2nd Year', '3rd Year', '4th Year', '5th Year', '6th Year'];
	let programOptions = $state<Program[]>([]);
	let yearOptions = $state<YearLevel[]>([]);
	let sortBy = $state<
		'last_name' | 'student_id' | 'program_code' | 'section' | 'year_level_label'
	>('last_name');
	let sortDir = $state<'asc' | 'desc'>('asc');

	// Columns the backend list endpoint cannot sort (its sort_by Literal only
	// covers last_name/student_id/created_at) are sorted client-side within the
	// loaded page instead of sending a value the API would reject with 422.
	// "Course" here is the Program column (students carry program_code, not a course).
	const CLIENT_SORTS = ['program_code', 'section', 'year_level_label'] as const;
	type ClientSort = (typeof CLIENT_SORTS)[number];
	const isClientSort = (column: typeof sortBy): column is ClientSort =>
		(CLIENT_SORTS as readonly string[]).includes(column);
	const CLIENT_SORT_KEY = {
		program_code: 'programCode',
		section: 'section',
		year_level_label: 'yearLevelLabel',
	} as const;

	// The year_level_id the server can scope to, if any: only when a program
	// is picked AND that program actually has a year with the chosen label.
	const yearIdForServer = $derived(
		programFilter && yearLabel
			? yearOptions.find((y) => y.label === yearLabel)?.id
			: undefined
	);

	// Rows as rendered: server order for backend sorts, local order for the
	// client-side columns above, plus the standalone year-label filter (used
	// whenever the label isn't server-scoped to one year_level_id — i.e. no
	// program picked, or the picked program has no such year).
	const visibleStudents = $derived.by(() => {
		let items = adminStudentsState.items;
		if (isClientSort(sortBy)) {
			const key = CLIENT_SORT_KEY[sortBy];
			const dir = sortDir === 'desc' ? -1 : 1;
			items = [...items].sort(
				(a, b) =>
					(String(a[key] ?? '').localeCompare(String(b[key] ?? '')) ||
						a.lastName.localeCompare(b.lastName) ||
						a.firstName.localeCompare(b.firstName)) * dir
			);
		}
		if (yearLabel && yearIdForServer === undefined) {
			items = items.filter((s) => s.yearLevelLabel === yearLabel);
		}
		return items;
	});

	// In label-only mode the server total covers unfiltered rows, so count
	// what's shown and keep the pager on the single local page.
	const clientYearFiltered = $derived(yearLabel !== '' && yearIdForServer === undefined);
	const displayTotal = $derived(
		clientYearFiltered ? visibleStudents.length : adminStudentsState.total
	);
	let searchTimer: ReturnType<typeof setTimeout> | null = null;
	let searchAbort: AbortController | null = null;
	const autoRefreshStops: (() => void)[] = [];

	onDestroy(() => {
		if (searchTimer) clearTimeout(searchTimer);
		searchAbort?.abort();
		for (const stop of autoRefreshStops) stop();
	});

	const onSearchInput = () => {
		if (searchTimer) clearTimeout(searchTimer);
		searchTimer = setTimeout(() => void load(1), 300);
	};

	let formOpen = $state(false);
	let editing = $state<AdminStudent | null>(null);
	let formError = $state<string | null>(null);
	let fieldErrors = $state<Record<string, string>>({});
	let formBusy = $state(false);
	let deleteTarget = $state<AdminStudent | null>(null);
	let deleteBusy = $state(false);
	let toggleTarget = $state<AdminStudent | null>(null);
	let toggleBusy = $state(false);
	// Credential reset: the row drives the modal, the call and its copy live in
	// TempPasswordModal because all three rosters share one backend path.
	let resetTarget = $state<AdminStudent | null>(null);

	// Face enrollment (D43 3-photo upload): the row drives the modal; status
	// reads GET /admin/face-enrollment/{id}, upload POSTs multipart
	// front/left/right. The roster Face column flips on success via refresh.
	let faceTarget = $state<AdminStudent | null>(null);
	let faceStatus = $state<FaceEnrollmentStatus | null>(null);
	let faceLoading = $state(false);
	let faceFront = $state<File | null>(null);
	let faceLeft = $state<File | null>(null);
	let faceRight = $state<File | null>(null);
	let frontInput = $state<HTMLInputElement>();
	let leftInput = $state<HTMLInputElement>();
	let rightInput = $state<HTMLInputElement>();
	let faceFrontPreview = $state<string | null>(null);
	let faceLeftPreview = $state<string | null>(null);
	let faceRightPreview = $state<string | null>(null);

	const setFaceSlot = (slot: 'front' | 'left' | 'right', file: File | null) => {
		const previousPreview = slot === 'front' ? faceFrontPreview : slot === 'left' ? faceLeftPreview : faceRightPreview;
		if (previousPreview) URL.revokeObjectURL(previousPreview);
		const nextPreview = file ? URL.createObjectURL(file) : null;
		if (slot === 'front') { faceFront = file; faceFrontPreview = nextPreview; }
		else if (slot === 'left') { faceLeft = file; faceLeftPreview = nextPreview; }
		else { faceRight = file; faceRightPreview = nextPreview; }
	};

	const clearFacePhotos = () => {
		setFaceSlot('front', null);
		setFaceSlot('left', null);
		setFaceSlot('right', null);
		if (frontInput) frontInput.value = '';
		if (leftInput) leftInput.value = '';
		if (rightInput) rightInput.value = '';
	};

	const closeFace = () => {
		if (faceBusy || faceRevokeBusy) return;
		faceConfirm = null;
		faceCameraActive = false;
		faceCameraMode = false;
		faceCameraSingleSlot = null;
		faceRetakeSlot = null;
		clearFacePhotos();
		faceTarget = null;
	};
	let faceError = $state<string | null>(null);
	let faceBusy = $state(false);
	let faceRevokeBusy = $state(false);
	let faceNote = $state<string | null>(null);
	let faceCameraMode = $state(false);
	let faceCameraActive = $state(false);
	let faceCameraSingleSlot = $state<'front' | 'left' | 'right' | null>(null);
	let faceRetakeSlot = $state<'front' | 'left' | 'right' | null>(null);
	let faceConfirm = $state<'save' | 'remove' | null>(null);

	const resolveFaceErrorCode = (e: unknown): string | undefined => {
		if (!(e instanceof APIError)) return undefined;
		if (e.code && FACE_ERROR_MESSAGES[e.code]) return e.code;
		if (e.status === 500) return 'internal_error';
		return undefined;
	};

	const FACE_ERROR_MESSAGES: Record<string, string> = {
		invalid_image: 'One of the photos could not be read. Use clear JPG, PNG, or WebP images.',
		no_face_detected: 'No face was detected in one of the photos (front/left/right). Retake with the face centered and well lit.',
		multiple_faces: 'More than one face was detected. Each photo must show a single face.',
		quality_too_low: 'One of the photos failed the quality check (lighting, size, sharpness, eyes open). Retake that photo.',
		student_not_found: 'Student record not found. Refresh the list and try again.',
		internal_error: 'The server hit an unexpected error while enrolling. Check the captured photo and try again, or contact support.',
	};

	const openFace = (row: AdminStudent) => {
		faceTarget = row;
		faceStatus = null;
		clearFacePhotos();
		faceError = null;
		faceNote = null;
		faceCameraMode = false;
		faceCameraActive = false;
		faceConfirm = null;
		faceLoading = true;
		void getFaceEnrollmentStatus(row.id)
			.then((status) => {
				if (faceTarget?.id === row.id) faceStatus = status;
			})
			.catch((e: unknown) => {
				if (faceTarget?.id !== row.id) return;
				faceError =
					e instanceof APIError && e.code && FACE_ERROR_MESSAGES[e.code]
						? FACE_ERROR_MESSAGES[e.code]
						: (e instanceof Error && e.message ? e.message : 'Could not load enrollment status.');
			})
			.finally(() => {
				if (faceTarget?.id === row.id) faceLoading = false;
			});
	};

	const pickFacePhoto = async (slot: 'front' | 'left' | 'right', list: FileList | null, input?: HTMLInputElement) => {
		const file = list?.[0] ?? null;
		try {
			if (!file) return;
			const parsed = facePhotoSchema.safeParse(file);
			if (!parsed.success) {
				faceError = parsed.error.issues[0]?.message ?? 'Photo rejected.';
				return;
			}
			const quality = await validateFacePhoto(file);
			if (!quality.ok) {
				faceError = quality.reason ?? 'Photo rejected.';
				return;
			}
			faceError = null;
			setFaceSlot(slot, file);
		} finally {
			if (input) input.value = '';
		}
	};

	const handleFaceCameraComplete = (photos: { front: File; left: File; right: File }) => {
		setFaceSlot('front', photos.front);
		setFaceSlot('left', photos.left);
		setFaceSlot('right', photos.right);
		faceCameraActive = false;
		faceCameraMode = false;
		faceCameraSingleSlot = null;
		faceError = null;
	};

	const handleSingleCapture = (slot: 'front' | 'left' | 'right', file: File) => {
		setFaceSlot(slot, file);
		faceCameraMode = false;
		faceCameraActive = false;
		faceCameraSingleSlot = null;
		faceError = null;
	};

	const performUploadFace = async () => {
		if (!faceTarget || faceBusy) return;
		if (!faceFront || !faceLeft || !faceRight) {
			faceError = 'Choose front, left, and right photos to enroll.';
			return;
		}
		faceBusy = true;
		faceError = null;
		faceNote = null;
		try {
			const result = await uploadFaceEnrollment(faceTarget.id, {
				front: faceFront,
				left: faceLeft,
				right: faceRight,
			});
			faceStatus = {
				enrolled: true,
				faceEnrolledAt: result.faceEnrolledAt,
				faceEmbeddingVersion: result.faceEmbeddingVersion,
			};
			faceNote = `Enrolled (v${result.faceEmbeddingVersion}). The roster Face column updates on refresh.`;
			faceConfirm = null;
			clearFacePhotos();
			await refreshAdminStudents();
			notifyEntityChanged('students');
		} catch (e: unknown) {
			if (e instanceof APIError) {
				const code = resolveFaceErrorCode(e);
				if (code && FACE_ERROR_MESSAGES[code]) {
					// Prefer the backend detail, which names the failing photo and gate.
					faceError = e.message && e.message.length > 0 ? e.message : FACE_ERROR_MESSAGES[code];
				} else {
					faceError = e.message || 'Upload failed. Try again.';
				}
			} else {
				faceError = e instanceof Error && e.message ? e.message : 'Upload failed. Try again.';
			}
		} finally {
			faceBusy = false;
		}
	};

	const performRevokeFace = async () => {
		if (!faceTarget || faceRevokeBusy) return;
		faceRevokeBusy = true;
		faceError = null;
		faceNote = null;
		try {
			await revokeFaceEnrollment(faceTarget.id);
			faceConfirm = null;
			faceStatus = { enrolled: false };
			clearFacePhotos();
			faceNote = 'Enrollment removed.';
			await refreshAdminStudents();
			notifyEntityChanged('students');
		} catch (e: unknown) {
			if (e instanceof APIError) {
				const code = resolveFaceErrorCode(e);
				faceError =
					code && FACE_ERROR_MESSAGES[code]
						? (e.message && e.message.length > 0 ? e.message : FACE_ERROR_MESSAGES[code])
						: (e.message || 'Removal failed. Try again.');
			} else {
				faceError = e instanceof Error && e.message ? e.message : 'Removal failed. Try again.';
			}
		} finally {
			faceRevokeBusy = false;
		}
	};

	const requestUploadFace = () => {
		if (!faceTarget || faceBusy || faceRevokeBusy) return;
		if (!faceFront || !faceLeft || !faceRight) {
			faceError = 'Choose front, left, and right photos to enroll.';
			return;
		}
		faceError = null;
		faceConfirm = 'save';
	};

	const requestRevokeFace = () => {
		if (!faceTarget || faceRevokeBusy || faceBusy) return;
		if (!faceStatus?.enrolled) return;
		faceError = null;
		faceConfirm = 'remove';
	};

	const confirmFaceAction = () => {
		if (faceConfirm === 'save') {
			if (!faceFront || !faceLeft || !faceRight) {
				faceError = 'Choose front, left, and right photos to enroll.';
				return;
			}
			void performUploadFace();
		} else if (faceConfirm === 'remove') {
			void performRevokeFace();
		}
	};

	// Form fields (strings for inputs; ids coerced by zod on submit).
	// Program/year are picked from dropdowns (displayed as code — name /
	// label) but still submit DB ids — the Programs UI never shows ids, so
	// raw numeric inputs were unusable. See the modal markup below.
	let f_student_id = $state('');
	let f_first_name = $state('');
	let f_middle_name = $state('');
	let f_last_name = $state('');
	let f_email = $state('');
	let f_program_id = $state('');
	let f_year_level_id = $state('');
	let f_section = $state('');
	// Year options for the Add/Edit modal. Separate from `yearOptions` (the
	// list-filter cascade) so opening the modal never clobbers the filter.
	let modalYearOptions = $state<YearLevel[]>([]);
	let modalYearsLoading = $state(false);
	let modalYearsError = $state<string | null>(null);

	// Fixed page size: the admin store is shared with the dashboard (which
	// loads it with size=1 for KPI counts), so never inherit size from it —
	// that leak is what shrank this table to one row per page.
	const PAGE_SIZE = 10;

	const totalPages = $derived(
		Math.max(1, Math.ceil(displayTotal / PAGE_SIZE))
	);

	const load = (page = 1) => {
		searchAbort?.abort();
		searchAbort = new AbortController();
		return initAdminStudents(
			{
				search: search.trim() || undefined,
				section: sectionFilter.trim() || undefined,
				program_id: programFilter ? Number(programFilter) : undefined,
				year_level_id: yearIdForServer,
				is_active: true,
				// Client-side columns sort locally (see visibleStudents), so
				// leave the request unsorted rather than sending sort_by the
				// backend rejects.
				sort_by: isClientSort(sortBy) ? undefined : sortBy,
				sort_dir: isClientSort(sortBy) ? undefined : sortDir,
			},
			page,
			PAGE_SIZE,
			{ signal: searchAbort.signal }
		);
	};

	// Program picker options (list filter + Add/Edit modal share the program
	// list; the modal keeps its own year options). Reloaded when programs
	// change elsewhere so renames/creates show without a manual reload.
	const loadProgramOptions = async () => {
		try {
			programOptions = (await listPrograms({ page: 1, size: 50 })).items;
		} catch {
			programOptions = [];
		}
	};

	const reloadProgramLookups = async () => {
		await loadProgramOptions();
		// Keep the picked program's year cascade in sync when its years change.
		if (programFilter) {
			try {
				yearOptions = await listYearLevels(Number(programFilter));
			} catch {
				yearOptions = [];
			}
		}
	};

	const refreshVisible = () => {
		if (!adminStudentsState.loading) void refreshAdminStudents();
	};

	onMount(() => {
		void initFaceModel();
		void loadProgramOptions();
		load(1);
		// Own entity -> refresh the table; lookup entity -> reload picker
		// options only. Focus return -> refresh the visible page (1 GET,
		// skipped while hidden/loading; idle tabs issue 0 requests).
		autoRefreshStops.push(
			subscribeEntity('students', refreshVisible),
			subscribeEntity('programs', () => void reloadProgramLookups()),
			onFocusRevalidate(refreshVisible)
		);
	});

	const changeProgram = async () => {
		yearLabel = '';
		yearOptions = [];
		if (programFilter) {
			try {
				yearOptions = await listYearLevels(Number(programFilter));
			} catch {
				yearOptions = [];
			}
		}
		load(1);
	};

	// Modal cascade: program select drives the year select via
	// listYearLevels, mirroring the offerings page pattern. Values are still
	// DB ids (the create/update contract takes ids); only the display is
	// human (code — name / label).
	const changeModalProgram = async () => {
		f_year_level_id = '';
		modalYearOptions = [];
		modalYearsError = null;
		if (!f_program_id) return;
		modalYearsLoading = true;
		try {
			modalYearOptions = await listYearLevels(Number(f_program_id));
			if (modalYearOptions.length === 0) {
				modalYearsError = 'No year levels under this program yet — add one in Program Management first.';
			}
		} catch {
			modalYearOptions = [];
			modalYearsError = 'Could not load year levels. Re-pick the program to retry.';
		} finally {
			modalYearsLoading = false;
		}
	};

	// The modal shares `programOptions` with the filter bar; reload it when
	// empty so the selects work even if the initial list fetch failed.
	const ensureModalPrograms = async () => {
		if (programOptions.length > 0) return;
		try {
			programOptions = (await listPrograms({ page: 1, size: 50 })).items;
		} catch {
			programOptions = [];
		}
	};

	const applyFilters = () => {
		if (searchTimer) {
			clearTimeout(searchTimer);
			searchTimer = null;
		}
		load(1);
	};

	const toggleSort = (column: typeof sortBy) => {
		if (sortBy === column) {
			sortDir = sortDir === 'asc' ? 'desc' : 'asc';
		} else {
			sortBy = column;
			sortDir = 'asc';
		}
		load(adminStudentsState.page);
	};

	const sortArrow = (column: typeof sortBy) =>
		sortBy === column ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ' ↕';

	// Sort state for assistive tech, mirroring the professor ledger pattern
	// (professor/attendance/+page.svelte). The arrow glyph is decorative, so it
	// is hidden from screen readers and the button carries the spoken state.
	const sortLabel = (column: typeof sortBy, label: string): string => {
		if (sortBy !== column) return `Sort by ${label.toLowerCase()} ascending`;
		return `Sort by ${label.toLowerCase()} ${sortDir === 'asc' ? 'descending' : 'ascending'}`;
	};

	const ariaSort = (column: typeof sortBy): 'ascending' | 'descending' | 'none' =>
		sortBy === column ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none';

	const fullName = (s: AdminStudent) =>
		[s.firstName, s.middleName, s.lastName].filter(Boolean).join(' ');

	const clearFieldError = (field: string) => {
		if (fieldErrors[field]) fieldErrors = { ...fieldErrors, [field]: '' };
	};

	const openCreate = () => {
		editing = null;
		formError = null;
		fieldErrors = {};
		f_student_id = '';
		f_first_name = '';
		f_middle_name = '';
		f_last_name = '';
		f_email = '';
		f_program_id = '';
		f_year_level_id = '';
		f_section = '';
		modalYearOptions = [];
		modalYearsError = null;
		formOpen = true;
		void ensureModalPrograms();
	};

	const openEdit = (s: AdminStudent) => {
		editing = s;
		formError = null;
		fieldErrors = {};
		f_student_id = s.studentId;
		f_first_name = s.firstName;
		f_middle_name = s.middleName ?? '';
		f_last_name = s.lastName;
		f_email = s.email;
		// Pre-populate the actual assigned cohort so administrators see the
		// current program/year immediately. PATCH still sends both ids; the
		// backend resolves the same row when unchanged.
		f_program_id = String(s.programId);
		f_year_level_id = String(s.yearLevelId);
		f_section = s.section ?? '';
		modalYearOptions = [];
		modalYearsError = null;
		formOpen = true;
		void ensureModalPrograms();
		void loadEditYears(s.programId, s.yearLevelId);
	};

	const loadEditYears = async (programId: number, yearLevelId: number) => {
		modalYearsLoading = true;
		try {
			const years = await listYearLevels(programId);
			modalYearOptions = years;
			if (!years.some((y) => y.id === yearLevelId)) {
				f_year_level_id = '';
			}
		} catch {
			modalYearOptions = [];
			modalYearsError = 'Could not load year levels. Re-pick the program to retry.';
		} finally {
			modalYearsLoading = false;
		}
	};

	const submitForm = async () => {
		formError = null;
		fieldErrors = {};
		formBusy = true;
		try {
			if (editing === null) {
				const parsed = adminStudentCreateSchema.safeParse({
					student_id: f_student_id,
					first_name: f_first_name,
					middle_name: f_middle_name || undefined,
					last_name: f_last_name,
					email: f_email,
					program_id: f_program_id,
					year_level_id: f_year_level_id,
					section: f_section || undefined,
				});
				if (!parsed.success) {
					const fe: Record<string, string> = {};
					for (const issue of parsed.error.issues) {
						const key = String(issue.path[0] ?? '');
						if (key && !fe[key]) fe[key] = issue.message;
					}
					fieldErrors = fe;
					formError =
						Object.keys(fe).length > 0
							? 'Some information needs your attention. Review the highlighted fields and correct the indicated errors.'
							: (parsed.error.issues[0]?.message ?? 'Check the form and try again.');
					return;
				}
				const d = parsed.data;
				await createStudent({
					student_id: d.student_id,
					first_name: d.first_name,
					middle_name: d.middle_name || undefined,
					last_name: d.last_name,
					email: d.email,
					program_id: d.program_id,
					year_level_id: d.year_level_id,
					section: d.section || undefined,
				});
			} else {
				if (!f_program_id || !f_year_level_id) {
					fieldErrors = { program_id: 'Pick a program.', year_level_id: 'Pick a year level.' };
					formError = 'Program and year level are required.';
					return;
				}
			const parsed = adminStudentUpdateSchema.safeParse({
				first_name: f_first_name,
				middle_name: f_middle_name || undefined,
				last_name: f_last_name,
				email: f_email,
				program_id: f_program_id,
				year_level_id: f_year_level_id,
				section: f_section || undefined,
			});
			if (!parsed.success) {
				const fe: Record<string, string> = {};
				for (const issue of parsed.error.issues) {
					const key = String(issue.path[0] ?? '');
					if (key && !fe[key]) fe[key] = issue.message;
				}
				fieldErrors = fe;
				formError =
					Object.keys(fe).length > 0
						? 'Some information needs your attention. Review the highlighted fields and correct the indicated errors.'
						: (parsed.error.issues[0]?.message ?? 'Check the form and try again.');
				return;
			}
			const d = parsed.data;
			await updateStudent(editing.id, {
				first_name: d.first_name,
				// Edit modals prefill from the row, so an empty field means
				// "cleared" — send null (the backend nulls the column) rather
				// than omitting, which would make clearing impossible.
				middle_name: d.middle_name || null,
				last_name: d.last_name,
				email: d.email,
				program_id: d.program_id,
				year_level_id: d.year_level_id,
				section: d.section,
			});
			}
			formOpen = false;
			await refreshAdminStudents();
			notifyEntityChanged('students');
		} catch (e: unknown) {
			formError = friendlyActionError(e, 'Save failed. Please try again.');
		} finally {
			formBusy = false;
		}
	};

	const confirmDelete = async () => {
		if (!deleteTarget) return;
		deleteBusy = true;
		try {
			await deleteArchivedStudent(deleteTarget.id);
			deleteTarget = null;
		} catch {
			// deleteArchivedStudent already put the reason in actionError —
			// keep the modal open so it stays visible.
		} finally {
			deleteBusy = false;
		}
	};

	const confirmToggle = async () => {
		if (!toggleTarget || toggleBusy) return;
		toggleBusy = true;
		try {
			await toggleStudentActive(toggleTarget);
			// Keep the modal open on failure so the surfaced error stays visible;
			// on success the store clears actionError and the row leaves the view.
			if (!adminStudentsState.actionError) toggleTarget = null;
		} finally {
			toggleBusy = false;
		}
	};
</script>

<div class="page page-enter">
	<header class="header">
		<div>
			<h1>Student Management</h1>
			<p class="muted">Roster records students claim at registration · {displayTotal} total</p>
		</div>
		<div class="header-actions">
			<button class="btn btn-secondary" data-testid="import" onclick={() => goto(Routes.ADMIN_STUDENTS_IMPORT)}>
				<AppIcon name="file" size={18} />
				Import
			</button>
			<button class="btn btn-secondary" onclick={() => goto(Routes.ADMIN_STUDENTS_ARCHIVE)}>
				Archive
			</button>
			<button class="btn btn-primary" data-testid="add-student" onclick={openCreate}>
				<AppIcon name="plus" size={18} />
				Add
			</button>
		</div>
	</header>

	<section class="card filters">
		<input
			class="input search"
			type="search"
			placeholder="Search ID, name, email…"
			aria-label="Search students"
			bind:value={search}
			oninput={onSearchInput}
			onkeydown={(e) => {
				if (e.key === 'Enter') applyFilters();
			}}
		/>
		<input
			class="input section"
			type="text"
			placeholder="Section (e.g. A)"
			aria-label="Section filter"
			bind:value={sectionFilter}
			oninput={onSearchInput}
			onkeydown={(e) => {
				if (e.key === 'Enter') applyFilters();
			}}
		/>
		<select class="input" aria-label="Program filter" bind:value={programFilter} onchange={changeProgram}>
			<option value="">All programs</option>
			{#each programOptions as p (p.id)}
				<option value={String(p.id)}>{p.code} — {p.name}</option>
			{/each}
		</select>
		<select class="input" aria-label="Year level filter" bind:value={yearLabel} onchange={applyFilters}>
			<option value="">All years</option>
			{#each YEAR_LABELS as label (label)}
				<option value={label}>{label}</option>
			{/each}
		</select>
		<button class="btn btn-secondary" data-testid="apply" onclick={applyFilters}>Apply</button>
	</section>

	{#if adminStudentsState.loading && adminStudentsState.items.length === 0}
		<SkeletonTable rows={8} cols={7} label="Loading students…" />
	{:else if adminStudentsState.error}
		<section class="card">
			<p class="error">Could not load students: {adminStudentsState.error}</p>
			<button class="btn btn-secondary" onclick={() => load(adminStudentsState.page)}>Retry</button>
		</section>
	{:else if visibleStudents.length === 0}
		<section class="card">
			<EmptyState
				icon="users"
				title="No students match these filters"
				hint="Import a roster or add one manually."
			/>
		</section>
	{:else}
		<section class="card table-wrap" aria-busy={adminStudentsState.loading}>
			{#if adminStudentsState.actionError}
				<p class="error" role="alert">{adminStudentsState.actionError}</p>
			{/if}
			<table>
				<thead>
					<tr>
						<th scope="col" aria-sort={ariaSort('student_id')}>
							<button class="th-btn" type="button" onclick={() => toggleSort('student_id')} aria-label={sortLabel('student_id', 'ID')}>
								ID<span aria-hidden="true">{sortArrow('student_id')}</span>
							</button>
						</th>
						<th scope="col" aria-sort={ariaSort('last_name')}>
							<button class="th-btn" type="button" onclick={() => toggleSort('last_name')} aria-label={sortLabel('last_name', 'Name')}>
								Name<span aria-hidden="true">{sortArrow('last_name')}</span>
							</button>
						</th>
						<th scope="col">Email</th>
						<th scope="col" aria-sort={ariaSort('program_code')}>
							<button class="th-btn" type="button" onclick={() => toggleSort('program_code')} aria-label={sortLabel('program_code', 'Program')}>
								Program<span aria-hidden="true">{sortArrow('program_code')}</span>
							</button>
						</th>
						<th scope="col" aria-sort={ariaSort('section')}>
							<button class="th-btn" type="button" onclick={() => toggleSort('section')} aria-label={sortLabel('section', 'Section')}>
								Sec<span aria-hidden="true">{sortArrow('section')}</span>
							</button>
						</th>
						<th scope="col" aria-sort={ariaSort('year_level_label')}>
							<button class="th-btn" type="button" onclick={() => toggleSort('year_level_label')} aria-label={sortLabel('year_level_label', 'Year level')}>
								Year<span aria-hidden="true">{sortArrow('year_level_label')}</span>
							</button>
						</th>
						<th scope="col">Face</th>
						<th scope="col">Claim</th>
						<th scope="col"><span class="sr">Actions</span></th>
					</tr>
				</thead>
				<tbody>
					{#each visibleStudents as s (s.id)}
						<tr>
							<td class="mono">{s.studentId}</td>
							<td>{fullName(s)}</td>
							<td>
								<button class="link mono" onclick={() => goto(adminStudent(s.id))}>
									{s.email}
								</button>
							</td>
							<td>{s.programCode}</td>
							<td>{s.section ?? '—'}</td>
							<td>{s.yearLevelLabel}</td>
							<td>{s.faceEnrolled ? 'Yes' : '—'}</td>
							<td>{s.claimStatus}</td>
							<td>
								<div class="row-actions">
									<button class="link" onclick={() => openEdit(s)}>Edit</button>
									<button
										class="link"
										onclick={() => {
											adminStudentsState.actionError = null;
											toggleTarget = s;
										}}
									>
										{s.isActive ? 'Deactivate' : 'Reactivate'}
									</button>
									{#if !s.isActive}
										<button class="link danger" onclick={() => { adminStudentsState.actionError = null; deleteTarget = s; }}>Delete</button>
									{/if}
									<button class="link" onclick={() => (resetTarget = s)}>Reset password</button>
									<button class="link" onclick={() => openFace(s)}>
										{s.faceEnrolled ? 'Re-enroll face' : 'Enroll face'}
									</button>
								</div>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
			<div class="pager">
				<button
					class="btn btn-secondary"
					disabled={adminStudentsState.loading || clientYearFiltered || adminStudentsState.page <= 1}
					onclick={() => load(Math.max(1, adminStudentsState.page - 1))}
				>
					‹ Prev
				</button>
				<span class="muted"
					>Page {Math.min(adminStudentsState.page, totalPages)} of {totalPages} · {displayTotal}
					total</span
				>
				<button
					class="btn btn-secondary"
					disabled={adminStudentsState.loading || clientYearFiltered || adminStudentsState.page >= totalPages}
					onclick={() => load(Math.min(totalPages, adminStudentsState.page + 1))}
				>
					Next ›
				</button>
			</div>
		</section>
	{/if}
</div>

{#if formOpen}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="student-form-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (formOpen = false) }}
		>
			<h2 id="student-form-title" class="modal-title">{editing ? 'Edit student' : 'Add student'}</h2>
			{#if formError}
				<p class="error" role="alert">{formError}</p>
			{/if}
			<div class="form">
				{#if !editing}
					<label>
						Student ID *
						<input
							class="input"
							class:invalid={!!fieldErrors.student_id}
							bind:value={f_student_id}
							placeholder="ID number as printed on the student card"
							maxlength="50"
							aria-required="true"
							aria-invalid={!!fieldErrors.student_id}
							aria-describedby="student-id-help"
							oninput={() => clearFieldError('student_id')}
						/>
						{#if fieldErrors.student_id}
							<p class="field-error" role="alert">{fieldErrors.student_id}</p>
						{:else}
							<p class="hint" id="student-id-help">1–50 characters. Stored in uppercase.</p>
						{/if}
					</label>
				{/if}
				<div class="grid2">
					<label>
						First name *
						<input
							class="input"
							class:invalid={!!fieldErrors.first_name}
							bind:value={f_first_name}
							maxlength="100"
							aria-required="true"
							aria-invalid={!!fieldErrors.first_name}
							aria-describedby="student-first-help"
							oninput={() => clearFieldError('first_name')}
						/>
						{#if fieldErrors.first_name}
							<p class="field-error" role="alert">{fieldErrors.first_name}</p>
						{:else}
							<p class="hint" id="student-first-help">Up to 100 characters.</p>
						{/if}
					</label>
					<label>
						Middle name (optional)
						<input
							class="input"
							class:invalid={!!fieldErrors.middle_name}
							bind:value={f_middle_name}
							maxlength="100"
							aria-invalid={!!fieldErrors.middle_name}
							aria-describedby="student-middle-help"
							oninput={() => clearFieldError('middle_name')}
						/>
						{#if fieldErrors.middle_name}
							<p class="field-error" role="alert">{fieldErrors.middle_name}</p>
						{:else}
							<p class="hint" id="student-middle-help">Optional. Leave blank if the student has no middle name.</p>
						{/if}
					</label>
				</div>
				<div class="grid2">
					<label>
						Last name *
						<input
							class="input"
							class:invalid={!!fieldErrors.last_name}
							bind:value={f_last_name}
							maxlength="100"
							aria-required="true"
							aria-invalid={!!fieldErrors.last_name}
							aria-describedby="student-last-help"
							oninput={() => clearFieldError('last_name')}
						/>
						{#if fieldErrors.last_name}
							<p class="field-error" role="alert">{fieldErrors.last_name}</p>
						{:else}
							<p class="hint" id="student-last-help">Up to 100 characters.</p>
						{/if}
					</label>
					<label>
						Email *
						<input
							class="input"
							class:invalid={!!fieldErrors.email}
							type="email"
							bind:value={f_email}
							maxlength="255"
							aria-required="true"
							aria-invalid={!!fieldErrors.email}
							aria-describedby="student-email-help"
							oninput={() => clearFieldError('email')}
						/>
						{#if fieldErrors.email}
							<p class="field-error" role="alert">{fieldErrors.email}</p>
						{:else}
							<p class="hint" id="student-email-help">Valid email, up to 255 characters.</p>
						{/if}
					</label>
				</div>
				{#if !editing}
					<div class="grid2">
						<label>
							Program *
							<select
								class="input"
								class:invalid={!!fieldErrors.program_id}
								aria-label="Program"
								aria-required="true"
								aria-invalid={!!fieldErrors.program_id}
								bind:value={f_program_id}
								onchange={() => void changeModalProgram()}
							>
								<option value="">Select program…</option>
								{#each programOptions as p (p.id)}
									<option value={String(p.id)}>{p.code} — {p.name}</option>
								{/each}
							</select>
							{#if fieldErrors.program_id}
								<p class="field-error" role="alert">{fieldErrors.program_id}</p>
							{:else}
								<p class="hint">Pick a program to load its year levels.</p>
							{/if}
						</label>
						<label>
							Year level *
							<select
								class="input"
								class:invalid={!!fieldErrors.year_level_id}
								aria-label="Year level"
								aria-required="true"
								aria-invalid={!!fieldErrors.year_level_id}
								bind:value={f_year_level_id}
								disabled={!f_program_id || modalYearsLoading}
							>
								<option value="">{modalYearsLoading ? 'Loading…' : 'Select year level…'}</option>
								{#each modalYearOptions as y (y.id)}
									<option value={String(y.id)}>{y.label}</option>
								{/each}
							</select>
							{#if fieldErrors.year_level_id}
								<p class="field-error" role="alert">{fieldErrors.year_level_id}</p>
							{:else if modalYearsError}
								<p class="hint" role="status">{modalYearsError}</p>
							{:else}
								<p class="hint">Year levels belong to the selected program.</p>
							{/if}
						</label>
					</div>
					<label>
						Section
						<input
							class="input"
							class:invalid={!!fieldErrors.section}
							bind:value={f_section}
							placeholder="A"
							maxlength="20"
							aria-invalid={!!fieldErrors.section}
							aria-describedby="student-section-help"
							oninput={() => clearFieldError('section')}
						/>
						{#if fieldErrors.section}
							<p class="field-error" role="alert">{fieldErrors.section}</p>
						{:else}
							<p class="hint" id="student-section-help">Optional. Up to 20 characters.</p>
						{/if}
					</label>
				{:else}
					<div class="grid2">
						<label>
							Program *
							<select
								class="input"
								class:invalid={!!fieldErrors.program_id}
								aria-label="Program"
								aria-required="true"
								aria-invalid={!!fieldErrors.program_id}
								bind:value={f_program_id}
								onchange={() => void changeModalProgram()}
							>
								<option value="">Select program…</option>
								{#each programOptions as p (p.id)}
									<option value={String(p.id)}>{p.code} — {p.name}</option>
								{/each}
							</select>
							{#if fieldErrors.program_id}
								<p class="field-error" role="alert">{fieldErrors.program_id}</p>
							{:else}
								<p class="hint">Leave blank to keep the current program.</p>
							{/if}
						</label>
						<label>
							Year level *
							<select
								class="input"
								class:invalid={!!fieldErrors.year_level_id}
								aria-label="Year level"
								aria-required="true"
								aria-invalid={!!fieldErrors.year_level_id}
								bind:value={f_year_level_id}
								disabled={!f_program_id || modalYearsLoading}
							>
								<option value="">{modalYearsLoading ? 'Loading…' : 'Select year level…'}</option>
								{#each modalYearOptions as y (y.id)}
									<option value={String(y.id)}>{y.label}</option>
								{/each}
							</select>
							{#if fieldErrors.year_level_id}
								<p class="field-error" role="alert">{fieldErrors.year_level_id}</p>
							{:else if modalYearsError}
								<p class="hint" role="status">{modalYearsError}</p>
							{:else}
								<p class="hint">Leave blank to keep the current year level.</p>
							{/if}
						</label>
					</div>
					<label>
						Section
						<input
							class="input"
							class:invalid={!!fieldErrors.section}
							bind:value={f_section}
							maxlength="20"
							aria-invalid={!!fieldErrors.section}
							aria-describedby="student-section-edit-help"
							oninput={() => clearFieldError('section')}
						/>
						{#if fieldErrors.section}
							<p class="field-error" role="alert">{fieldErrors.section}</p>
						{:else}
							<p class="hint" id="student-section-edit-help">Optional. Up to 20 characters.</p>
						{/if}
					</label>
				{/if}
			</div>
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (formOpen = false)}>Cancel</button>
				<button class="btn btn-primary" data-testid="save-student" aria-busy={formBusy} disabled={formBusy} onclick={submitForm}>
					{formBusy ? 'Saving…' : 'Save'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if deleteTarget}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="delete-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (deleteTarget = null) }}
		>
			<h2 id="delete-title" class="modal-title">Permanently delete?</h2>
			<p class="modal-text">
				{fullName(deleteTarget)} ({deleteTarget.studentId}) is inactive. This cannot be undone.
				If enrollment, attendance, or excuse history is still linked, deletion will be
				blocked and the record stays archived.
			</p>
			{#if adminStudentsState.actionError}
				<p class="error" role="alert">{adminStudentsState.actionError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (deleteTarget = null)}>Cancel</button>
				<button class="btn btn-danger" disabled={deleteBusy} onclick={confirmDelete}>
					{deleteBusy ? 'Deleting…' : 'Delete'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if toggleTarget}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="toggle-student-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (toggleBusy ? undefined : (toggleTarget = null)) }}
		>
			<h2 id="toggle-student-title" class="modal-title">
				{toggleTarget.isActive ? 'Deactivate student?' : 'Reactivate student?'}
			</h2>
			<p class="modal-text">
				{#if toggleTarget.isActive}
					{fullName(toggleTarget)} will be moved to the Archive, lose login access, and have their face enrollment revoked. You can restore them later from the Archive.
				{:else}
					{fullName(toggleTarget)} will return to the active roster and regain login access. Face enrollment will need to be re-enrolled.
				{/if}
			</p>
			{#if adminStudentsState.actionError}
				<p class="error" role="alert">{adminStudentsState.actionError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" disabled={toggleBusy} onclick={() => (toggleTarget = null)}>Cancel</button>
				<button
					class="btn {toggleTarget.isActive ? 'btn-danger' : 'btn-primary'}"
					aria-busy={toggleBusy}
					disabled={toggleBusy}
					onclick={() => void confirmToggle()}
				>
					{toggleBusy ? 'Saving…' : (toggleTarget.isActive ? 'Deactivate' : 'Reactivate')}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if resetTarget}
	<TempPasswordModal
		subject="{fullName(resetTarget)} ({resetTarget.studentId})"
		subjectKind="student"
		onconfirm={() => resetStudentPassword(resetTarget!.id)}
		onclose={() => (resetTarget = null)}
	/>
{/if}

{#if faceTarget}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="face-title"
			tabindex="-1"
			use:trapFocus={faceConfirm ? undefined : { onEscape: () => closeFace() }}
		>
			<h2 id="face-title" class="modal-title">
				{faceTarget.faceEnrolled ? 'Re-enroll face' : 'Enroll face'} — {fullName(faceTarget)} ({faceTarget.studentId})
			</h2>
			{#if faceLoading}
				<div class="skeleton-stack" role="status" aria-busy="true">
					<span class="sr-only">Loading enrollment status…</span>
					<Skeleton height={12} width="55%" />
					<Skeleton height={12} width="40%" />
				</div>
			{:else if faceStatus?.enrolled}
				<p class="muted" role="status">
					Enrolled{#if faceStatus.faceEmbeddingVersion} (v{faceStatus.faceEmbeddingVersion}){/if}{#if faceStatus.faceEnrolledAt} · {new Date(faceStatus.faceEnrolledAt).toLocaleDateString()}{/if}.
					Uploading replaces the enrollment.
				</p>
			{:else}
				<p class="muted" role="status">Not enrolled. Upload front, left, and right photos.</p>
			{/if}
			{#if faceError}
				<p class="error" role="alert">{faceError}</p>
			{/if}
			{#if faceNote}
				<p class="note" role="status">{faceNote}</p>
			{/if}
			<div class="face-mode-toggle">
				<button class="btn btn-secondary" class:active={!faceCameraMode} disabled={faceBusy} onclick={() => { faceCameraMode = false; faceCameraActive = false; }}>Upload files</button>
				<button class="btn btn-secondary" class:active={faceCameraMode} disabled={faceBusy} onclick={() => { faceCameraMode = true; faceCameraActive = true; faceCameraSingleSlot = null; }}>Use camera</button>
			</div>

			{#if faceCameraMode}
				<FaceEnrollmentCamera
					active={faceCameraActive}
					singleSlot={faceCameraSingleSlot}
					onComplete={handleFaceCameraComplete}
					onCapture={handleSingleCapture}
					onQualityError={(r) => (faceError = r)}
					onCancel={() => { faceCameraActive = false; faceCameraMode = false; faceCameraSingleSlot = null; }}
				/>
			{:else}
				<div class="form">
					<label>Front photo<input bind:this={frontInput} class="input" type="file" accept=".jpg,.jpeg,.png,.webp" disabled={faceBusy} onchange={(e) => pickFacePhoto('front', e.currentTarget.files, e.currentTarget)} /></label>
					{#if faceFrontPreview}
						<div class="face-preview">
							<img src={faceFrontPreview} alt="Front preview" />
							<button type="button" class="btn ghost" disabled={faceBusy} onclick={() => (faceRetakeSlot = 'front')}>Retake</button>
						</div>
					{/if}
					{#if faceFront}<p class="muted">{faceFront.name} · {(faceFront.size / 1024).toFixed(0)} KB</p>{/if}
					<label>Left photo<input bind:this={leftInput} class="input" type="file" accept=".jpg,.jpeg,.png,.webp" disabled={faceBusy} onchange={(e) => pickFacePhoto('left', e.currentTarget.files, e.currentTarget)} /></label>
					{#if faceLeftPreview}
						<div class="face-preview">
							<img src={faceLeftPreview} alt="Left preview" />
							<button type="button" class="btn ghost" disabled={faceBusy} onclick={() => (faceRetakeSlot = 'left')}>Retake</button>
						</div>
					{/if}
					{#if faceLeft}<p class="muted">{faceLeft.name} · {(faceLeft.size / 1024).toFixed(0)} KB</p>{/if}
					<label>Right photo<input bind:this={rightInput} class="input" type="file" accept=".jpg,.jpeg,.png,.webp" disabled={faceBusy} onchange={(e) => pickFacePhoto('right', e.currentTarget.files, e.currentTarget)} /></label>
					{#if faceRightPreview}
						<div class="face-preview">
							<img src={faceRightPreview} alt="Right preview" />
							<button type="button" class="btn ghost" disabled={faceBusy} onclick={() => (faceRetakeSlot = 'right')}>Retake</button>
						</div>
					{/if}
					{#if faceRight}<p class="muted">{faceRight.name} · {(faceRight.size / 1024).toFixed(0)} KB</p>{/if}
				</div>
				{#if faceRetakeSlot}
					<div class="retake-chooser">
						<p class="muted">Retake {faceRetakeSlot} photo:</p>
						<button type="button" class="btn" disabled={faceBusy} onclick={() => {
							if (faceRetakeSlot === 'front') frontInput?.click();
							else if (faceRetakeSlot === 'left') leftInput?.click();
							else rightInput?.click();
							faceRetakeSlot = null;
						}}>Upload file</button>
						<button type="button" class="btn" disabled={faceBusy} onclick={() => {
							faceCameraSingleSlot = faceRetakeSlot;
							faceCameraMode = true;
							faceCameraActive = true;
							faceRetakeSlot = null;
						}}>Use camera</button>
						<button type="button" class="btn ghost" disabled={faceBusy} onclick={() => (faceRetakeSlot = null)}>Cancel</button>
					</div>
				{/if}
				<div class="modal-actions">
					<button class="btn btn-ghost" disabled={faceBusy || faceRevokeBusy} onclick={closeFace}>Close</button>
					{#if faceStatus?.enrolled}
						<button class="btn btn-danger" disabled={faceBusy || faceRevokeBusy} onclick={() => void requestRevokeFace()}>
							Remove enrollment
						</button>
					{/if}
					<button class="btn btn-primary" disabled={faceBusy || faceRevokeBusy} onclick={() => void requestUploadFace()}>
						Upload enrollment
					</button>
				</div>
			{/if}
		</div>
	</div>

	{#if faceConfirm === 'save'}
		<div class="modal-overlay face-confirm-overlay" role="presentation">
			<div class="modal face-confirm-modal" role="dialog" aria-modal="true" aria-labelledby="face-upload-confirm-title" aria-describedby="face-upload-confirm-description" tabindex="-1" use:trapFocus={{ onEscape: () => (faceConfirm = null) }}>
				<h2 id="face-upload-confirm-title" class="modal-title">Confirm face enrollment upload</h2>
				<p id="face-upload-confirm-description" class="modal-text">
					{faceStatus?.enrolled ? 'This will replace the student’s current face enrollment.' : 'This will create a face enrollment for this student.'}
					Review the photos before continuing.
				</p>
				{#if faceError}<p class="error" role="alert">{faceError}</p>{/if}
				<div class="face-confirm-previews">
					{#if faceFrontPreview}<figure><img src={faceFrontPreview} alt="" /><figcaption>Front</figcaption></figure>{/if}
					{#if faceLeftPreview}<figure><img src={faceLeftPreview} alt="" /><figcaption>Left</figcaption></figure>{/if}
					{#if faceRightPreview}<figure><img src={faceRightPreview} alt="" /><figcaption>Right</figcaption></figure>{/if}
				</div>
				<div class="modal-actions">
					<button class="btn btn-ghost" disabled={faceBusy} onclick={() => (faceConfirm = null)}>Cancel</button>
					<button class="btn btn-primary" disabled={faceBusy || !faceFront || !faceLeft || !faceRight} aria-busy={faceBusy} onclick={confirmFaceAction}>
						{faceBusy ? 'Uploading…' : 'Confirm Upload'}
					</button>
				</div>
			</div>
		</div>
	{:else if faceConfirm === 'remove'}
		<div class="modal-overlay face-confirm-overlay" role="presentation">
			<div class="modal face-confirm-modal" role="dialog" aria-modal="true" aria-labelledby="face-remove-confirm-title" aria-describedby="face-remove-confirm-description" tabindex="-1" use:trapFocus={{ onEscape: () => (faceConfirm = null) }}>
				<h2 id="face-remove-confirm-title" class="modal-title">Remove face enrollment?</h2>
				<p id="face-remove-confirm-description" class="modal-text">
					This permanently removes the student’s current face embedding. The student will no longer have a face enrollment until one is uploaded again.
				</p>
				{#if faceError}<p class="error" role="alert">{faceError}</p>{/if}
				<div class="modal-actions">
					<button class="btn btn-ghost" disabled={faceRevokeBusy} onclick={() => (faceConfirm = null)}>Cancel</button>
					<button class="btn btn-danger" disabled={faceRevokeBusy} aria-busy={faceRevokeBusy} onclick={confirmFaceAction}>
						{faceRevokeBusy ? 'Removing…' : 'Remove Enrollment'}
					</button>
				</div>
			</div>
		</div>
	{/if}
{/if}

<style>
	.page {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
	}

	.header {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 1rem;
		flex-wrap: wrap;
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

	.header-actions {
		display: flex;
		gap: 0.75rem;
	}

	.card {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 1.5rem;
		box-shadow: var(--shadow-sm);
	}

	.filters {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
		align-items: center;
	}

	.input {
		padding: 0.625rem 0.875rem;
		border: 1px solid var(--border-strong);
		border-radius: 8px;
		font-size: 0.9375rem;
		font-family: inherit;
		color: var(--text-strong);
		background: var(--bg-card);
	}

	.input:focus {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
		border-color: var(--accent);
	}

	.search {
		flex: 1 1 240px;
	}

	.section {
		flex: 0 1 140px;
		min-width: 120px;
	}

	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.875rem;
	}

	th,
	td {
		text-align: left;
		padding: 0.625rem 0.5rem;
		border-bottom: 1px solid var(--divider);
		vertical-align: middle;
	}

	th {
		color: var(--text-muted);
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	.th-btn {
		background: none;
		border: none;
		padding: 0;
		font: inherit;
		color: inherit;
		cursor: pointer;
		white-space: nowrap;
	}

	.th-btn:hover {
		color: var(--text-strong);
	}

	.th-btn:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
		border-radius: 4px;
	}

	.mono {
		font-variant-numeric: tabular-nums;
		font-weight: 600;
		white-space: nowrap;
	}

	.face-mode-toggle {
		display: flex;
		gap: 0.5rem;
		margin-bottom: 0.75rem;
	}

	.face-mode-toggle .btn.active,
	.face-mode-toggle .btn.active:hover:not(:disabled),
	.face-mode-toggle .btn.active:focus-visible {
		background: var(--brand);
		color: var(--on-brand);
		border-color: var(--brand);
	}

	.face-mode-toggle .btn:focus-visible,
	.face-confirm-modal .btn:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.face-confirm-overlay {
		z-index: 120;
	}

	.face-confirm-modal {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.face-confirm-previews {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 0.75rem;
	}

	.face-confirm-previews figure {
		min-width: 0;
		margin: 0;
	}

	.face-confirm-previews img {
		display: block;
		width: 100%;
		max-height: 9rem;
		object-fit: contain;
		border-radius: 8px;
		background: var(--divider);
	}

	.face-confirm-previews figcaption {
		margin-top: 0.375rem;
		text-align: center;
		font-size: 0.8125rem;
		color: var(--text-secondary);
	}

	@media (max-width: 420px) {
		.face-confirm-previews { gap: 0.375rem; }
		.face-confirm-previews img { max-height: 6rem; }
	}

	.row-actions {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
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

	.link.danger {
		color: var(--danger);
	}

	.sr {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
	}

	.pager {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		margin-top: 1rem;
	}

	.error {
		color: var(--danger);
		font-size: 0.875rem;
		margin: 0 0 1rem;
	}

	.note {
		color: var(--success);
		font-size: 0.875rem;
		margin: 0 0 1rem;
	}

	.btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		padding: 0.625rem 1rem;
		border-radius: 8px;
		font-size: 0.875rem;
		font-weight: 600;
		font-family: inherit;
		cursor: pointer;
		white-space: nowrap;
		transition: background 0.15s ease, border-color 0.15s ease;
	}

	.btn:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.btn-primary {
		background: var(--brand);
		border: 1px solid var(--brand);
		color: var(--on-brand);
	}

	.btn-primary:hover:not(:disabled) {
		background: var(--brand-hover);
	}

	.btn-secondary {
		background: var(--bg-card);
		border: 1px solid var(--border-strong);
		color: var(--text-strong);
	}

	.btn-secondary:hover:not(:disabled) {
		background: var(--divider);
	}

	.btn-ghost {
		background: var(--divider);
		border: 1px solid transparent;
		color: var(--text-secondary);
	}

	.btn-danger {
		background: var(--danger);
		border: 1px solid var(--danger);
		color: var(--on-brand);
	}

	.modal-overlay {
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
		max-width: 520px;
		max-height: 90vh;
		overflow-y: auto;
		background: var(--bg-card);
		border-radius: 12px;
		box-shadow: var(--shadow-lg);
		padding: 1.75rem 1.5rem;
	}

	.modal-title {
		margin: 0 0 1rem;
		font-size: 1.25rem;
		font-weight: 700;
		color: var(--text);
	}

	.modal-text {
		margin: 0 0 1.5rem;
		font-size: 0.9375rem;
		color: var(--text-secondary);
	}

	.form {
		display: flex;
		flex-direction: column;
		gap: 0.875rem;
	}

	.form label {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-secondary);
	}

	.grid2 {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.875rem;
	}

	.hint {
		font-size: 0.75rem;
		color: var(--text-muted);
		margin: 0;
	}

	.modal-actions {
		display: flex;
		gap: 0.75rem;
		justify-content: flex-end;
		margin-top: 1.5rem;
	}

	.table-wrap {
		overflow-x: auto;
	}

	.input.invalid {
		border-color: var(--danger);
	}

	.field-error {
		color: var(--danger);
		font-size: 0.75rem;
		margin: 0;
	}

	@media (max-width: 640px) {
		.card {
			padding: 1.25rem;
		}

		.grid2 {
			grid-template-columns: minmax(0, 1fr);
		}
	}
	.face-preview {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin: 0.5rem 0;
	}

	.face-preview img {
		width: 96px;
		height: 96px;
		object-fit: cover;
		border-radius: 8px;
		border: 1px solid var(--border-strong, #cbd5e1);
		transform: scaleX(-1);
	}

	.retake-chooser {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex-wrap: wrap;
		margin: 0.5rem 0;
	}

</style>
