import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import AcademicYearPicker from './AcademicYearPicker.svelte';

describe('AcademicYearPicker', () => {
	it('renders a select with canonical year ranges', () => {
		const { container } = render(AcademicYearPicker, { props: { value: '' } });
		const select = container.querySelector('select');
		expect(select).not.toBeNull();
		const options = Array.from(select!.querySelectorAll('option')).map((o) => o.value);
		expect(options.every((v) => /^\d{4}-\d{4}$/.test(v))).toBe(true);
		expect(options.length).toBeGreaterThan(0);
	});

	it('keeps a non-canonical selection representable', () => {
		const { container } = render(AcademicYearPicker, { props: { value: '2020' } });
		const select = container.querySelector('select') as HTMLSelectElement;
		const values = Array.from(select.querySelectorAll('option')).map((o) => (o as HTMLOptionElement).value);
		expect(values).toContain('2020');
	});
});