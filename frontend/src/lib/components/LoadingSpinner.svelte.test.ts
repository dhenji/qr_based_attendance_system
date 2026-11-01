import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import LoadingSpinner from './LoadingSpinner.svelte';

describe('LoadingSpinner', () => {
	it('renders inline by default with message', () => {
		const { container } = render(LoadingSpinner);
		expect(container.querySelector('.loading-inline')).not.toBeNull();
		expect(screen.getByText('Loading...')).toBeInTheDocument();
	});

	it('renders fullscreen overlay when requested', () => {
		const { container } = render(LoadingSpinner, { props: { fullscreen: true } });
		expect(container.querySelector('.loading-overlay')).not.toBeNull();
	});

	it('omits message when empty', () => {
		render(LoadingSpinner, { props: { message: '' } });
		expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
	});

	it('applies size class', () => {
		const { container } = render(LoadingSpinner, { props: { size: 'lg' } });
		expect(container.querySelector('.spinner-lg')).not.toBeNull();
	});
});