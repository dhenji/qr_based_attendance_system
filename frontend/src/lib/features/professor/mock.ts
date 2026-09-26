// features/professor/mock.ts
// Shared fixture for the professor portal's course assignments.
//
// `GET /professor/courses` is still a prefix-only router stub on the backend
// (features/professor/service.py does not exist yet), so both pages that need
// this data — My Courses and Open Session — read it from here. Kept in its own
// module so the page call sites stay readable, and so there is exactly one
// source of truth for the offering ids the session-create page links against.
// The field set mirrors the GET /professor/courses contract
// (docs/architecture/api-contracts.md) in camelCase, plus the offering columns
// the session-create form needs (D44 moved the window defaults here from
// courses). Swapping in the real endpoint should leave the pages untouched.
export type ProfessorCourse = {
	offeringId: number;
	courseId: number;
	courseCode: string;
	courseName: string;
	units: number;
	programCode: string;
	// year_levels.label is a free-form string; the badge abbreviation is
	// presentation-only and has no contract field behind it.
	yearLevelLabel: string;
	shortYear: string;
	semester: string;
	academicYear: string;
	section: string;
	scheduleDays: string;
	scheduleStartTime: string;
	scheduleEndTime: string;
	// The scheduled class length in minutes. Kept as a field rather than parsed
	// from the two clock strings above, which are display-only. Must stay
	// consistent with them: 9:00 AM - 10:30 AM is 90.
	scheduledMinutes: number;
	classroomName: string | null;
	classroomLat: number | null;
	classroomLng: number | null;
	defaultPresentWindowMinutes: number;
	defaultLateWindowMinutes: number;
	enrolledCount: number;
	// is_primary and the effective range are contract fields but are not
	// rendered on the card: the role carries no consequence there, since per D9
	// a primary and an assistant can both open sessions. They ride along so the
	// endpoint swap stays mechanical.
	isPrimary: boolean;
	effectiveFrom: string;
	effectiveTo: string | null;
	hasActiveSession: boolean;
};

export const PROFESSOR_COURSES: ProfessorCourse[] = [
	{
		offeringId: 1,
		courseId: 1,
		courseCode: 'CS101',
		courseName: 'Software Engineering 1',
		units: 3,
		programCode: 'BSCS',
		yearLevelLabel: '1st Year',
		shortYear: 'Y1',
		semester: '1st Sem',
		academicYear: '2025-2026',
		section: 'A',
		scheduleDays: 'MWF',
		scheduleStartTime: '9:00 AM',
		scheduleEndTime: '10:30 AM',
		scheduledMinutes: 90,
		classroomName: 'Lab 101',
		classroomLat: 14.5995,
		classroomLng: 120.9842,
		defaultPresentWindowMinutes: 5,
		defaultLateWindowMinutes: 10,
		enrolledCount: 30,
		isPrimary: true,
		effectiveFrom: '2025-08-04',
		effectiveTo: null,
		hasActiveSession: true,
	},
	{
		offeringId: 2,
		courseId: 2,
		courseCode: 'MATH202',
		courseName: 'Calculus 2',
		units: 4,
		programCode: 'BSCS',
		yearLevelLabel: '1st Year',
		shortYear: 'Y1',
		semester: '1st Sem',
		academicYear: '2025-2026',
		section: 'A',
		scheduleDays: 'TTH',
		scheduleStartTime: '11:00 AM',
		scheduleEndTime: '12:30 PM',
		scheduledMinutes: 90,
		classroomName: 'Room 203',
		classroomLat: 14.5997,
		classroomLng: 120.9839,
		defaultPresentWindowMinutes: 5,
		defaultLateWindowMinutes: 10,
		enrolledCount: 35,
		isPrimary: true,
		effectiveFrom: '2025-08-04',
		effectiveTo: null,
		hasActiveSession: false,
	},
	{
		offeringId: 3,
		courseId: 1,
		courseCode: 'CS101',
		courseName: 'Software Engineering 1',
		units: 3,
		programCode: 'BSIT',
		yearLevelLabel: '1st Year',
		shortYear: 'Y1',
		semester: '1st Sem',
		academicYear: '2025-2026',
		section: 'B',
		scheduleDays: 'MWF',
		scheduleStartTime: '9:00 AM',
		scheduleEndTime: '10:30 AM',
		scheduledMinutes: 90,
		classroomName: 'Lab 101',
		classroomLat: 14.5995,
		classroomLng: 120.9842,
		defaultPresentWindowMinutes: 5,
		defaultLateWindowMinutes: 10,
		enrolledCount: 25,
		isPrimary: false,
		effectiveFrom: '2025-08-11',
		effectiveTo: null,
		hasActiveSession: false,
	},
];
