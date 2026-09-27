// features/report/service.ts
// Professor-facing report queries over deterministic mock history.
//
// Field names intentionally mirror the professor report contracts in
// docs/architecture/api-contracts.md so the future backend swap stays
// mechanical. The backend will replace these aggregations; the page should not
// need to change.

import { PROFESSOR_COURSES } from '$lib/features/professor/mock';
import { REPORT_SESSIONS, type ReportSessionRecord } from '$lib/features/report/mock';

const MOCK = true;

export type ReportGranularity = 'daily' | 'weekly' | 'monthly';
export type ReportMetric = 'compliance' | 'participation';

export type ReportFilters = {
	program: string;
	year: string;
	course: string;
	section: string;
	from: string;
	to: string;
	granularity: ReportGranularity;
	metric: ReportMetric;
};

export type AggregateBucket = {
	key: string;
	label: string;
	date: string;
	total_sessions: number;
	total_students: number;
	compliance_rate: number;
	participation_rate: number;
};

export type ComparisonRow = {
	course_id: number;
	offering_id: number;
	course_code: string;
	course_name: string;
	program_id: string;
	program_code: string;
	year_level_id: string;
	year_level_label: string;
	section: string;
	total_sessions: number;
	compliance_rate: number;
	participation_rate: number;
};

export type TrendPoint = {
	date: string;
	label: string;
	offering_id: number;
	course_id: number;
	course_code: string;
	cohort: string;
	rate: number;
};

const parseDateKey = (key: string): Date => {
	const [year, month, day] = key.split('-').map(Number);
	return new Date(year, month - 1, day);
};

const toDateKey = (date: Date): string =>
	`${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;

const mondayOf = (date: Date): Date => {
	const monday = new Date(date);
	monday.setDate(date.getDate() - ((date.getDay() + 6) % 7));
	return monday;
};

const bucketFor = (dateKey: string, granularity: ReportGranularity): AggregateBucket => {
	const date = parseDateKey(dateKey);
	if (granularity === 'weekly') {
		const monday = mondayOf(date);
		const key = toDateKey(monday);
		return {
			key,
			label: `Week of ${monday.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}`,
			date: key,
			total_sessions: 0,
			total_students: 0,
			compliance_rate: 0,
			participation_rate: 0
		};
	}
	if (granularity === 'monthly') {
		return {
			key: dateKey.slice(0, 7),
			label: date.toLocaleDateString(undefined, { month: 'short', year: 'numeric' }),
			date: `${dateKey.slice(0, 7)}-01`,
			total_sessions: 0,
			total_students: 0,
			compliance_rate: 0,
			participation_rate: 0
		};
	}
	return {
		key: dateKey,
		label: date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
		date: dateKey,
		total_sessions: 0,
		total_students: 0,
		compliance_rate: 0,
		participation_rate: 0
	};
};

const filterSessions = (filters: ReportFilters): ReportSessionRecord[] => {
	if (!MOCK) throw new Error('Report data is unavailable until professor report endpoints land.');
	const start = filters.from <= filters.to ? filters.from : filters.to;
	const end = filters.from <= filters.to ? filters.to : filters.from;

	return REPORT_SESSIONS.filter(
		(session) =>
			(filters.program === 'All' || session.programCode === filters.program) &&
			(filters.year === 'All' || session.yearLevelLabel === filters.year) &&
			(filters.course === 'All' || session.courseCode === filters.course) &&
			(filters.section === 'All' || session.section === filters.section) &&
			session.date >= start &&
			session.date <= end
	);
};

const summarize = (sessions: ReportSessionRecord[]) => {
	let present = 0;
	let eligible = 0;
	let seats = 0;
	for (const session of sessions) {
		present += session.present;
		eligible += session.present + session.late + session.excused;
		seats += session.enrolled;
	}
	return {
		compliance_rate: seats === 0 ? 0 : present / seats,
		participation_rate: seats === 0 ? 0 : eligible / seats,
		seats
	};
};

export const defaultReportRange = (days = 30): { from: string; to: string } => {
	const to = new Date();
	to.setHours(0, 0, 0, 0);
	const from = new Date(to);
	from.setDate(to.getDate() - (days - 1));
	return { from: toDateKey(from), to: toDateKey(to) };
};

export const getReportFilterOptions = () => {
	const unique = (values: string[]): string[] => [...new Set(values)].sort();
	const courses = new Map<string, string>();
	for (const course of PROFESSOR_COURSES) {
		if (!courses.has(course.courseCode)) courses.set(course.courseCode, course.courseName);
	}

	return {
		programs: unique(PROFESSOR_COURSES.map((course) => course.programCode)),
		years: unique(PROFESSOR_COURSES.map((course) => course.yearLevelLabel)),
		courses: [...courses].map(([code, name]) => ({ code, name })).sort((a, b) => a.code.localeCompare(b.code)),
		sections: unique(PROFESSOR_COURSES.map((course) => course.section))
	};
};

export const getAllCoursesReport = async (filters: ReportFilters) => {
	const sessions = filterSessions(filters);
	const buckets = new Map<string, AggregateBucket & { present: number; eligible: number }>();

	for (const session of sessions) {
		const bucket = bucketFor(session.date, filters.granularity);
		const current = buckets.get(bucket.key) ?? { ...bucket, present: 0, eligible: 0 };
		current.total_sessions += 1;
		current.total_students += session.enrolled;
		current.present += session.present;
		current.eligible += session.present + session.late + session.excused;
		buckets.set(bucket.key, current);
	}

	const items: AggregateBucket[] = [...buckets.values()]
		.map((bucket) => ({
			key: bucket.key,
			label: bucket.label,
			date: bucket.date,
			total_sessions: bucket.total_sessions,
			total_students: bucket.total_students,
			compliance_rate: bucket.total_students === 0 ? 0 : bucket.present / bucket.total_students,
			participation_rate: bucket.total_students === 0 ? 0 : bucket.eligible / bucket.total_students
		}))
		.sort((a, b) => (a.date === b.date ? a.key.localeCompare(b.key) : a.date < b.date ? -1 : 1));
	const totals = summarize(sessions);

	return {
		items,
		total_sessions: sessions.length,
		total_students: totals.seats,
		avg_compliance: totals.compliance_rate,
		avg_participation: totals.participation_rate
	};
};

export const getComparisonReport = async (filters: ReportFilters) => {
	const sessions = filterSessions(filters);
	const groups = new Map<number, ReportSessionRecord[]>();
	for (const session of sessions) {
		const group = groups.get(session.offeringId) ?? [];
		group.push(session);
		groups.set(session.offeringId, group);
	}

	const items: ComparisonRow[] = [...groups].map(([offeringId, group]) => {
		const first = group[0];
		const totals = summarize(group);
		return {
			course_id: first.courseId,
			course_code: first.courseCode,
			course_name: first.courseName,
			program_id: first.programCode,
			program_code: first.programCode,
			year_level_id: first.yearLevelLabel,
			year_level_label: first.yearLevelLabel,
			section: first.section,
			total_sessions: group.length,
			compliance_rate: totals.compliance_rate,
			participation_rate: totals.participation_rate,
			offering_id: offeringId
		};
	});

	return {
		items: items.sort((a, b) =>
			a.course_code === b.course_code
				? `${a.program_code}${a.year_level_label}${a.section}`.localeCompare(
						`${b.program_code}${b.year_level_label}${b.section}`
					)
				: a.course_code.localeCompare(b.course_code)
		)
	};
};

export const getTrendsReport = async (filters: ReportFilters) => {
	const sessions = filterSessions(filters);
	const points = new Map<string, { bucket: AggregateBucket; offering: ReportSessionRecord; present: number; eligible: number; seats: number }>();

	for (const session of sessions) {
		const bucket = bucketFor(session.date, filters.granularity);
		const key = `${bucket.key}|${session.offeringId}`;
		const current = points.get(key) ?? { bucket, offering: session, present: 0, eligible: 0, seats: 0 };
		current.present += session.present;
		current.eligible += session.present + session.late + session.excused;
		current.seats += session.enrolled;
		points.set(key, current);
	}

	const items: TrendPoint[] = [...points.values()].map((point) => ({
		date: point.bucket.date,
		label: point.bucket.label,
		offering_id: point.offering.offeringId,
		course_id: point.offering.courseId,
		course_code: point.offering.courseCode,
		cohort: `${point.offering.programCode}·${point.offering.yearLevelLabel} ${point.offering.courseCode} · Section ${point.offering.section}`,
		rate:
			point.seats === 0
				? 0
				: filters.metric === 'compliance'
					? point.present / point.seats
					: point.eligible / point.seats
	}));

	return {
		metric: filters.metric,
		items: items.sort((a, b) =>
			a.date === b.date ? a.offering_id - b.offering_id : a.date < b.date ? -1 : 1
		)
	};
};

export const buildCsv = (header: string[], rows: Array<Array<string | number>>): string => {
	const escape = (value: string | number): string => {
		const text = String(value);
		return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
	};
	return [header, ...rows].map((row) => row.map(escape).join(',')).join('\r\n');
};
