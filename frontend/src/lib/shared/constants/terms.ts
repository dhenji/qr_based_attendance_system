// terms.ts
// Term vocabulary for year levels. The admin program form offers these as
// dropdowns, so a term code/label can only be one of the recognised values.
//
// There is deliberately NO cap on how many term rows a year can hold — the user
// adds and removes rows freely.

export const TERM_CODES = ["1st", "2nd", "3rd", "4th", "5th", "6th"] as const;

export const TERM_LABELS = ["1st Semester", "2nd Semester", "Midyear"] as const;

export type TermCode = (typeof TERM_CODES)[number];
export type TermLabel = (typeof TERM_LABELS)[number];

export type TermEditorRow = { code: string; label: string; existing?: boolean };

export function nextTermRow(rows: TermEditorRow[]): TermEditorRow {
	const usedCodes = new Set(rows.map((row) => row.code));
	const usedLabels = new Set(rows.map((row) => row.label));
	return {
		code: TERM_CODES.find((code) => !usedCodes.has(code)) ?? TERM_CODES[0],
		label: TERM_LABELS.find((label) => !usedLabels.has(label)) ?? TERM_LABELS[0],
		existing: false,
	};
}