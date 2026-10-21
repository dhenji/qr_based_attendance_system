// shared/utils/schedule.ts
// Pure schedule math shared by the offering create surfaces (the Setup
// Wizard step 3 and the Offerings page modal). No Svelte, no I/O — every
// function is a pure computation over plain data, so the rules below can
// be verified by execution (see the wizard/modal submit paths that call
// them) without rendering anything.
//
// Counting rule (also documented in api-contracts.md): one session per
// meeting day. A Monday lecture plus a Wednesday lab counts 2 sessions/week,
// and one MWF row counts 3. Weekly hours are Σ duration × day count.
//
// The two display helpers at the bottom turn the same wire values into
// readable text (day names, a 12-hour clock) for surfaces that show a
// schedule rather than edit one.

import { DAY_OPTIONS } from '$lib/shared/constants/days';

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

export interface WeeklyHoursBreakdown {
	/** Σ meeting durations in hours/week, rounded to two decimals. */
	scheduled: number;
	/** Course units requirement in hours/week (1 unit = 1 hour). */
	limit: number;
	/** limit − scheduled, rounded to two decimals (negative when over). */
	remaining: number;
	/** True when scheduled exceeds the requirement. */
	over: boolean;
	/** True when scheduled falls short of the requirement. */
	under: boolean;
	/** Minute-rounded verdict: 'ok' when the total matches the requirement. */
	status: 'ok' | 'over' | 'under';
}

// Weekly total against the course units requirement (D79): units are the
// required scheduled meeting hours per week. Pure, so both offering create
// surfaces and the offering detail page share it with the backend rule
// (`_check_weekly_hours` in course/service.py). Comparison is in whole
// minutes — meeting durations are minute-precise times an integer day count,
// so rounding here only absorbs float dust, never a real deviation.
export const weeklyHoursBreakdown = (
	rows: ScheduleMeetingLike[],
	units: number | null | undefined
): WeeklyHoursBreakdown | null => {
	if (units === null || units === undefined || !Number.isFinite(units)) return null;
	const scheduled = weeklyMeetingHours(rows);
	const limit = Math.round(units * 100) / 100;
	const remaining = Math.round((limit - scheduled) * 100) / 100;
	const status =
		Math.round(scheduled * 60) === Math.round(limit * 60)
			? ('ok' as const)
			: scheduled > limit
				? ('over' as const)
				: ('under' as const);
	return { scheduled, limit, remaining, over: status === 'over', under: status === 'under', status };
};

// Whether a schedule write must be blocked (D79). `oldScheduled` is the
// current active-set total, or null when there is none (offering creation:
// the payload is the whole schedule, so it must match exactly).
// Grandfathered or mid-build totals off the requirement may only converge:
// strictly closer without crossing to the other side. Mirrors
// `_check_weekly_hours` — keep the two in sync.
export const weeklyWriteBlocked = (
	oldScheduled: number | null | undefined,
	newScheduled: number,
	limit: number
): boolean => {
	const limMin = Math.round(limit * 60);
	const newMin = Math.round(newScheduled * 60);
	if (newMin === limMin) return false;
	if (oldScheduled === null || oldScheduled === undefined || !Number.isFinite(oldScheduled))
		return true;
	const oldMin = Math.round(oldScheduled * 60);
	if (oldMin === limMin) return true;
	const sameSide = (newMin - limMin) * (oldMin - limMin) > 0;
	return !(sameSide && Math.abs(newMin - limMin) < Math.abs(oldMin - limMin));
};

// Weekly session count: one session per meeting day, so a multi-day row
// counts each of its days (MWF is 3 sessions). The Setup Wizard rows are
// single-day, so there it reduces to the row count; the offering detail
// reuses this for multi-day rows. It only ever sums integer day counts.
export const weeklySessionCount = (rows: ScheduleMeetingLike[]): number =>
	rows.reduce((total, row) => total + distinctDayCount(row.schedule_days), 0);

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

// --- Display helpers --------------------------------------------------------

// Day letters -> day names, in the canonical week order, using the one
// shared list in `shared/constants/days.ts`. Those are the same single-letter
// codes the backend reads (`shared/schedule.py::DAY_WEEKDAYS`, where T is
// Tuesday and H is Thursday because T was taken), so the names here match
// what the server stored without a second mapping.
//
// Unknown letters are ignored, and the result follows the calendar rather
// than the raw string, so "FMW" reads Monday, Wednesday, Friday.
export const dayLabels = (days: string): string[] => {
	const wanted = new Set(days.toUpperCase().match(DAY_LETTERS) ?? []);
	return DAY_OPTIONS.filter((day) => wanted.has(day.code)).map((day) => day.label);
};

// Institution wall clock ("09:00:00") -> a readable 12-hour clock ("9:00 AM").
// Class times are naive wall clock in `INSTITUTION_TIMEZONE`, not instants,
// so they are formatted and never converted. An unparsable value is returned
// unchanged rather than replaced by a guess.
export const formatWallClock = (value: string): string => {
	const match = TIME_RE.exec(value.trim());
	if (!match) return value.trim();
	const hour = Number(match[1]);
	const suffix = hour >= 12 ? 'PM' : 'AM';
	const hour12 = hour % 12 === 0 ? 12 : hour % 12;
	return `${hour12}:${match[2]} ${suffix}`;
};
