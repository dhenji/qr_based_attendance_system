// Shared types and preset math for the analytics filter rail.
//
// The rail is presentational: parents own filter values, fetching, and
// debouncing. These definitions keep the preset ids and the date ranges they
// resolve to in one place so the analytics page and the attendance snapshot
// cannot drift again.

export type DatePresetId = 'custom' | 'today' | 'week' | 'month' | 'year' | 'all';

export type PresetId = Exclude<DatePresetId, 'custom'>;

export interface FilterPreset {
	id: PresetId;
	label: string;
}

export const DATE_PRESETS: readonly FilterPreset[] = [
	{ id: 'today', label: 'Today' },
	{ id: 'week', label: 'This week' },
	{ id: 'month', label: 'This month' },
	{ id: 'year', label: 'This year' },
	{ id: 'all', label: 'All time' },
];

export interface DateRange {
	from: string;
	to: string;
}

// Presets are calendar days, so the range is built from local date parts (the
// same convention as the professor attendance/session quick filters) rather
// than UTC. `all` clears both bounds.
export const presetDateRange = (preset: PresetId, now: Date = new Date()): DateRange => {
	const toIso = (d: Date) =>
		`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

	if (preset === 'today') return { from: toIso(now), to: toIso(now) };
	if (preset === 'week') {
		const start = new Date(now);
		start.setDate(now.getDate() - now.getDay());
		return { from: toIso(start), to: toIso(now) };
	}
	if (preset === 'month') {
		return { from: toIso(new Date(now.getFullYear(), now.getMonth(), 1)), to: toIso(now) };
	}
	if (preset === 'year') {
		return { from: toIso(new Date(now.getFullYear(), 0, 1)), to: toIso(now) };
	}
	return { from: '', to: '' };
};
