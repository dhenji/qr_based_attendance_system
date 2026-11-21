import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { debounce, SEARCH_DEBOUNCE_MS } from './debounce';

describe('debounce', () => {
	beforeEach(() => {
		vi.useFakeTimers();
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('runs only after the configured delay', () => {
		const fn = vi.fn();
		const run = debounce(fn, 100);

		run();
		vi.advanceTimersByTime(99);
		expect(fn).not.toHaveBeenCalled();

		vi.advanceTimersByTime(1);
		expect(fn).toHaveBeenCalledTimes(1);
	});

	it('collapses rapid calls and keeps the latest arguments', () => {
		const fn = vi.fn((_value: string) => {});
		const run = debounce(fn, 100);

		run('first');
		vi.advanceTimersByTime(50);
		run('second');
		vi.advanceTimersByTime(99);
		expect(fn).not.toHaveBeenCalled();

		vi.advanceTimersByTime(1);
		expect(fn).toHaveBeenCalledTimes(1);
		expect(fn).toHaveBeenCalledWith('second');
	});

	it('preserves multiple callback arguments', () => {
		const fn = vi.fn((_page: number, _term: string) => {});
		const run = debounce(fn, 100);

		run(2, 'roster');
		vi.advanceTimersByTime(100);

		expect(fn).toHaveBeenCalledWith(2, 'roster');
	});

	it('cancel prevents a pending call', () => {
		const fn = vi.fn();
		const run = debounce(fn, 100);

		run();
		run.cancel();
		vi.advanceTimersByTime(1000);

		expect(fn).not.toHaveBeenCalled();
	});

	it('can be scheduled again after running', () => {
		const fn = vi.fn();
		const run = debounce(fn, 100);

		run();
		vi.advanceTimersByTime(100);
		run();
		vi.advanceTimersByTime(100);

		expect(fn).toHaveBeenCalledTimes(2);
	});

	it('uses SEARCH_DEBOUNCE_MS by default', () => {
		const fn = vi.fn();
		const run = debounce(fn);

		run();
		vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS - 1);
		expect(fn).not.toHaveBeenCalled();

		vi.advanceTimersByTime(1);
		expect(fn).toHaveBeenCalledTimes(1);
	});

	it('cancel is safe to call repeatedly', () => {
		const fn = vi.fn();
		const run = debounce(fn, 100);

		run.cancel();
		run.cancel();
		run();
		run.cancel();
		vi.advanceTimersByTime(1000);

		expect(fn).not.toHaveBeenCalled();
	});
});
