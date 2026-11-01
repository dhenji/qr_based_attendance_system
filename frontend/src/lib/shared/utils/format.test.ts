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
	formatBytes
} from './format';

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
});