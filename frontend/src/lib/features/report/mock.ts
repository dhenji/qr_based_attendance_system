// features/report/mock.ts
// Deterministic historical fixtures for professor reports.
//
// The live session store is mutable and only represents current activity, so it
// cannot back trends or comparisons. These fixtures synthesize completed
// sessions from each offering's recurring schedule. Values are hashed rather
// than random so every tab, filter, chart, table, and CSV export agrees.

import { PROFESSOR_COURSES } from '$lib/features/professor/mock';
import { parseScheduleDays } from '$lib/features/professor/schedule';

export type ReportSessionRecord = {
	sessionId: string;
	offeringId: number;
	courseId: number;
	courseCode: string;
	courseName: string;
	programCode: string;
	yearLevelLabel: string;
	section: string;
	date: string;
	sessionType: 'lecture' | 'lab';
	startTime: string;
	endTime: string;
	enrolled: number;
	present: number;
	late: number;
	excused: number;
	absent: number;
};

const REPORT_HISTORY_DAYS = 90;

const hashText = (value: string): number => {
	let hash = 2166136261;
	for (let index = 0; index < value.length; index += 1) {
		hash ^= value.charCodeAt(index);
		hash = Math.imul(hash, 16777619);
	}
	return hash >>> 0;
};

const unitFromHash = (hash: number, salt: number): number =>
	(((hash + Math.imul(salt, 2654435761)) >>> 0) % 1000) / 1000;

const toLocalDateKey = (date: Date): string =>
	`${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;

const sessionsForOffering = (offeringId: number): ReportSessionRecord[] => {
	const course = PROFESSOR_COURSES.find((item) => item.offeringId === offeringId);
	if (!course) return [];

	const weekdays = parseScheduleDays(course.scheduleDays);
	if (!weekdays) return [];

	const today = new Date();
	today.setHours(0, 0, 0, 0);
	const sessions: ReportSessionRecord[] = [];

	for (let offset = 1; offset <= REPORT_HISTORY_DAYS; offset += 1) {
		const date = new Date(today);
		date.setDate(today.getDate() - offset);
		if (!weekdays.includes(date.getDay())) continue;

		const dateKey = toLocalDateKey(date);
		const seed = hashText(`${offeringId}|${dateKey}`);
		const compliance = Math.min(
			0.97,
			Math.max(0.45, 0.68 + ((seed % 25) / 100) + (unitFromHash(seed, 1) - 0.5) * 0.12)
		);
		const present = Math.round(course.enrolledCount * compliance);
		let remaining = course.enrolledCount - present;
		const late = Math.min(remaining, Math.round(course.enrolledCount * (0.03 + 0.09 * unitFromHash(seed, 2))));
		remaining -= late;
		const excused = Math.min(
			remaining,
			Math.round(course.enrolledCount * (0.02 + 0.05 * unitFromHash(seed, 3)))
		);
		remaining -= excused;

		sessions.push({
			sessionId: `${offeringId}-${dateKey}`,
			offeringId: course.offeringId,
			courseId: course.courseId,
			courseCode: course.courseCode,
			courseName: course.courseName,
			programCode: course.programCode,
			yearLevelLabel: course.yearLevelLabel,
			section: course.section,
			date: dateKey,
			sessionType: 'lecture',
			startTime: course.scheduleStartTime,
			endTime: course.scheduleEndTime,
			enrolled: course.enrolledCount,
			present,
			late,
			excused,
			absent: remaining
		});
	}

	return sessions;
};

export const REPORT_SESSIONS: ReportSessionRecord[] = PROFESSOR_COURSES.flatMap((course) =>
	sessionsForOffering(course.offeringId)
).sort((a, b) => (a.date === b.date ? a.offeringId - b.offeringId : a.date < b.date ? -1 : 1));
