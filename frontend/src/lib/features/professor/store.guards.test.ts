import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { ProfessorCourseSummary } from '$lib/shared/types';

const { listCoursesMock } = vi.hoisted(() => ({ listCoursesMock: vi.fn() }));

vi.mock('$lib/features/professor/service', () => ({
	getProfile: vi.fn(),
	listCourses: listCoursesMock
}));

import { initProfessorCourses, professorState, resetProfessorState } from './store.svelte';

function deferred<T>() {
	let resolve!: (value: T) => void;
	let reject!: (reason?: unknown) => void;
	const promise = new Promise<T>((res, rej) => {
		resolve = res;
		reject = rej;
	});
	return { promise, resolve, reject };
}

describe('professor course load stale-response guard', () => {
	beforeEach(() => {
		resetProfessorState();
		listCoursesMock.mockReset();
	});

	it('keeps the newest course list when an older request resolves later', async () => {
		const older = deferred<ProfessorCourseSummary[]>();
		const newer = deferred<ProfessorCourseSummary[]>();
		listCoursesMock.mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise);

		const first = initProfessorCourses();
		const second = initProfessorCourses();

		newer.resolve([{ offering_id: 2 } as never]);
		await second;
		older.resolve([{ offering_id: 1 } as never]);
		await first;

		expect(professorState.courses).toEqual([{ offering_id: 2 }]);
		expect(professorState.coursesLoading).toBe(false);
	});

	it('ignores a stale rejection', async () => {
		const older = deferred<ProfessorCourseSummary[]>();
		const newer = deferred<ProfessorCourseSummary[]>();
		listCoursesMock.mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise);

		const first = initProfessorCourses();
		const second = initProfessorCourses();

		newer.resolve([{ offering_id: 2 } as never]);
		await second;
		older.reject(new Error('stale network failure'));
		await first;

		expect(professorState.coursesError).toBeNull();
		expect(professorState.courses).toEqual([{ offering_id: 2 }]);
	});
});
