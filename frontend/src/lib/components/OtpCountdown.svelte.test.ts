import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import OtpCountdown from './OtpCountdown.svelte';

describe('OtpCountdown', () => {
	it('renders expiry text', () => {
		render(OtpCountdown, { props: { remaining: 300 } });
		expect(screen.getByText(/Expires in/)).toBeInTheDocument();
	});

	it('shows expired styling at zero', () => {
		const { container } = render(OtpCountdown, { props: { remaining: 0 } });
		expect(container.querySelector('.expired')).not.toBeNull();
	});

	it('defaults remaining to 300', () => {
		render(OtpCountdown);
		expect(screen.getByText(/Expires in/)).toBeInTheDocument();
	});
});