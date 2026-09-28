// features/admin/mock.ts
// Mock fixtures for admin roster UI work. Only consulted when
// PUBLIC_MOCK_MODE=true (api/client.ts); real API calls by default.

import type { AdminProfessor, AdminStudent } from '$lib/shared/types';

export const mockAdminStudents: AdminStudent[] = [
	{
		id: 1,
		studentId: '2021-001',
		firstName: 'Alice',
		middleName: 'M',
		lastName: 'Santos',
		email: 'alice.santos@isu.edu.ph',
		programCode: 'BSCS',
		yearLevelLabel: '3rd Year',
		section: 'A',
		isActive: true,
		faceEnrolled: true,
		createdAt: new Date().toISOString(),
		scanCount: 42,
	},
	{
		id: 2,
		studentId: '2022-002',
		firstName: 'Bob',
		lastName: 'Cruz',
		email: 'bob.cruz@isu.edu.ph',
		programCode: 'BSIT',
		yearLevelLabel: '2nd Year',
		section: 'B',
		isActive: true,
		faceEnrolled: false,
		createdAt: new Date().toISOString(),
		scanCount: 18,
	},
];

export const mockAdminProfessors: AdminProfessor[] = [
	{
		id: 1,
		first_name: 'John',
		middle_name: 'A',
		last_name: 'Smith',
		email: 'john.smith@isu.edu.ph',
		department: 'Computer Science',
		is_active: true,
		claim_status: 'Claimed',
		assigned_courses: [{ offering_id: 1, course_code: 'CS101' }],
		created_at: new Date().toISOString(),
		firstName: 'John',
		middleName: 'A',
		lastName: 'Smith',
		claimStatus: 'Claimed',
		isActive: true,
		createdAt: new Date().toISOString(),
	},
	{
		id: 2,
		first_name: 'Maria',
		middle_name: null,
		last_name: 'Garcia',
		email: 'maria.garcia@isu.edu.ph',
		department: 'Mathematics',
		is_active: true,
		claim_status: 'Unclaimed',
		assigned_courses: [],
		created_at: new Date().toISOString(),
		firstName: 'Maria',
		lastName: 'Garcia',
		claimStatus: 'Unclaimed',
		isActive: true,
		createdAt: new Date().toISOString(),
	},
];
