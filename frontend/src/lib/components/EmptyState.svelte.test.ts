import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import EmptyState from './EmptyState.svelte';

describe('EmptyState', () => {
	it('renders the title', () => {
		render(EmptyState, { props: { title: 'Nothing here' } });
		expect(screen.getByText('Nothing here')).toBeInTheDocument();
	});

	it('renders hint when provided', () => {
		render(EmptyState, { props: { title: 'T', hint: 'some hint' } });
		expect(screen.getByText('some hint')).toBeInTheDocument();
	});

	it('omits hint when not provided', () => {
		render(EmptyState, { props: { title: 'T' } });
		expect(screen.queryByText('some hint')).not.toBeInTheDocument();
	});

	it('does not render actions container when no children', () => {
		const { container } = render(EmptyState, { props: { title: 'T' } });
		expect(container.querySelector('.actions')).toBeNull();
	});
});