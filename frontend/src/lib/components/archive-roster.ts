// components/archive-roster.ts
// Types for the shared archive roster page (issue #497). The two admin
// archive routes (/admin/students/archive and /admin/professors/archive)
// are thin wrappers around ArchiveRosterPage.svelte; the per-entity
// differences live in the config object below.

import type { AdminEntity } from '$lib/shared/utils/entityEvents';

/** The minimum row shape the archive table can render. */
export interface ArchiveRosterItem {
	id: number;
	email: string;
	firstName: string;
	middleName?: string | null;
	lastName: string;
}

/**
 * Read-only view of the owning store's list state. The page never mutates
 * this object; actions go through the callbacks so the store stays the
 * single writer.
 */
export interface ArchiveRosterState<T extends ArchiveRosterItem> {
	items: T[];
	total: number;
	page: number;
	size: number;
	loading: boolean;
	error: string | null;
	actionError: string | null;
}

/**
 * Everything that differs between the student and professor archives.
 * `detailColumnLabel`/`detailValue` cover the Program vs Department column.
 */
export interface ArchiveRosterConfig<T extends ArchiveRosterItem> {
	heading: string;
	backLabel: string;
	backRoute: string;
	backTestId: string;
	searchAriaLabel: string;
	loadingLabel: string;
	emptyHint: string;
	detailColumnLabel: string;
	detailValue: (item: T) => string;
	restoreTitle: string;
	restoreDescription: (item: T) => string;
	deleteDescription: (item: T) => string;
	entity: AdminEntity;
}

/** Display name used in the table, confirmations, and copy. */
export const archiveRosterFullName = (item: ArchiveRosterItem): string =>
	[item.firstName, item.middleName, item.lastName].filter(Boolean).join(' ');
