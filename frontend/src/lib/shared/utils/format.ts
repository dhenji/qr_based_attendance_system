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