// features/admin/audit/labels.ts
// The lookup context the audit reader resolves names from.
//
// The audit endpoint returns the stored row unaltered (ADR-064): the actor is
// a `users.id` and the subject is `entity_type` + `entity_id`. The names an
// administrator needs are derived on the read side, and this file owns the
// two halves of that:
//
//   1. The SNAPSHOT. Every `_snapshot` method on the server already carries
//      the human identifiers — a program snapshot has `code` and `name`, a
//      course snapshot has `course_code` and `course_name`, a student
//      snapshot has `student_id` and the names. So the label is read out of
//      `new_value ?? old_value` FIRST, and a lookup below is only the
//      fallback for the rows whose snapshot does not carry one.
//
//      This is not just an optimisation. A hard-deleted program has no row
//      left to join against — its audit snapshot is the only surviving
//      record of it — so the snapshot answers a question the join cannot.
//
//   2. The LOOKUP. A roster map, fetched only when the loaded page actually
//      needs it, and only once per kind.
//
// The lookups are lazy on purpose. A general resolver that loads all five
// rosters on every audit page load is the obvious implementation and the
// wrong one: it spends five requests on data most rows already carry.

import type {
	AdminCourse,
	AdminOffering,
	AdminProfessor,
	AdminStudent,
	AdminUser,
	Program,
	YearLevel,
} from '$lib/shared/types';
import type { AuditLogRow } from '$lib/features/admin/audit/service';

export interface AuditUserRef {
	name: string;
	email: string;
	role: string;
}

export interface AuditProgramRef {
	code: string;
	name: string;
}

export interface AuditYearLevelRef {
	label: string;
	programId: number;
}

export interface AuditCourseRef {
	code: string;
	name: string;
}

export interface AuditStudentRef {
	studentId: string;
	name: string;
	programCode: string;
}

export interface AuditProfessorRef {
	name: string;
	email: string;
}

export interface AuditOfferingRef {
	/** "CS101 · Data Structures" */
	course: string;
	program: string;
	yearLevel: string;
	semester: string;
	academicYear: string;
}

export interface AuditLabelContext {
	users: Map<number, AuditUserRef>;
	programs: Map<number, AuditProgramRef>;
	yearLevels: Map<number, AuditYearLevelRef>;
	courses: Map<number, AuditCourseRef>;
	students: Map<number, AuditStudentRef>;
	professors: Map<number, AuditProfessorRef>;
	offerings: Map<number, AuditOfferingRef>;
}

export const emptyLabelContext = (): AuditLabelContext => ({
	users: new Map(),
	programs: new Map(),
	yearLevels: new Map(),
	courses: new Map(),
	students: new Map(),
	professors: new Map(),
	offerings: new Map(),
});

export type LabelKind =
	| 'users'
	| 'programs'
	| 'yearLevels'
	| 'courses'
	| 'students'
	| 'professors'
	| 'offerings';

/**
 * Which lookups a set of rows can actually need.
 *
 * Driven by the entity type, because that is what decides which snapshot
 * fields are present. A program row carries its own code and name, so it
 * needs nothing; a `course_offering` row carries ids, so it needs the
 * course, program and year-level maps to become a name.
 */
export const neededLabelKinds = (rows: AuditLogRow[]): Set<LabelKind> => {
	const kinds = new Set<LabelKind>();
	for (const row of rows) {
		switch (row.entity_type) {
			case 'year_level':
				kinds.add('programs');
				kinds.add('yearLevels');
				break;
			case 'course_offering':
				kinds.add('courses');
				kinds.add('programs');
				kinds.add('yearLevels');
				kinds.add('offerings');
				break;
			case 'session':
				kinds.add('courses');
				kinds.add('programs');
				kinds.add('yearLevels');
				kinds.add('offerings');
				break;
			case 'excuse':
				kinds.add('students');
				break;
			case 'course_professor':
				kinds.add('courses');
				kinds.add('programs');
				kinds.add('yearLevels');
				kinds.add('offerings');
				kinds.add('professors');
				break;
			case 'face_enrollment':
				kinds.add('students');
				break;
			case 'enrollment':
				kinds.add('courses');
				kinds.add('programs');
				kinds.add('yearLevels');
				kinds.add('offerings');
				break;
			case 'user':
				kinds.add('users');
				break;
			default:
				// program, course, student, professor, backup, app_setting,
				// maintenance and attendance_record all carry their own
				// identifying fields in the snapshot.
				break;
		}
	}
	return kinds;
};

/**
 * The loaders the resolver calls.
 *
 * Passed in rather than imported, so the resolver has no dependency on the
 * API layer and can be exercised against fixtures. Each returns the page it
 * got plus the total the server reports, so a truncated map is visible
 * rather than silently incomplete.
 */
export interface LabelPage<T> {
	items: T[];
	total: number;
}

export interface AuditLabelLoaders {
	programs: () => Promise<LabelPage<Program>>;
	yearLevels: (programId: number) => Promise<LabelPage<YearLevel>>;
	courses: () => Promise<LabelPage<AdminCourse>>;
	students: () => Promise<LabelPage<AdminStudent>>;
	professors: () => Promise<LabelPage<AdminProfessor>>;
	offerings: () => Promise<LabelPage<AdminOffering>>;
	users: () => Promise<LabelPage<AdminUser>>;
}

const fullName = (first?: string, last?: string): string =>
	[first, last].filter((part) => !!part && part.trim().length > 0).join(' ').trim();

/**
 * A lazy, cached lookup context.
 *
 * `ensure()` fetches only the kinds that are missing, once each, and
 * remembers what it loaded. A kind whose fetch fails is left unloaded rather
 * than poisoned, so the next page can retry it. A kind that came back
 * shorter than its total is marked partial, so the UI can say so instead of
 * pretending the map is complete.
 */
export class AuditLabelResolver {
	private readonly ctx: AuditLabelContext = emptyLabelContext();
	private readonly loaded = new Set<LabelKind>();
	private readonly partial = new Set<LabelKind>();
	private readonly inFlight = new Map<LabelKind, Promise<void>>();

	constructor(private readonly loaders: AuditLabelLoaders) {}

	context(): AuditLabelContext {
		return this.ctx;
	}

	/** True when a kind was fetched but its map is incomplete. */
	isPartial(kind: LabelKind): boolean {
		return this.partial.has(kind);
	}

	async ensure(kinds: Iterable<LabelKind>): Promise<void> {
		const wanted = [...kinds].filter((k) => !this.loaded.has(k));
		await Promise.all(wanted.map((kind) => this.loadOne(kind)));
	}

	private loadOne(kind: LabelKind): Promise<void> {
		const existing = this.inFlight.get(kind);
		if (existing) return existing;
		const promise = this.fetch(kind)
			.then(() => {
				this.loaded.add(kind);
			})
			.catch(() => {
				// A roster that cannot be read leaves its label unresolved; the
				// row still renders, with the id as the fallback.
			})
			.finally(() => {
				this.inFlight.delete(kind);
			});
		this.inFlight.set(kind, promise);
		return promise;
	}

	private note(kind: LabelKind, total: number, count: number): void {
		if (total > count) this.partial.add(kind);
	}

	private async fetch(kind: LabelKind): Promise<void> {
		switch (kind) {
			case 'users': {
				const page = await this.loaders.users();
				for (const u of page.items) {
					this.ctx.users.set(u.id, {
						name: fullName(u.firstName, u.lastName) || u.email,
						email: u.email,
						role: u.role,
					});
				}
				this.note(kind, page.total, page.items.length);
				return;
			}
			case 'programs': {
				const page = await this.loaders.programs();
				for (const p of page.items) {
					this.ctx.programs.set(p.id, { code: p.code, name: p.name });
				}
				this.note(kind, page.total, page.items.length);
				return;
			}
			case 'yearLevels': {
				// Year levels hang off a program, so the program map has to
				// exist first — otherwise there is nothing to enumerate.
				if (!this.loaded.has('programs')) await this.loadOne('programs');
				const programIds = [...this.ctx.programs.keys()];
				let seen = 0;
				for (const programId of programIds) {
					const page = await this.loaders.yearLevels(programId);
					seen += page.items.length;
					for (const level of page.items) {
						this.ctx.yearLevels.set(level.id, {
							label: level.label,
							programId: level.programId,
						});
					}
				}
				this.note(kind, seen, seen);
				return;
			}
			case 'courses': {
				const page = await this.loaders.courses();
				for (const c of page.items) {
					this.ctx.courses.set(c.id, { code: c.courseCode, name: c.courseName });
				}
				this.note(kind, page.total, page.items.length);
				return;
			}
			case 'students': {
				const page = await this.loaders.students();
				for (const s of page.items) {
					this.ctx.students.set(s.id, {
						studentId: s.studentId,
						name: fullName(s.firstName, s.lastName) || s.studentId,
						programCode: s.programCode,
					});
				}
				this.note(kind, page.total, page.items.length);
				return;
			}
			case 'professors': {
				const page = await this.loaders.professors();
				for (const p of page.items) {
					this.ctx.professors.set(p.id, {
						name: fullName(p.firstName, p.lastName) || p.email,
						email: p.email,
					});
				}
				this.note(kind, page.total, page.items.length);
				return;
			}
			case 'offerings': {
				const page = await this.loaders.offerings();
				for (const o of page.items) {
					const course = this.ctx.courses.get(o.courseId);
					const program = this.ctx.programs.get(o.programId);
					const yearLevel = this.ctx.yearLevels.get(o.yearLevelId);
					this.ctx.offerings.set(o.id, {
						course: course ? `${course.code} · ${course.name}` : `Course #${o.courseId}`,
						program: program ? program.code : `Program #${o.programId}`,
						yearLevel: yearLevel ? yearLevel.label : `Year level #${o.yearLevelId}`,
						semester: o.semester,
						academicYear: o.academicYear,
					});
				}
				this.note(kind, page.total, page.items.length);
				return;
			}
		}
	}
}

/** "CS101 · Data Structures — BSIT 1st Year · 1st Sem · 2026-2027" */
export const offeringTitle = (ref: AuditOfferingRef): string =>
	`${ref.course} — ${ref.program} ${ref.yearLevel} · ${ref.semester} Sem · ${ref.academicYear}`;
