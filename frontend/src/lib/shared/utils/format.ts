// format.ts
// Display helpers for dates, times, and percentages.

// e.g. "Wed, Sep 22, 2026"
export const formatDate = (isoString: string): string => {
  const date = new Date(isoString);
  return date.toLocaleDateString(undefined, {
    weekday: "short",
    year: "numeric",
    month: "short",
    day: "numeric",
  });
};

// e.g. "10:30 PM"
export const formatTime = (isoString: string): string => {
  const date = new Date(isoString);
  return date.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
};

// Rounds a 0-100 value to an integer and appends "%".
export const formatPercentage = (value: number): string =>
  `${Math.round(value)}%`;

// Full ISO timestamp squashed to "YYYY-MM-DD HH:MM:SS".
export const formatTimestamp = (isoString: string): string => {
  const date = new Date(isoString);
  return date.toISOString().replace("T", " ").slice(0, 19);
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