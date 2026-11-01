import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import RadiusSelector from './RadiusSelector.svelte';

describe('RadiusSelector', () => {
	it('renders chips for default options within min/max', () => {
		const onChange = vi.fn();
		render(RadiusSelector, { props: { value: 50, min: 10, max: 100, onChange } });
		expect(screen.getByText('50m')).toBeInTheDocument();
	});

	it('marks selected chip', () => {
		const onChange = vi.fn();
		render(RadiusSelector, { props: { value: 50, min: 10, max: 100, onChange } });
		const btn = screen.getByText('50m');
		expect(btn.getAttribute('aria-pressed')).toBe('true');
	});

	it('calls onChange when a chip is clicked', async () => {
		const onChange = vi.fn();
		render(RadiusSelector, { props: { value: 50, min: 10, max: 100, onChange } });
		await fireEvent.click(screen.getByText('30m'));
		expect(onChange).toHaveBeenCalledWith(30);
	});

	it('renders default chip when label provided', () => {
		const onChange = vi.fn();
		const onDefault = vi.fn();
		render(RadiusSelector, {
			props: { value: 50, min: 10, max: 100, onChange, defaultChipLabel: 'System default', defaultValue: 50, onDefault }
		});
		expect(screen.getByText('System default')).toBeInTheDocument();
	});

	it('disables all chips when disabled', () => {
		const onChange = vi.fn();
		render(RadiusSelector, { props: { value: 50, min: 10, max: 100, onChange, disabled: true } });
		for (const btn of screen.getAllByRole('button')) {
			expect(btn).toBeDisabled();
		}
	});
});