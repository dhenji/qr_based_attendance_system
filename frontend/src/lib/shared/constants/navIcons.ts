// NAV_ICONS — the single glyph registry behind every role sidebar (admin,
// professor, student). Each string is the inner markup of a 24x24 stroke
// icon; the layouts render it via {@html} inside an <svg> that already
// carries fill="none" stroke="currentColor" with round caps/joins.
//
// One map instead of three per-layout dicts: it stops the drift where two
// nav items shipped byte-identical glyphs (professors==courses,
// users==students, excuses==reports were all real duplicates, fixed one at
// a time). A nav entry must name an existing key — `icon` is typed as
// NavIconName, so a typo or a missing glyph fails `npm run check`.

export const NAV_ICONS = {
	dashboard:
		'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
	wizard:
		'<circle cx="5" cy="12" r="2.2"/><circle cx="12" cy="12" r="2.2"/><circle cx="19" cy="12" r="2.2"/><path d="M7.3 12h2.4M14.3 12h2.4"/>',
	students:
		'<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.6 2.9-5.5 6.5-5.5s6.5 1.9 6.5 5.5"/><path d="M16.5 5.2a3.5 3.5 0 0 1 0 5.6"/><path d="M18 14.8c2.1.7 3.5 2.4 3.5 5.2"/>',
	professors:
		'<path d="M3 3h18"/><path d="M21 3v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V3"/><path d="m7 21 5-5 5 5"/>',
	programs:
		'<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h4"/>',
	courses:
		'<path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H10a2 2 0 0 1 2 2v13a2 2 0 0 0-2-2H5.5A1.5 1.5 0 0 1 4 15.5Z"/><path d="M20 5.5A1.5 1.5 0 0 0 18.5 4H14a2 2 0 0 0-2 2v13a2 2 0 0 1 2-2h4.5a1.5 1.5 0 0 0 1.5-1.5Z"/>',
	offerings:
		'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4"/><path d="M3 10h18"/>',
	reports:
		'<path d="M4 20h16"/><path d="M7 20v-6"/><path d="M12 20V6"/><path d="M17 20v-9"/>',
	excuses:
		'<path d="M14 3H7a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7l-4-4Z"/><path d="M14 3v4h4"/><path d="M12 11v6"/><path d="m9.8 13.2 2.2-2.2 2.2 2.2"/>',
	review:
		'<circle cx="12" cy="12" r="9"/><path d="m8.5 12 2.5 2.5 4.5-5"/>',
	audit:
		'<path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/><path d="M12 8v4l3 2"/>',
	users:
		'<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.6 2.9-5.5 6.5-5.5s6.5 1.9 6.5 5.5"/><circle cx="18.5" cy="14.5" r="2.2"/><path d="m17 16.2 3.8 3.8"/><path d="m19.2 18.4 1-1"/>',
	settings:
		'<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3h.1a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5h.1a1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9v.1a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/>',
	profile:
		'<circle cx="12" cy="8" r="3.5"/><path d="M5 20c0-3.6 3.1-5.5 7-5.5s7 1.9 7 5.5"/>',
	scan:
		'<path d="M4 8h3l1.5-2h7L17 8h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1Z"/><circle cx="12" cy="13.5" r="3.5"/>',
	history:
		'<path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/><path d="M12 8v4l3 2"/>',
	schedule:
		'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4"/><path d="M3 10h18"/>',
	sessions:
		'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4"/><path d="M3 10h18"/><path d="m9.5 15.5 1.8 1.8 3.4-3.6"/>',
	attendance:
		'<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h4"/><path d="m9 14 2 2 4-4"/>',
} as const;

export type NavIconName = keyof typeof NAV_ICONS;

/** One sidebar entry: every role layout declares its items as NavItem[]. */
export interface NavItem {
	label: string;
	path: string;
	enabled: boolean;
	icon: NavIconName;
}
