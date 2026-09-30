// terms.ts
// Canonical term vocabulary for year levels. The admin program forms offer
// these as dropdowns rather than free text, so a term code/label can only be
// one of the recognised values.

export const TERM_CODES = ["1st", "2nd", "3rd", "4th", "5th", "6th"] as const;

export const TERM_LABELS = ["1st Semester", "2nd Semester", "Midyear"] as const;

// A year cannot have more terms than there are distinct codes to label them.
export const MAX_TERMS_PER_YEAR = TERM_CODES.length;

export type TermCode = (typeof TERM_CODES)[number];
export type TermLabel = (typeof TERM_LABELS)[number];
