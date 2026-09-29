// features/admin/programs/mock.ts
// Mock fixtures for program management UI work. Only consulted when
// PUBLIC_MOCK_MODE=true (api/client.ts); real API calls by default.

import type { Program, YearLevel } from '$lib/shared/types';

export const mockPrograms: Program[] = [
	{
		id: 1,
		code: 'BSCS',
		name: 'BS Computer Science',
		totalYears: 4,
		isActive: true,
		courseCount: 24,
		yearLevelCount: 4,
		termsCount: 9,
		createdAt: new Date().toISOString(),
		updatedAt: new Date().toISOString(),
	},
	{
		id: 2,
		code: 'BSIT',
		name: 'BS Information Technology',
		totalYears: 4,
		isActive: true,
		courseCount: 20,
		yearLevelCount: 4,
		termsCount: 8,
		createdAt: new Date().toISOString(),
		updatedAt: new Date().toISOString(),
	},
];

export const mockYearLevels: YearLevel[] = [
	{
		id: 1,
		programId: 1,
		yearNumber: 1,
		label: '1st Year',
		terms: [
			{ code: '1st', label: '1st Semester' },
			{ code: '2nd', label: '2nd Semester' },
		],
		sortOrder: 1,
	},
	{
		id: 2,
		programId: 1,
		yearNumber: 2,
		label: '2nd Year',
		terms: [
			{ code: '1st', label: '1st Semester' },
			{ code: '2nd', label: '2nd Semester' },
		],
		sortOrder: 2,
	},
];
