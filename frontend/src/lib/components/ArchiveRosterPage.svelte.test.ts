import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/svelte';
import ArchiveRosterPage from './ArchiveRosterPage.svelte';
import type { ArchiveRosterConfig, ArchiveRosterItem } from './archive-roster';

vi.mock('$app/navigation', () => ({ goto: vi.fn() }));

// testing-library renders components without propagating a generic argument,
// so the props are expressed against the base `ArchiveRosterItem` shape and the
// per-entity extra field is narrowed inside `detailValue`.
const item = {
	id: 1,
	email: 'ada@example.com',
	firstName: 'Ada',
	middleName: '',
	lastName: 'Lovelace',
	programCode: 'BSCS'
} satisfies ArchiveRosterItem & { programCode: string };

const config = {
	heading: 'Archived Students',
	backLabel: 'Back to students',
	backRoute: '/admin/students',
	backTestId: 'back-to-students',
	searchAriaLabel: 'Search archived students',
	loadingLabel: 'Loading archived students…',
	emptyHint: 'Deactivated students appear here.',
	detailColumnLabel: 'Program',
	detailValue: (row: ArchiveRosterItem) => (row as typeof item).programCode,
	restoreTitle: 'Reactivate student?',
	restoreDescription: (row: ArchiveRosterItem) => `${row.firstName} will return to the active roster.`,
	deleteDescription: (row: ArchiveRosterItem) => `${row.firstName} will be removed for good.`,
	entity: 'students'
} satisfies ArchiveRosterConfig<ArchiveRosterItem>;

const renderPage = (items: ArchiveRosterItem[] = [item]) => {
	const onDelete = vi.fn().mockResolvedValue(undefined);
	const onToggle = vi.fn().mockResolvedValue(undefined);
	const onClearActionError = vi.fn();
	render(ArchiveRosterPage, {
		props: {
			config,
			roster: {
				items,
				total: items.length,
				page: 1,
				size: 20,
				loading: false,
				error: null,
				actionError: null
			},
			onLoad: vi.fn(),
			onRefresh: vi.fn(),
			onDelete,
			onToggle,
			onClearActionError
		}
	});
	return { onDelete, onToggle, onClearActionError };
};

describe('ArchiveRosterPage', () => {
	it('renders the roster rows and fires the initial load', async () => {
		const onLoad = vi.fn();
		render(ArchiveRosterPage, {
			props: {
				config,
				roster: {
					items: [item],
					total: 1,
					page: 1,
					size: 20,
					loading: false,
					error: null,
					actionError: null
				},
				onLoad,
				onRefresh: vi.fn(),
				onDelete: vi.fn().mockResolvedValue(undefined),
				onToggle: vi.fn().mockResolvedValue(undefined),
				onClearActionError: vi.fn()
			}
		});

		expect(screen.getByRole('heading', { name: 'Archived Students' })).toBeInTheDocument();
		expect(screen.getByText('Ada Lovelace')).toBeInTheDocument();
		expect(screen.getByText('BSCS')).toBeInTheDocument();
		expect(screen.getByLabelText('Search archived students')).toBeInTheDocument();
		expect(onLoad).toHaveBeenCalledWith(1, '');
	});

	it('restores through the confirmation modal', async () => {
		const { onToggle, onClearActionError } = renderPage();

		await fireEvent.click(screen.getAllByRole('button', { name: 'Restore' })[0]);
		const dialog = await screen.findByRole('dialog');
		expect(dialog).toHaveAttribute('aria-modal', 'true');

		await fireEvent.click(within(dialog).getByRole('button', { name: 'Restore' }));
		expect(onToggle).toHaveBeenCalledWith(item);
		expect(onClearActionError).toHaveBeenCalled();
	});

	it('deletes through the confirmation modal', async () => {
		const { onDelete } = renderPage();

		await fireEvent.click(screen.getAllByRole('button', { name: 'Delete' })[0]);
		const dialog = await screen.findByRole('dialog');
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));
		expect(onDelete).toHaveBeenCalledWith(1);
	});

	it('keeps the delete modal open and shows the error when deletion is blocked', async () => {
		const onDelete = vi.fn().mockRejectedValue(new Error('blocked by history'));
		render(ArchiveRosterPage, {
			props: {
				config,
				roster: {
					items: [item],
					total: 1,
					page: 1,
					size: 20,
					loading: false,
					error: null,
					actionError: 'Deletion blocked: history still linked.'
				},
				onLoad: vi.fn(),
				onRefresh: vi.fn(),
				onDelete,
				onToggle: vi.fn().mockResolvedValue(undefined),
				onClearActionError: vi.fn()
			}
		});

		await fireEvent.click(screen.getAllByRole('button', { name: 'Delete' })[0]);
		const dialog = await screen.findByRole('dialog');
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));

		await waitFor(() => expect(onDelete).toHaveBeenCalledWith(1));
		expect(screen.getByRole('dialog')).toBeInTheDocument();
		expect(within(screen.getByRole('dialog')).getByRole('alert')).toHaveTextContent(
			'Deletion blocked'
		);
	});

	it('shows the empty state when the archive has no rows', () => {
		renderPage([]);
		expect(screen.getByText('Archive is empty')).toBeInTheDocument();
	});
});
