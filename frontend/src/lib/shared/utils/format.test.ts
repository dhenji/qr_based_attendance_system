import { describe, it, expect } from 'vitest';
import {
	formatDate,
	formatTime,
	formatPercentage,
	formatTimestamp,
	formatLocalDateTime,
	formatLocalDate,
	formatUTCTimestamp,
	ordinal,
	yearLabel,
	formatBytes,
	type LocalDateTimeFormatOptions
} from './format';

// A local Date, so the assertions do not depend on the machine timezone.
const sample = new Date(2026, 8, 22, 10, 30, 5);

const LONG_DATE: Intl.DateTimeFormatOptions = {
	weekday: 'long',
	year: 'numeric',
	month: 'long',
	day: 'numeric'
};
const SHORT_DATE: Intl.DateTimeFormatOptions = {
	weekday: 'short',
	year: 'numeric',
	month: 'short',
	day: 'numeric'
};
const SHORT_WEEKDAY: Intl.DateTimeFormatOptions = {
	weekday: 'short',
	month: 'short',
	day: 'numeric'
};
const MONTH_YEAR: Intl.DateTimeFormatOptions = { month: 'short', year: 'numeric' };
const MONTH_DAY: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' };
const CLOCK: Intl.DateTimeFormatOptions = { hour: 'numeric', minute: '2-digit' };
const CLOCK_2_DIGIT: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit' };

describe('format', () => {
	it('formatDate returns — for invalid', () => {
		expect(formatDate('not-a-date')).toBe('—');
	});
	it('formatDate returns a string for valid', () => {
		expect(typeof formatDate('2026-09-22T10:30:00Z')).toBe('string');
		expect(formatDate('2026-09-22T10:30:00Z')).not.toBe('—');
	});
	it('formatTime returns — for invalid', () => {
		expect(formatTime('x')).toBe('—');
	});
	it('formatPercentage rounds and appends %', () => {
		expect(formatPercentage(42.4)).toBe('42%');
		expect(formatPercentage(42.6)).toBe('43%');
	});
	it('formatTimestamp returns UTC-ish string', () => {
		expect(formatTimestamp('2026-09-22T10:30:00Z')).toBe('2026-09-22 10:30:00');
		expect(formatTimestamp('bad')).toBe('—');
	});
	it('formatLocalDateTime returns — for invalid', () => {
		expect(formatLocalDateTime('bad')).toBe('—');
	});
	it('formatLocalDate returns — for invalid', () => {
		expect(formatLocalDate('bad')).toBe('—');
	});
	it('formatUTCTimestamp appends UTC', () => {
		expect(formatUTCTimestamp('2026-09-22T10:30:00Z')).toContain('UTC');
		expect(formatUTCTimestamp('bad')).toBe('—');
	});
	it('ordinal handles teens and units', () => {
		expect(ordinal(1)).toBe('1st');
		expect(ordinal(2)).toBe('2nd');
		expect(ordinal(3)).toBe('3rd');
		expect(ordinal(11)).toBe('11th');
		expect(ordinal(12)).toBe('12th');
		expect(ordinal(13)).toBe('13th');
		expect(ordinal(21)).toBe('21st');
	});
	it('yearLabel', () => {
		expect(yearLabel(1)).toBe('1st Year');
		expect(yearLabel(2)).toBe('2nd Year');
	});
	it('formatBytes', () => {
		expect(formatBytes(0)).toBe('—');
		expect(formatBytes(NaN)).toBe('—');
		expect(formatBytes(1536)).toBe('1.5 KB');
		expect(formatBytes(500)).toBe('500 B');
	});

	describe('formatLocalDateTime options', () => {
		it('keeps the legacy machine format when no options are given', () => {
			expect(formatLocalDateTime('2026-09-22T10:30:05')).toBe('2026-09-22 10:30:05');
			expect(formatLocalDateTime(sample)).toBe('2026-09-22 10:30:05');
		});

		it('renders a date-only locale string with the supplied options', () => {
			expect(formatLocalDateTime(sample, { date: LONG_DATE })).toBe(
				sample.toLocaleDateString(undefined, LONG_DATE)
			);
		});

		it('renders a short month/year date', () => {
			expect(formatLocalDateTime(sample, { date: MONTH_YEAR })).toBe(
				sample.toLocaleDateString(undefined, MONTH_YEAR)
			);
		});

		it('renders a time-only locale string', () => {
			expect(formatLocalDateTime(sample, { time: CLOCK })).toBe(
				sample.toLocaleTimeString(undefined, CLOCK)
			);
		});

		it('renders a combined date and time string', () => {
			expect(formatLocalDateTime(sample, { date: SHORT_WEEKDAY, time: CLOCK })).toBe(
				`${sample.toLocaleDateString(undefined, SHORT_WEEKDAY)}, ${sample.toLocaleTimeString(undefined, CLOCK)}`
			);
		});

		it('supports a bare default date format', () => {
			expect(formatLocalDateTime(sample, { date: {} })).toBe(sample.toLocaleDateString());
		});

		it('omits a part when it is false', () => {
			expect(formatLocalDateTime(sample, { date: false, time: CLOCK })).toBe(
				sample.toLocaleTimeString(undefined, CLOCK)
			);
			expect(formatLocalDateTime(sample, { date: MONTH_DAY, time: false })).toBe(
				sample.toLocaleDateString(undefined, MONTH_DAY)
			);
		});

		it('supports a custom separator between date and time', () => {
			expect(formatLocalDateTime(sample, { date: MONTH_DAY, time: CLOCK, separator: ' at ' })).toBe(
				`${sample.toLocaleDateString(undefined, MONTH_DAY)} at ${sample.toLocaleTimeString(undefined, CLOCK)}`
			);
		});

		it('returns — for invalid, null, and undefined inputs', () => {
			expect(formatLocalDateTime('bad', { date: {} })).toBe('—');
			expect(formatLocalDateTime(null, { date: {} })).toBe('—');
			expect(formatLocalDateTime(undefined, { date: {} })).toBe('—');
		});
	});

	describe('regression comparisons against the original implementations', () => {
		const cases: Array<{
			name: string;
			options: LocalDateTimeFormatOptions;
			render: (date: Date) => string;
		}> = [
			{
				name: 'long weekday date',
				options: { date: LONG_DATE },
				render: (date) => date.toLocaleDateString(undefined, LONG_DATE)
			},
			{
				name: 'short weekday date with year',
				options: { date: SHORT_DATE },
				render: (date) => date.toLocaleDateString(undefined, SHORT_DATE)
			},
			{
				name: 'short weekday and month/day',
				options: { date: SHORT_WEEKDAY },
				render: (date) => date.toLocaleDateString(undefined, SHORT_WEEKDAY)
			},
			{
				name: 'short month and year',
				options: { date: MONTH_YEAR },
				render: (date) => date.toLocaleDateString(undefined, MONTH_YEAR)
			},
			{
				name: 'short month and day',
				options: { date: MONTH_DAY },
				render: (date) => date.toLocaleDateString(undefined, MONTH_DAY)
			},
			{
				name: 'numeric-hour clock',
				options: { time: CLOCK },
				render: (date) => date.toLocaleTimeString(undefined, CLOCK)
			},
			{
				name: 'two-digit-hour clock',
				options: { time: CLOCK_2_DIGIT },
				render: (date) => date.toLocaleTimeString(undefined, CLOCK_2_DIGIT)
			},
			{
				name: 'combined short date and clock',
				options: { date: SHORT_WEEKDAY, time: CLOCK },
				render: (date) =>
					`${date.toLocaleDateString(undefined, SHORT_WEEKDAY)}, ${date.toLocaleTimeString(undefined, CLOCK)}`
			},
			{
				name: 'bare default date',
				options: { date: {} },
				render: (date) => date.toLocaleDateString()
			}
		];

		for (const { name, options, render } of cases) {
			it(name, () => {
				expect(formatLocalDateTime(sample, options)).toBe(render(sample));
			});
		}
	});
});
