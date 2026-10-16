// shared/utils/schedule.ts
// Pure schedule math shared by the offering create surfaces (the Setup
// Wizard step 3 and the Offerings page modal). No Svelte, no I/O — every
// function is a pure computation over plain data, so the rules below can
// be verified by execution (see the wizard/modal submit paths that call
// them) without rendering anything.
//
// Counting rule (also documented in api-contracts.md): one session per
// meeting entry. Entries are single-day, so a Monday lecture plus a
// Wednesday lab counts 2 sessions/week. Weekly hours are Σ duration
// (one day each).

export interface ScheduleMeetingLike {
	schedule_days: string;
	schedule_start_time: string;
	schedule_end_time: string;
}

const DAY_LETTERS = /[A-Z]/g;
const TIME_RE = /^([01]\d|2[0-3]):([0-5]\d)(:([0-5]\d))?$/;

export const parseTimeToMinutes = (value: string): number | null => {
	const match = TIME_RE.exec(value.trim());
	if (!match) return null;
	return Number(match[1]) * 60 + Number(match[2]);
};

// Distinct day letters in a compact days string ("MWF" -> 3). Upper-cased
// and de-duplicated so legacy free text cannot inflate the count.
export const distinctDayCount = (days: string): number =>
	new Set(days.toUpperCase().match(DAY_LETTERS) ?? []).size;

export const meetingDurationMinutes = (start: string, end: string): number | null => {
	const from = parseTimeToMinutes(start);
	const to = parseTimeToMinutes(end);
	if (from === null || to === null || to <= from) return null;
	return to - from;
};

// Total scheduled hours per week across meetings. Rows with invalid or
// end-before-start times contribute nothing (validation reports those
// separately); the result is rounded to two decimals.
export const weeklyMeetingHours = (rows: ScheduleMeetingLike[]): number => {
	let total = 0;
	for (const row of rows) {
		const minutes = meetingDurationMinutes(row.schedule_start_time, row.schedule_end_time);
		if (minutes === null) continue;
		total += (minutes / 60) * distinctDayCount(row.schedule_days);
	}
	return Math.round(total * 100) / 100;
};

// Sessions per week is the meeting entry count (entries are single-day, so
// one entry is exactly one weekly session). Callers pass `rows.length`
// directly — no helper needed.

// Total expected sessions for the term — the same product the risk batch
// uses (semester_weeks × sessions_per_week). Null until both inputs hold
// positive integers, so the UI shows a placeholder instead of NaN.
export const totalExpectedSessions = (
	sessionsPerWeek: string,
	semesterWeeks: string
): number | null => {
	const perWeek = Number(sessionsPerWeek);
	const weeks = Number(semesterWeeks);
	if (!Number.isInteger(perWeek) || perWeek <= 0) return null;
	if (!Number.isInteger(weeks) || weeks <= 0) return null;
	return perWeek * weeks;
};

export interface MeetingOverlap {
	a: number;
	b: number;
	days: string;
}

// Same-day time intersections between meeting rows (any types). The backend
// permits overlaps — there is no overlap guard server-side — so this is UI
// guidance only and must never block a submit.
export const findOverlappingMeetings = (rows: ScheduleMeetingLike[]): MeetingOverlap[] => {
	const parsed = rows.map((row) => ({
		days: new Set(row.schedule_days.toUpperCase().match(DAY_LETTERS) ?? []),
		from: parseTimeToMinutes(row.schedule_start_time),
		to: parseTimeToMinutes(row.schedule_end_time),
	}));
	const overlaps: MeetingOverlap[] = [];
	for (let i = 0; i < parsed.length; i += 1) {
		const left = parsed[i];
		if (left.days.size === 0 || left.from === null || left.to === null || left.to <= left.from)
			continue;
		for (let j = i + 1; j < rows.length; j += 1) {
			const right = parsed[j];
			if (
				right.days.size === 0 ||
				right.from === null ||
				right.to === null ||
				right.to <= right.from
			)
				continue;
			const shared = [...left.days].filter((day) => right.days.has(day)).sort();
			if (shared.length > 0 && left.from < right.to && right.from < left.to) {
				overlaps.push({ a: i, b: j, days: shared.join('') });
			}
		}
	}
	return overlaps;
}

export interface MeetingDuplicate {
	index: number;
	first: number;
}

// Exact-duplicate rows per the backend unique key (session_type,
// schedule_days, schedule_start_time). Rows with blank days/start cannot
// be judged — callers must only pass schema-valid rows.
export const findDuplicateMeetings = (
	rows: { session_type: string; schedule_days: string; schedule_start_time: string }[]
): MeetingDuplicate[] => {
	const seen = new Map<string, number>();
	const duplicates: MeetingDuplicate[] = [];
	rows.forEach((row, index) => {
		const days = row.schedule_days.trim().toUpperCase();
		const start = row.schedule_start_time.trim();
		if (!days || !start) return;
		const key = [row.session_type, days, start].join('|');
		const first = seen.get(key);
		if (first === undefined) {
			seen.set(key, index);
		} else {
			duplicates.push({ index, first });
		}
	});
	return duplicates;
};
