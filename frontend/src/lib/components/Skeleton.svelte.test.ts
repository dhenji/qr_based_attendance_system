import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import Skeleton from './Skeleton.svelte';

describe('Skeleton', () => {
	it('renders with default line variant', () => {
		const { container } = render(Skeleton);
		expect(container.querySelector('.skeleton-line')).not.toBeNull();
	});

	it('supports block variant', () => {
		const { container } = render(Skeleton, { props: { variant: 'block' } });
		expect(container.querySelector('.skeleton-block')).not.toBeNull();
	});

	it('supports circle variant', () => {
		const { container } = render(Skeleton, { props: { variant: 'circle' } });
		expect(container.querySelector('.skeleton-circle')).not.toBeNull();
	});

	it('applies numeric width/height as px', () => {
		const { container } = render(Skeleton, { props: { width: 10, height: 20 } });
		const el = container.querySelector('.skeleton') as HTMLElement;
		expect(el.style.width).toBe('10px');
		expect(el.style.height).toBe('20px');
	});

	it('is aria-hidden', () => {
		const { container } = render(Skeleton);
		expect(container.querySelector('.skeleton')?.getAttribute('aria-hidden')).toBe('true');
	});
});