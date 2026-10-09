// features/report/service.ts
// Professor-facing report queries.
//
// Live first: the dedicated aggregates GET /professor/reports/all-courses,
// /comparison and /trends are tried first; when the backend is unreachable or
// the app runs with PUBLIC_MOCK_MODE=true, the per-session derivation from
// GET /professor/sessions/history (server-computed counts + rates) backs the
// same shapes, and the deterministic mock history below backs mock mode.
// Course identity joins from the professor courses store in every path.
//
// Field names intentionally mirror the professor report contracts in
// docs/architecture/api-contracts.md so the live swap stays mechanical; the
// page does not change.

import { get, isMockMode, postText, TEXT_EXPORTS } from '$lib/api/client';
import type {
	ProfessorReportsAllCoursesResponse,
	ProfessorReportsComparisonItemResponse,
	ProfessorReportsTrendItemResponse,
} from '$lib/api/endpoints';
import { PROFESSOR_COURSES } from '$lib/features/professor/mock';
import { initProfessorCourses, professorState } from '$lib/features/professor/store.svelte';
import { listSessionHistory, type SessionHistoryRow } from '$lib/features/session/service';
import { REPORT_SESSIONS, type ReportSessionRecord } from '$lib/features/report/mock';
import type { ProfessorCourseSummary } from '$lib/shared/types';

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

export type ReportDataSource = 'live' | 'demo';

export type ReportMeta = {
	dataSource: ReportDataSource;
	truncated: boolean;
};

// Course directory the report filters and identity joins read. One entry per
// offering × section (live summaries carry a sections array; the mock fixture
// carries one section string per entry, which already matches this shape).
export type ReportCourseDir = {
	offeringId: number;
	courseId: number;
	courseCode: string;
	courseName: string;
	programCode: string;
	yearLevelLabel: string;
	section: string;
	enrolledCount: number;
};

export const toReportDirectory = (courses: ProfessorCourseSummary[]): ReportCourseDir[] => {
	const directory: ReportCourseDir[] = [];
	for (const course of courses) {
		const sections = course.sections.length > 0 ? course.sections : ['—'];
		for (const section of sections) {
			directory.push({
				offeringId: course.offeringId,
				courseId: course.courseId,
				courseCode: course.courseCode,
				courseName: course.courseName,
				programCode: course.programCode,
				yearLevelLabel: course.yearLevelLabel,
				section,
				enrolledCount: course.enrolledCount
			});
		}
	}
	return directory;
};

// Warms the directory from GET /professor/courses. Returns the mock fixture
// (live: false) when the app runs without a backend or the courses call
// fails, so filter options and identity joins always have something to read.
export const initReportDirectory = async (): Promise<{
	directory: ReportCourseDir[];
	live: boolean;
}> => {
	if (isMockMode()) return { directory: PROFESSOR_COURSES, live: false };
	if (professorState.courses.length === 0 && !professorState.coursesError) {
		await initProfessorCourses();
	}
	if (professorState.coursesError || professorState.courses.length === 0) {
		return { directory: PROFESSOR_COURSES, live: false };
	}
	return { directory: toReportDirectory(professorState.courses), live: true };
};

// History paging budget: professors hold a handful of offerings, so a few
// hundred closed sessions cover any sane date range. Past the cap the oldest
// sessions are dropped and truncated is set so the page can say so.
const LIVE_HISTORY_PAGE_SIZE = 100;
const LIVE_HISTORY_MAX_SESSIONS = 500;

const rangeOf = (filters: ReportFilters): { start: string; end: string } => ({
	start: filters.from <= filters.to ? filters.from : filters.to,
	end: filters.from <= filters.to ? filters.to : filters.from
});

const filterMockSessions = (filters: ReportFilters): ReportSessionRecord[] => {
	const { start, end } = rangeOf(filters);

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

// History rows carry no excused count, only the two server-computed rates.
// eligible = present + late + excused is recovered from the participation
// rate (exact up to rounding), so excused is the residual. summarize() only
// consumes present and eligible, so the split never affects the displayed
// rates beyond ±1 seat of rounding.
const toLiveRecord = (row: SessionHistoryRow, directory: ReportCourseDir[]): ReportSessionRecord => {
	const identity = directory.find((item) => item.offeringId === row.offering_id) ?? null;
	const enrolled = row.enrolled_count ?? identity?.enrolledCount ?? 0;
	const eligible = enrolled === 0 ? 0 : Math.round(row.participation_rate * enrolled);
	return {
		sessionId: String(row.id),
		offeringId: row.offering_id,
		courseId: identity?.courseId ?? 0,
		courseCode: row.course_code,
		courseName: row.course_name,
		programCode: identity?.programCode ?? '',
		yearLevelLabel: identity?.yearLevelLabel ?? '',
		section: row.section,
		date: row.created_at.slice(0, 10),
		startTime: row.created_at.slice(11, 16),
		endTime: '',
		enrolled,
		present: row.present_count,
		late: row.late_count,
		excused: Math.max(0, eligible - row.present_count - row.late_count),
		absent: row.absent_count
	};
};

const matchesLiveFilters = (
	session: ReportSessionRecord,
	filters: ReportFilters,
	start: string,
	end: string
): boolean => {
	if (filters.program !== 'All' && session.programCode !== filters.program) return false;
	if (filters.year !== 'All' && session.yearLevelLabel !== filters.year) return false;
	if (filters.course !== 'All' && session.courseCode !== filters.course) return false;
	if (filters.section !== 'All') {
		// Live sections join as a ", "-separated set per offering, so a
		// single-section filter matches by membership rather than equality.
		const sections = session.section.split(',').map((entry) => entry.trim());
		if (!sections.includes(filters.section)) return false;
	}
	return session.date >= start && session.date <= end;
};

const fetchLiveSessions = async (
	filters: ReportFilters,
	directory: ReportCourseDir[]
): Promise<{ sessions: ReportSessionRecord[]; truncated: boolean }> => {
	const { start, end } = rangeOf(filters);
	const rows: SessionHistoryRow[] = [];
	let total = Number.POSITIVE_INFINITY;
	let page = 1;
	while (rows.length < total && rows.length < LIVE_HISTORY_MAX_SESSIONS) {
		const response = await listSessionHistory({
			from: start,
			to: end,
			page,
			size: LIVE_HISTORY_PAGE_SIZE,
			sortBy: 'date',
			sortDir: 'desc'
		});
		total = response.total;
		if ((response.items ?? []).length === 0) break;
		rows.push(...response.items);
		page += 1;
	}
	const truncated = total > rows.length;
	const sessions = rows
		.slice(0, LIVE_HISTORY_MAX_SESSIONS)
		.map((row) => toLiveRecord(row, directory))
		.filter((session) => matchesLiveFilters(session, filters, start, end));
	return { sessions, truncated };
};

const fetchSessions = async (
	filters: ReportFilters,
	directory: ReportCourseDir[]
): Promise<{ sessions: ReportSessionRecord[]; meta: ReportMeta }> => {
	if (isMockMode()) {
		return { sessions: filterMockSessions(filters), meta: { dataSource: 'demo', truncated: false } };
	}
	// Live mode: propagate failures so the page shows an error with retry
	// instead of silently rendering demo fixtures as if they were real.
	const { sessions, truncated } = await fetchLiveSessions(filters, directory);
	return { sessions, meta: { dataSource: 'live', truncated } };
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

// --- Dedicated live aggregates (D37) -------------------------------------------
// Tried first outside mock mode; any failure falls back to the
// sessions/history derivation below so a missing scope or a 404 still renders.
const fetchLiveAllCourses = async (
	filters: ReportFilters
): Promise<{ items: AggregateBucket[]; total_sessions: number; total_students: number; avg_compliance: number; avg_participation: number }> => {
	const { start, end } = rangeOf(filters);
	const response = await get<ProfessorReportsAllCoursesResponse>('professorReportsAllCourses', {
		granularity: filters.granularity,
		date_from: start,
		date_to: end,
	});
	const items: AggregateBucket[] = (response.items ?? []).map((row) => {
		const bucket = bucketFor(row.date.slice(0, 10), filters.granularity);
		return {
			key: row.date,
			label: bucket.label,
			date: row.date,
			total_sessions: row.total_sessions,
			total_students: row.total_students,
			compliance_rate: row.compliance_rate,
			participation_rate: row.participation_rate,
		};
	});
	items.sort((a, b) => (a.date === b.date ? a.key.localeCompare(b.key) : a.date < b.date ? -1 : 1));
	return {
		items,
		total_sessions: items.reduce((sum, item) => sum + item.total_sessions, 0),
		total_students: items.reduce((sum, item) => sum + item.total_students, 0),
		avg_compliance: response.avg_compliance ?? 0,
		avg_participation: response.avg_participation ?? 0,
	};
};

const toComparisonRow = (
	row: ProfessorReportsComparisonItemResponse,
	directory: ReportCourseDir[]
): ComparisonRow => {
	const identity = directory.find((item) => item.courseId === row.course_id) ?? null;
	const programCode = identity?.programCode ?? String(row.program_id);
	const yearLabel = identity?.yearLevelLabel ?? String(row.year_level_id);
	return {
		course_id: row.course_id,
		offering_id: identity?.offeringId ?? row.course_id,
		course_code: row.course_code,
		course_name: identity?.courseName ?? row.course_code,
		program_id: programCode,
		program_code: programCode,
		year_level_id: yearLabel,
		year_level_label: yearLabel,
		section: identity?.section ?? '—',
		total_sessions: row.total_sessions,
		compliance_rate: row.compliance_rate,
		participation_rate: row.participation_rate,
	};
};

const fetchLiveComparison = async (
	filters: ReportFilters,
	directory: ReportCourseDir[]
): Promise<ComparisonRow[]> => {
	const { start, end } = rangeOf(filters);
	const response = await get<{ items: ProfessorReportsComparisonItemResponse[] }>(
		'professorReportsComparison',
		{ granularity: filters.granularity, date_from: start, date_to: end }
	);
	return (response.items ?? []).map((row) => toComparisonRow(row, directory));
};

const fetchLiveTrends = async (
	filters: ReportFilters,
	directory: ReportCourseDir[]
): Promise<TrendPoint[]> => {
	const { start, end } = rangeOf(filters);
	const courseIds = [
		...new Set(
			directory
				.filter(
					(item) =>
						(filters.program === 'All' || item.programCode === filters.program) &&
						(filters.year === 'All' || item.yearLevelLabel === filters.year) &&
						(filters.course === 'All' || item.courseCode === filters.course)
				)
				.map((item) => String(item.courseId))
		),
	];
	const response = await get<{ items: ProfessorReportsTrendItemResponse[] }>(
		'professorReportsTrends',
		{
			metric: filters.metric,
			granularity: filters.granularity,
			date_from: start,
			date_to: end,
			...(courseIds.length > 0 && filters.course !== 'All' ? { course_ids: courseIds } : {}),
		}
	);
	return (response.items ?? []).map((row) => {
		const identity = directory.find((item) => item.courseId === row.course_id) ?? null;
		const bucket = bucketFor(row.date.slice(0, 10), filters.granularity);
		return {
			date: row.date,
			label: bucket.label,
			offering_id: identity?.offeringId ?? row.course_id,
			course_id: row.course_id,
			course_code: row.course_code,
			cohort: identity
				? `${identity.programCode}·${identity.yearLevelLabel} ${identity.courseCode} · Section ${identity.section}`
				: row.course_code,
			rate: row.rate,
		};
	});
};

export const defaultReportRange = (days = 30): { from: string; to: string } => {
	const to = new Date();
	to.setHours(0, 0, 0, 0);
	const from = new Date(to);
	from.setDate(to.getDate() - (days - 1));
	return { from: toDateKey(from), to: toDateKey(to) };
};

export const getReportFilterOptions = (directory: ReportCourseDir[] = PROFESSOR_COURSES) => {
	const unique = (values: string[]): string[] => [...new Set(values)].sort();
	const courses = new Map<string, string>();
	for (const course of directory) {
		if (!courses.has(course.courseCode)) courses.set(course.courseCode, course.courseName);
	}

	return {
		programs: unique(directory.map((course) => course.programCode)),
		years: unique(directory.map((course) => course.yearLevelLabel)),
		courses: [...courses].map(([code, name]) => ({ code, name })).sort((a, b) => a.code.localeCompare(b.code)),
		sections: unique(directory.map((course) => course.section))
	};
};

export const getAllCoursesReport = async (
	filters: ReportFilters,
	directory: ReportCourseDir[] = PROFESSOR_COURSES
) => {
	// Dedicated aggregate first; history derivation stays the fallback.
	if (!isMockMode()) {
		try {
			const live = await fetchLiveAllCourses(filters);
			return { ...live, meta: { dataSource: 'live', truncated: false } as ReportMeta };
		} catch {
			// Fall through to the history derivation below.
		}
	}
	const { sessions, meta } = await fetchSessions(filters, directory);
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
		avg_participation: totals.participation_rate,
		meta
	};
};

export const getComparisonReport = async (
	filters: ReportFilters,
	directory: ReportCourseDir[] = PROFESSOR_COURSES
) => {
	if (!isMockMode()) {
		try {
			const liveItems = await fetchLiveComparison(filters, directory);
			// Program/year/course/section slicing still applies client-side: the
			// comparison aggregate has no section dimension.
			const scoped = directory.length === 0 ? liveItems : liveItems.filter((item) => {
				const dir = directory.find((d) => d.courseId === item.course_id) ?? null;
				if (!dir) return true;
				if (filters.program !== 'All' && dir.programCode !== filters.program) return false;
				if (filters.year !== 'All' && dir.yearLevelLabel !== filters.year) return false;
				if (filters.course !== 'All' && dir.courseCode !== filters.course) return false;
				return true;
			});
			return {
				items: scoped.sort((a, b) =>
					a.course_code === b.course_code
						? `${a.program_code}${a.year_level_label}${a.section}`.localeCompare(
								`${b.program_code}${b.year_level_label}${b.section}`
							)
						: a.course_code.localeCompare(b.course_code)
				),
				meta: { dataSource: 'live', truncated: false } as ReportMeta
			};
		} catch {
			// Fall through to the history derivation below.
		}
	}
	const { sessions, meta } = await fetchSessions(filters, directory);
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
		),
		meta
	};
};

export const getTrendsReport = async (
	filters: ReportFilters,
	directory: ReportCourseDir[] = PROFESSOR_COURSES
) => {
	if (!isMockMode()) {
		try {
			const liveItems = await fetchLiveTrends(filters, directory);
			return {
				metric: filters.metric,
				items: liveItems.sort((a, b) =>
					a.date === b.date ? a.offering_id - b.offering_id : a.date < b.date ? -1 : 1
				),
				meta: { dataSource: 'live', truncated: false } as ReportMeta
			};
		} catch {
			// Fall through to the history derivation below.
		}
	}
	const { sessions, meta } = await fetchSessions(filters, directory);
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
		),
		meta
	};
};

// Server CSV export (POST /professor/reports/export, backend #139). Body
// mirrors ProfessorExportRequest: course/date bounds optional, format csv.
// It throws in mock mode and when the backend is unreachable — the reports
// page falls back to the client-side buildCsv export below, so Export always
// produces a file.
export type ProfessorReportsExportBody = {
	course_id?: number;
	date_from?: string;
	date_to?: string;
	statuses?: Array<'present' | 'late' | 'absent' | 'excused' | 'pending' | 'rejected'>;
};

export const fetchProfessorReportsCsv = (body: ProfessorReportsExportBody): Promise<string> =>
	postText(TEXT_EXPORTS.professorReports, { format: 'csv', ...body });

export const buildCsv = (header: string[], rows: Array<Array<string | number>>): string => {
	const escape = (value: string | number): string => {
		const text = String(value);
		return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
	};
	return [header, ...rows].map((row) => row.map(escape).join(',')).join('\r\n');
};
