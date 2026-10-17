// shared/constants/days.ts
// Canonical weekday codes for `schedule_days`. Single-letter codes only:
// student/service.py::_meets_on reads the string per character with
// T=Tuesday/H=Thursday (T was taken), S=Saturday/U=Sunday (S was taken),
// so multi-letter codes would match extra days. Every schedule surface
// (DayPicker, meeting rows) builds from this one list.

export interface DayOption {
	code: string;
	label: string;
}

export const DAY_OPTIONS: DayOption[] = [
	{ code: 'M', label: 'Monday' },
	{ code: 'T', label: 'Tuesday' },
	{ code: 'W', label: 'Wednesday' },
	{ code: 'H', label: 'Thursday' },
	{ code: 'F', label: 'Friday' },
	{ code: 'S', label: 'Saturday' },
	{ code: 'U', label: 'Sunday' },
];
