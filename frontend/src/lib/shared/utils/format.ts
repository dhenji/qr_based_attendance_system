export const formatDate = (isoString: string): string => {
  const date = new Date(isoString);
  return date.toLocaleDateString(undefined, {
    weekday: "short",
    year: "numeric",
    month: "short",
    day: "numeric",
  });
};

export const formatTime = (isoString: string): string => {
  const date = new Date(isoString);
  return date.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
};

export const formatPercentage = (value: number): string =>
  `${Math.round(value)}%`;

export const formatTimestamp = (isoString: string): string => {
  const date = new Date(isoString);
  return date.toISOString().replace("T", " ").slice(0, 19);
};