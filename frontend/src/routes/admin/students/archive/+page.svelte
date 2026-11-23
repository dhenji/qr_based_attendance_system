<script lang="ts">
	import ArchiveRosterPage from '$lib/components/ArchiveRosterPage.svelte';
	import {
		archiveRosterFullName,
		type ArchiveRosterConfig
	} from '$lib/components/archive-roster';
	import {
		adminStudentsState,
		deleteArchivedStudent,
		initAdminStudents,
		refreshAdminStudents,
		toggleStudentActive
	} from '$lib/features/admin/store.svelte';
	import type { AdminStudent } from '$lib/shared/types';
	import { Routes } from '$lib/shared/constants/routes';

	// Students archive (wireframe 4.10): inactive roster rows only.
	// Restore flips is_active back on; Delete permanently removes the row
	// (backend allows it only with no enrollments/attendance/excuse records,
	// else 409). No new backend — the list endpoint's is_active filter.
	// The shared ArchiveRosterPage owns the table, modals, and auto-refresh.

	const config = {
		heading: 'Archived Students',
		backLabel: 'Back to students',
		backRoute: Routes.ADMIN_STUDENTS,
		backTestId: 'back-to-students',
		searchAriaLabel: 'Search archived students',
		loadingLabel: 'Loading archived students…',
		emptyHint: 'Deactivated students appear here.',
		detailColumnLabel: 'Program',
		detailValue: (student: AdminStudent) => student.programCode,
		restoreTitle: 'Reactivate student?',
		restoreDescription: (student: AdminStudent) =>
			`${archiveRosterFullName(student)} will return to the active roster and regain login access. Face enrollment will need to be re-enrolled.`,
		deleteDescription: (student: AdminStudent) =>
			`${archiveRosterFullName(student)} will be removed for good. If enrollment, attendance, or excuse history is still linked, deletion will be blocked and the record stays archived.`,
		entity: 'students'
	} satisfies ArchiveRosterConfig<AdminStudent>;

	const load = (page: number, search: string) =>
		initAdminStudents(
			{ search: search.trim() || undefined, is_active: false },
			page,
			adminStudentsState.size
		);
</script>

<ArchiveRosterPage
	{config}
	roster={adminStudentsState}
	onLoad={load}
	onRefresh={refreshAdminStudents}
	onDelete={deleteArchivedStudent}
	onToggle={toggleStudentActive}
	onClearActionError={() => (adminStudentsState.actionError = null)}
/>
