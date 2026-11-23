import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { Program } from '$lib/shared/types';

const { listProgramsMock } = vi.hoisted(() => ({ listProgramsMock: vi.fn() }));

vi.mock('$lib/features/admin/programs/service', () => ({
	listPrograms: listProgramsMock,
	deleteProgram: vi.fn(),
	deleteYearLevel: vi.fn(),
	getProgram: vi.fn(),
	setProgramActive: vi.fn()
}));

import {
	adminProgramsState,
	initAdminPrograms,
	resetAdminProgramsStates
} from './store.svelte';

type ProgramPage = {
	items: Program[];
	total: number;
	page: number;
	size: number;
};

const programPage = (page: number): ProgramPage => ({
	items: [{ id: page } as unknown as Program],
	total: page,
	page,
	size: 20
});

function deferred<T>() {
	let resolve!: (value: T) => void;
	let reject!: (reason?: unknown) => void;
	const promise = new Promise<T>((res, rej) => {
		resolve = res;
		reject = rej;
	});
	return { promise, resolve, reject };
}

describe('programs list stale-response guard', () => {
	beforeEach(() => {
		resetAdminProgramsStates();
		listProgramsMock.mockReset();
	});

	it('keeps the newest program page when an older request resolves later', async () => {
		const older = deferred<ProgramPage>();
		const newer = deferred<ProgramPage>();
		listProgramsMock.mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise);

		const first = initAdminPrograms({ is_active: false }, 1, 20);
		const second = initAdminPrograms({ is_active: false }, 2, 20);

		newer.resolve(programPage(2));
		await second;
		older.resolve(programPage(1));
		await first;

		expect(adminProgramsState.items).toEqual([{ id: 2 }]);
		expect(adminProgramsState.page).toBe(2);
		expect(adminProgramsState.loading).toBe(false);
	});

	it('ignores a stale rejection', async () => {
		const older = deferred<ProgramPage>();
		const newer = deferred<ProgramPage>();
		listProgramsMock.mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise);

		const first = initAdminPrograms({}, 1, 20);
		const second = initAdminPrograms({}, 2, 20);

		newer.resolve(programPage(2));
		await second;
		older.reject(new Error('stale network failure'));
		await first;

		expect(adminProgramsState.error).toBeNull();
		expect(adminProgramsState.items).toEqual([{ id: 2 }]);
	});
});
