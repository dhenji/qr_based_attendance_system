import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { AdminProfessor, AdminStudent } from '$lib/shared/types';

const { listStudentsMock, listProfessorsMock } = vi.hoisted(() => ({
	listStudentsMock: vi.fn(),
	listProfessorsMock: vi.fn()
}));

vi.mock('$lib/features/admin/service', () => ({
	listStudents: listStudentsMock,
	listProfessors: listProfessorsMock,
	setStudentActive: vi.fn(),
	setProfessorActive: vi.fn(),
	hardDeleteStudent: vi.fn(),
	hardDeleteProfessor: vi.fn(),
	listUsers: vi.fn(),
	deactivateUser: vi.fn(),
	reactivateUser: vi.fn()
}));

import {
	adminProfessorsState,
	adminStudentsState,
	initAdminProfessors,
	initAdminStudents,
	resetAdminRosterStates
} from './store.svelte';

type StudentPage = {
	items: AdminStudent[];
	total: number;
	page: number;
	size: number;
};

type ProfessorPage = {
	items: AdminProfessor[];
	total: number;
	page: number;
	size: number;
};

// Minimal stand-ins: the store only reads these four fields.
const studentPage = (page: number): StudentPage => ({
	items: [{ id: page } as unknown as AdminStudent],
	total: page,
	page,
	size: 20
});

const professorPage = (page: number): ProfessorPage => ({
	items: [{ id: page } as unknown as AdminProfessor],
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

describe('admin roster stale-response guards', () => {
	beforeEach(() => {
		resetAdminRosterStates();
		listStudentsMock.mockReset();
		listProfessorsMock.mockReset();
	});

	it('lets a newer student request win when an older one resolves later', async () => {
		const older = deferred<StudentPage>();
		const newer = deferred<StudentPage>();
		listStudentsMock.mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise);

		const first = initAdminStudents({ is_active: false }, 1, 20);
		const second = initAdminStudents({ is_active: false }, 2, 20);

		newer.resolve(studentPage(2));
		await second;
		older.resolve(studentPage(1));
		await first;

		expect(adminStudentsState.items).toEqual([{ id: 2 }]);
		expect(adminStudentsState.page).toBe(2);
		expect(adminStudentsState.loading).toBe(false);
	});

	it('does not clear the loading flag for a superseded student request', async () => {
		const older = deferred<StudentPage>();
		const newer = deferred<StudentPage>();
		listStudentsMock.mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise);

		const first = initAdminStudents({}, 1, 20);
		const second = initAdminStudents({}, 2, 20);

		older.resolve(studentPage(1));
		await first;
		expect(adminStudentsState.loading).toBe(true);

		newer.resolve(studentPage(2));
		await second;
		expect(adminStudentsState.loading).toBe(false);
	});

	it('ignores a stale student rejection instead of overwriting the current rows', async () => {
		const older = deferred<StudentPage>();
		const newer = deferred<StudentPage>();
		listStudentsMock.mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise);

		const first = initAdminStudents({}, 1, 20);
		const second = initAdminStudents({}, 2, 20);

		newer.resolve(studentPage(2));
		await second;
		older.reject(new Error('stale network failure'));
		await first;

		expect(adminStudentsState.error).toBeNull();
		expect(adminStudentsState.items).toEqual([{ id: 2 }]);
	});

	it('lets a newer professor request win when an older one resolves later', async () => {
		const older = deferred<ProfessorPage>();
		const newer = deferred<ProfessorPage>();
		listProfessorsMock.mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise);

		const first = initAdminProfessors({ is_active: false }, 1, 20);
		const second = initAdminProfessors({ is_active: false }, 2, 20);

		newer.resolve(professorPage(2));
		await second;
		older.resolve(professorPage(1));
		await first;

		expect(adminProfessorsState.items).toEqual([{ id: 2 }]);
		expect(adminProfessorsState.page).toBe(2);
	});
});
