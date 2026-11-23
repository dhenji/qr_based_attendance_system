import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import Pagination from './Pagination.svelte';

describe('Pagination', () => {
	it('renders the full control with numbered pages and a page count', () => {
		render(Pagination, { props: { page: 2, totalPages: 5, onPageChange: vi.fn() } });
		expect(screen.getByRole('button', { name: 'First page' })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'Page 2' })).toBeDisabled();
		expect(screen.getByRole('button', { name: 'Page 2' })).toHaveAttribute('aria-current', 'page');
		expect(screen.getByText('Page 2 of 5')).toBeInTheDocument();
	});

	it('calls onPageChange from the full control', async () => {
		const onPageChange = vi.fn();
		render(Pagination, { props: { page: 2, totalPages: 5, onPageChange } });
		await fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
		expect(onPageChange).toHaveBeenCalledWith(3);
	});

	it('renders the compact control without numbered pages', () => {
		render(Pagination, {
			props: { page: 1, totalPages: 3, onPageChange: vi.fn(), variant: 'compact' },
		});
		expect(screen.getByText('Page 1 of 3')).toBeInTheDocument();
		expect(screen.queryByRole('button', { name: 'Page 2' })).not.toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled();
	});

	it('calls onPageChange from the compact control', async () => {
		const onPageChange = vi.fn();
		render(Pagination, {
			props: { page: 2, totalPages: 3, onPageChange, variant: 'compact' },
		});
		await fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
		expect(onPageChange).toHaveBeenCalledWith(3);
	});

	it('uses the provided aria label', () => {
		render(Pagination, {
			props: {
				page: 1,
				totalPages: 2,
				onPageChange: vi.fn(),
				ariaLabel: 'Archive pages',
			},
		});
		expect(screen.getByRole('navigation', { name: 'Archive pages' })).toBeInTheDocument();
	});
});
