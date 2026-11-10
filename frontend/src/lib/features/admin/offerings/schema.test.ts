import { describe, it, expect } from 'vitest';
import { offeringSettingsSchema } from './schema';

describe('offeringSettingsSchema', () => {
	it('accepts blank inherit values', () => {
		const parsed = offeringSettingsSchema.safeParse({ present: '', late: '', radius: '', room: '', lat: '', lng: '' });
		expect(parsed.success).toBe(true);
	});

	it('rejects out-of-range windows', () => {
		const parsed = offeringSettingsSchema.safeParse({ present: '0', late: '10', radius: '', room: '', lat: '', lng: '' });
		expect(parsed.success).toBe(false);
	});

	it('requires both lat and lng', () => {
		const parsed = offeringSettingsSchema.safeParse({ present: '', late: '', radius: '', room: '', lat: '1.0', lng: '' });
		expect(parsed.success).toBe(false);
	});
});