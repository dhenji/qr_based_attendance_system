// format.ts
// Display helpers for dates, times, and percentages.

export type LocalDateTimeInput = string | number | Date | null | undefined;

export interface LocalDateTimeFormatOptions {
	/** Options for `toLocaleDateString`; omit to render only the time. */
	date?: Intl.DateTimeFormatOptions | false;
	/** Options for `toLocaleTimeString`; omit to render only the date. */
	time?: Intl.DateTimeFormatOptions | false;
	/** Separator between the date and time parts. Defaults to ", ". */
	separator?: string;
}

// Local datetime in "YYYY-MM-DD HH:MM:SS" format (user's timezone).
// Returns "—" for invalid input, like the other formatters.
//
// Pass the options form to render a locale-aware date and/or time instead;
// the no-options form stays machine-friendly because existing admin, scan,
// and history surfaces render it as-is.
export function formatLocalDateTime(value: LocalDateTimeInput): string;
export function formatLocalDateTime(
	value: LocalDateTimeInput,
	options: LocalDateTimeFormatOptions
): string;
export function formatLocalDateTime(
	value: LocalDateTimeInput,
	options?: LocalDateTimeFormatOptions
): string {
	if (value === null || value === undefined) return '—';
	const date = value instanceof Date ? new Date(value.getTime()) : new Date(value);
	if (Number.isNaN(date.getTime())) return '—';

	if (!options) {
		const year = date.getFullYear();
		const month = String(date.getMonth() + 1).padStart(2, '0');
		const day = String(date.getDate()).padStart(2, '0');
		const hours = String(date.getHours()).padStart(2, '0');
		const minutes = String(date.getMinutes()).padStart(2, '0');
		const seconds = String(date.getSeconds()).padStart(2, '0');
		return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
	}

	const dateText =
		options.date === false || options.date === undefined
			? ''
			: date.toLocaleDateString(undefined, options.date);
	const timeText =
		options.time === false || options.time === undefined
			? ''
			: date.toLocaleTimeString(undefined, options.time);
	return [dateText, timeText].filter((part) => part !== '').join(options.separator ?? ', ');
}

// e.g. "Wed, Sep 22, 2026" (viewer locale). Returns "—" for invalid input
// rather than "Invalid Date".
export const formatDate = (isoString: string): string =>
	formatLocalDateTime(isoString, {
		date: { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric' },
	});

// e.g. "10:30 PM" (viewer locale). Returns "—" for invalid input.
export const formatTime = (isoString: string): string =>
	formatLocalDateTime(isoString, { time: { hour: '2-digit', minute: '2-digit' } });

// Rounds a 0-100 value to an integer and appends "%".
export const formatPercentage = (value: number): string =>
  `${Math.round(value)}%`;

// Full ISO timestamp squashed to "YYYY-MM-DD HH:MM:SS" in UTC (not local).
// Kept for log-like surfaces; prefer formatLocalDateTime for user-facing times.
// Returns "—" for invalid input.
export const formatTimestamp = (isoString: string): string => {
	const date = new Date(isoString);
	if (Number.isNaN(date.getTime())) return '—';
	return date.toISOString().replace('T', ' ').slice(0, 19);
};

// Local date in "YYYY-MM-DD" format (user's timezone). Returns "—" for
// invalid input, like the other formatters.
export const formatLocalDate = (isoString: string): string => {
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return '—';
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

// UTC timestamp with explicit UTC label for admin/debugging use.
// Returns "—" for invalid input (toISOString would otherwise throw).
export const formatUTCTimestamp = (isoString: string): string => {
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return '—';
  return `${date.toISOString().replace("T", " ").slice(0, 19)} UTC`;
};

const ORDINAL_SUFFIXES = ["th", "st", "nd", "rd"] as const;

// Ordinal suffix for a whole number: 1 -> "1st", 2 -> "2nd", 11 -> "11th".
export const ordinal = (value: number): string => {
  const teens = value % 100;
  // 11th/12th/13th break the pattern, so handle them before the last digit.
  if (teens >= 11 && teens <= 13) return `${value}th`;
  return `${value}${ORDINAL_SUFFIXES[value % 10] ?? "th"}`;
};

// Canonical year-level label, e.g. 1 -> "1st Year". The API still requires
// `label` on a year level, so the Add Year form derives it from the chosen
// year instead of asking for free text — that is what stops a label like
// "1st year" or "2" from disagreeing with its year_number.
export const yearLabel = (yearNumber: number): string => `${ordinal(yearNumber)} Year`;

// Human file size, e.g. 1536 -> "1.5 KB". Returns "—" for a non-positive or
// non-numeric size.
//
// Lives here rather than in the admin settings slice: the backup audit rows
// carry a `size_bytes` snapshot, so the audit reader needs it too, and a
// shared formatter is the one home for it.
export const formatBytes = (bytes: number): string => {
	if (!Number.isFinite(bytes) || bytes <= 0) return '—';
	const units = ['B', 'KB', 'MB', 'GB'];
	let value = bytes;
	let unit = 0;
	while (value >= 1024 && unit < units.length - 1) {
		value /= 1024;
		unit += 1;
	}
	return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
};