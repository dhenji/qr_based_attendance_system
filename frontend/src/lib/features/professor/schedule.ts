// features/professor/schedule.ts
// Resolve an offering's recurring schedule to the next valid class meeting.
//
// The fixture stores recurring patterns such as MWF 9:00-10:30 AM. Anchoring
// those times blindly to "today" can select a meeting that already ended—or a
// weekday on which the class never meets. This resolver returns the first
// meeting whose end is after the supplied moment, preserving D12's scheduled
// end ceiling without creating an instantly expired session.

import type { ProfessorCourse } from '$lib/features/professor/mock';

export type ClassMeeting = {
	start: Date;
	end: Date;
};

type CourseSchedule = Pick<
	ProfessorCourse,
	'scheduleDays' | 'scheduleStartTime' | 'scheduleEndTime'
>;

// JavaScript Date weekdays: Sunday is 0 through Saturday is 6.
const WEEKDAYS: Record<string, number> = {
	SU: 0,
	M: 1,
	T: 2,
	W: 3,
	TH: 4,
	F: 5,
	S: 6,
	SA: 6
};

export const parseScheduleDays = (value: string): number[] | null => {
	const days = value.toUpperCase().replace(/\s+/g, '');
	if (days === '') return null;

	const weekdays: number[] = [];
	let index = 0;
	while (index < days.length) {
		const pair = days.slice(index, index + 2);
		const token = pair === 'TH' || pair === 'SU' || pair === 'SA' ? pair : days[index];
		const weekday = WEEKDAYS[token];
		if (weekday === undefined) return null;
		if (!weekdays.includes(weekday)) weekdays.push(weekday);
		index += token.length;
	}

	return weekdays.sort((a, b) => a - b);
};

const parseClockTime = (value: string): { hours: number; minutes: number } | null => {
	const match = value.trim().toUpperCase().match(/^(\d{1,2}):(\d{2})\s*(AM|PM)$/);
	if (!match) return null;

	let hours = Number(match[1]);
	const minutes = Number(match[2]);
	if (hours < 1 || hours > 12 || minutes < 0 || minutes > 59) return null;
	if (match[3] === 'PM' && hours < 12) hours += 12;
	if (match[3] === 'AM' && hours === 12) hours = 0;

	return { hours, minutes };
};

const atTime = (day: Date, hours: number, minutes: number): Date => {
	const meeting = new Date(day);
	meeting.setHours(hours, minutes, 0, 0);
	return meeting;
};

export const resolveNextClassMeeting = (
	course: CourseSchedule,
	from: Date = new Date(),
	horizonDays = 14
): ClassMeeting | null => {
	const weekdays = parseScheduleDays(course.scheduleDays);
	const start = parseClockTime(course.scheduleStartTime);
	const end = parseClockTime(course.scheduleEndTime);
	if (!weekdays || !start || !end || horizonDays <= 0) return null;

	for (let offset = 0; offset < horizonDays; offset += 1) {
		const day = new Date(from);
		day.setDate(from.getDate() + offset);
		if (!weekdays.includes(day.getDay())) continue;

		const meetingStart = atTime(day, start.hours, start.minutes);
		const meetingEnd = atTime(day, end.hours, end.minutes);
		// Overnight meetings end on the following calendar day.
		if (meetingEnd.getTime() <= meetingStart.getTime()) {
			meetingEnd.setDate(meetingEnd.getDate() + 1);
		}

		// A meeting already in progress is usable; one that has ended is not.
		if (meetingEnd.getTime() > from.getTime()) return { start: meetingStart, end: meetingEnd };
	}

	return null;
};
