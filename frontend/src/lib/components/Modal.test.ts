import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import ModalWrapper from '../../testing/ModalWrapper.svelte';

describe('Modal', () => {
	it('renders title and children', () => {
		render(ModalWrapper);
		expect(screen.getByText('Test dialog')).toBeInTheDocument();
		expect(screen.getByText('Modal body content')).toBeInTheDocument();
	});

	it('has dialog role and aria-modal', () => {
		render(ModalWrapper);
		const dialog = screen.getByRole('dialog');
		expect(dialog.getAttribute('aria-modal')).toBe('true');
	});

	it('renders footer when provided', () => {
		render(ModalWrapper, { props: { showFooter: true } });
		expect(screen.getByText('OK')).toBeInTheDocument();
	});

	it('omits footer when not provided', () => {
		render(ModalWrapper);
		expect(screen.queryByText('OK')).not.toBeInTheDocument();
	});

	it('calls onclose on Escape via trapFocus', async () => {
		const onclose = vi.fn();
		render(ModalWrapper, { props: { onclose } });
		const dialog = screen.getByRole('dialog');
		dialog.focus();
		await fireEvent.keyDown(dialog, { key: 'Escape' });
		expect(onclose).toHaveBeenCalled();
	});

	it('backdrop click closes only when closeOnBackdrop', async () => {
		const onclose = vi.fn();
		render(ModalWrapper, { props: { onclose, closeOnBackdrop: true } });
		const overlay = screen.getByRole('dialog').parentElement as HTMLElement;
		await fireEvent.click(overlay);
		expect(onclose).toHaveBeenCalled();
	});

	it('backdrop click does not close by default', async () => {
		const onclose = vi.fn();
		render(ModalWrapper, { props: { onclose } });
		const overlay = screen.getByRole('dialog').parentElement as HTMLElement;
		await fireEvent.click(overlay);
		expect(onclose).not.toHaveBeenCalled();
	});
});