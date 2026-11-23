<script lang="ts">
	import ArchiveRosterPage from '$lib/components/ArchiveRosterPage.svelte';
	import {
		archiveRosterFullName,
		type ArchiveRosterConfig
	} from '$lib/components/archive-roster';
	import {
		adminProfessorsState,
		deleteArchivedProfessor,
		initAdminProfessors,
		refreshAdminProfessors,
		toggleProfessorActive
	} from '$lib/features/admin/store.svelte';
	import type { AdminProfessor } from '$lib/shared/types';
	import { Routes } from '$lib/shared/constants/routes';

	// Professors archive (wireframe 4.10): inactive roster rows only.
	// Restore flips is_active back on; Delete permanently removes the row
	// (backend allows it only with no sessions referencing them, else 409).
	// No new backend — the list endpoint's is_active filter.
	// The shared ArchiveRosterPage owns the table, modals, and auto-refresh.

	const config = {
		heading: 'Archived Professors',
		backLabel: 'Back to professors',
		backRoute: Routes.ADMIN_PROFESSORS,
		backTestId: 'back-to-professors',
		searchAriaLabel: 'Search archived professors',
		loadingLabel: 'Loading archived professors…',
		emptyHint: 'Deactivated professors appear here.',
		detailColumnLabel: 'Department',
		detailValue: (professor: AdminProfessor) => professor.department ?? '—',
		restoreTitle: 'Reactivate professor?',
		restoreDescription: (professor: AdminProfessor) =>
			`${archiveRosterFullName(professor)} will return to the active roster and regain login access.`,
		deleteDescription: (professor: AdminProfessor) =>
			`${archiveRosterFullName(professor)} will be removed for good. If class sessions are still linked, deletion will be blocked and the record stays archived.`,
		entity: 'professors'
	} satisfies ArchiveRosterConfig<AdminProfessor>;

	const load = (page: number, search: string) =>
		initAdminProfessors(
			{ search: search.trim() || undefined, is_active: false },
			page,
			adminProfessorsState.size
		);
</script>

<ArchiveRosterPage
	{config}
	roster={adminProfessorsState}
	onLoad={load}
	onRefresh={refreshAdminProfessors}
	onDelete={deleteArchivedProfessor}
	onToggle={toggleProfessorActive}
	onClearActionError={() => (adminProfessorsState.actionError = null)}
/>
