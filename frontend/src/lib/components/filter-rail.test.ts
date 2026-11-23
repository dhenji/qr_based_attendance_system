import { describe, it, expect } from 'vitest';
import { presetDateRange } from './filter-rail';

// Wednesday 25 November 2026, local time. Using local date parts keeps the
// assertions independent of the machine's timezone.
const now = new Date(2026, 10, 25, 12, 0, 0);

describe('presetDateRange', () => {
	it('resolves today to a single local day', () => {
		expect(presetDateRange('today', now)).toEqual({ from: '2026-11-25', to: '2026-11-25' });
	});

	it('starts the week on Sunday', () => {
		expect(presetDateRange('week', now)).toEqual({ from: '2026-11-22', to: '2026-11-25' });
	});

	it('starts the month on its first day', () => {
		expect(presetDateRange('month', now)).toEqual({ from: '2026-11-01', to: '2026-11-25' });
	});

	it('starts the year on January 1', () => {
		expect(presetDateRange('year', now)).toEqual({ from: '2026-01-01', to: '2026-11-25' });
	});

	it('clears both bounds for all time', () => {
		expect(presetDateRange('all', now)).toEqual({ from: '', to: '' });
	});
});
