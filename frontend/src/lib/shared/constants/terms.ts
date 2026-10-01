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