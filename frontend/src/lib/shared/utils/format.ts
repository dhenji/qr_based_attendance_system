// format.ts
// Display helpers for dates, times, and percentages.

// e.g. "Wed, Sep 22, 2026" (viewer locale). Returns "—" for invalid input
// rather than "Invalid Date".
export const formatDate = (isoString: string): string => {
	const date = new Date(isoString);
	if (Number.isNaN(date.getTime())) return '—';
	return date.toLocaleDateString(undefined, {
		weekday: 'short',
		year: 'numeric',
		month: 'short',
		day: 'numeric',
	});
};

// e.g. "10:30 PM" (viewer locale). Returns "—" for invalid input.
export const formatTime = (isoString: string): string => {
	const date = new Date(isoString);
	if (Number.isNaN(date.getTime())) return '—';
	return date.toLocaleTimeString(undefined, {
		hour: '2-digit',
		minute: '2-digit',
	});
};

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

// Local datetime in "YYYY-MM-DD HH:MM:SS" format (user's timezone)
export const formatLocalDateTime = (isoString: string): string => {
  const date = new Date(isoString);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  const seconds = String(date.getSeconds()).padStart(2, '0');
  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
};

// Local date in "YYYY-MM-DD" format (user's timezone)
export const formatLocalDate = (isoString: string): string => {
  const date = new Date(isoString);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

// UTC timestamp with explicit UTC label for admin/debugging use
export const formatUTCTimestamp = (isoString: string): string => {
  const date = new Date(isoString);
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