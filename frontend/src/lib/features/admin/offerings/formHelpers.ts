// features/admin/offerings/formHelpers.ts
// Pure form helpers shared by the offering detail surfaces. No Svelte, no I/O.

// Optional coordinate parser: blank means "not provided" and returns
// undefined; a set value must be a finite number inside the given range.
export const parseOptCoord = (
	raw: string,
	label: string,
	min: number,
	max: number
): number | undefined => {
	const trimmed = raw.trim();
	if (!trimmed) return undefined;
	const value = Number(trimmed);
	if (!Number.isFinite(value) || value < min || value > max) {
		throw new Error(`${label} must be a number between ${min} and ${max}`);
	}
	return value;
};
