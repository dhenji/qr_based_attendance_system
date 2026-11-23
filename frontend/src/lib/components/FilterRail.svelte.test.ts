import { describe, it, expect, vi } from 'vitest';
import { createRawSnippet } from 'svelte';
import { render, screen, fireEvent } from '@testing-library/svelte';
import FilterRail from './FilterRail.svelte';
import type { DatePresetId } from './filter-rail';

// The rail renders parent-supplied controls through snippets. `createRawSnippet`
// builds a real snippet whose render output is raw HTML, which is enough to
// assert the shell hands off the snippet slots without asserting parent markup.
const scope = createRawSnippet(() => ({
	render: () => '<div class="field"><span>scope-slot</span></div>'
}));

const advanced = createRawSnippet(() => ({
	render: () => '<div class="field"><span>advanced-slot</span></div>'
}));

const baseProps = () => ({
	scope,
	advanced,
	preset: 'custom' as DatePresetId,
	from: '',
	to: '',
	advancedOpen: false,
	advancedActiveCount: 0,
	idPrefix: 'test',
	onPreset: vi.fn(),
	onFromChange: vi.fn(),
	onToChange: vi.fn(),
	onReset: vi.fn(),
	onAdvancedToggle: vi.fn(),
	onClearAdvanced: vi.fn()
});

describe('FilterRail', () => {
	it('renders the shared scope grid, presets, and date fields', () => {
		render(FilterRail, { props: baseProps() });
		expect(screen.getByText('Scope')).toBeInTheDocument();
		expect(screen.getByText('Time range')).toBeInTheDocument();
		for (const label of ['Today', 'This week', 'This month', 'This year', 'All time']) {
			expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
		}
		expect(screen.getByLabelText('From date')).toBeInTheDocument();
		expect(screen.getByLabelText('To date')).toBeInTheDocument();
		expect(screen.getByText('scope-slot')).toBeInTheDocument();
	});

	it('marks the active preset and reports preset clicks', async () => {
		const props = baseProps();
		props.preset = 'week';
		render(FilterRail, { props });
		const active = screen.getByRole('button', { name: 'This week' });
		expect(active.className).toContain('selected');
		expect(active).toHaveAttribute('aria-pressed', 'true');
		expect(screen.getByRole('button', { name: 'Today' })).toHaveAttribute('aria-pressed', 'false');
		await fireEvent.click(screen.getByRole('button', { name: 'Today' }));
		expect(props.onPreset).toHaveBeenCalledWith('today');
	});

	it('reports from/to edits and reset', async () => {
		const props = baseProps();
		render(FilterRail, { props });
		await fireEvent.change(screen.getByLabelText('From date'), { target: { value: '2026-01-01' } });
		expect(props.onFromChange).toHaveBeenCalledWith('2026-01-01');
		await fireEvent.change(screen.getByLabelText('To date'), { target: { value: '2026-01-31' } });
		expect(props.onToChange).toHaveBeenCalledWith('2026-01-31');
		await fireEvent.click(screen.getByRole('button', { name: 'Reset filters' }));
		expect(props.onReset).toHaveBeenCalledOnce();
	});

	it('reveals the advanced panel with the parent snippet and clear action', async () => {
		const props = baseProps();
		props.advancedOpen = true;
		props.advancedActiveCount = 2;
		render(FilterRail, { props });

		const toggle = screen.getByRole('button', { name: /Advanced filters ?\(2\)/ });
		expect(toggle).toHaveAttribute('aria-expanded', 'true');
		expect(screen.getByText('advanced-slot')).toBeInTheDocument();

		await fireEvent.click(screen.getByRole('button', { name: 'Clear advanced' }));
		expect(props.onClearAdvanced).toHaveBeenCalledOnce();
	});

	it('toggles the advanced panel and keeps aria wiring intact', async () => {
		const props = baseProps();
		render(FilterRail, { props });
		const toggle = screen.getByRole('button', { name: 'Advanced filters' });
		expect(toggle).toHaveAttribute('aria-expanded', 'false');
		await fireEvent.click(toggle);
		expect(props.onAdvancedToggle).toHaveBeenCalledOnce();
	});
});
