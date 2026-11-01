import { describe, it, expect } from 'vitest';
import {
	parseTimeToMinutes,
	distinctDayCount,
	meetingDurationMinutes,
	weeklyMeetingHours,
	weeklyHoursBreakdown,
	weeklyWriteBlocked,
	weeklySessionCount,
	totalExpectedSessions,
	findOverlappingMeetings,
	findDuplicateMeetings,
	dayLabels,
	formatWallClock,
	parseDateOnly,
	formatInZone
} from './schedule';

describe('schedule', () => {
	it('parseTimeToMinutes', () => {
		expect(parseTimeToMinutes('09:30')).toBe(570);
		expect(parseTimeToMinutes('24:00')).toBeNull();
		expect(parseTimeToMinutes('bad')).toBeNull();
	});
	it('distinctDayCount de-dupes', () => {
		expect(distinctDayCount('MWF')).toBe(3);
		expect(distinctDayCount('MM')).toBe(1);
		expect(distinctDayCount('')).toBe(0);
	});
	it('meetingDurationMinutes', () => {
		expect(meetingDurationMinutes('09:00', '10:00')).toBe(60);
		expect(meetingDurationMinutes('10:00', '09:00')).toBeNull();
	});
	it('weeklyMeetingHours sums', () => {
		const rows = [{ schedule_days: 'MWF', schedule_start_time: '09:00', schedule_end_time: '10:00' }];
		expect(weeklyMeetingHours(rows)).toBe(3);
	});
	it('weeklyHoursBreakdown ok/over/under', () => {
		const rows = [{ schedule_days: 'M', schedule_start_time: '09:00', schedule_end_time: '10:00' }];
		const b = weeklyHoursBreakdown(rows, 1);
		expect(b?.status).toBe('ok');
		const over = weeklyHoursBreakdown(rows, 0.5);
		expect(over?.status).toBe('over');
		const under = weeklyHoursBreakdown([], 1);
		expect(under?.status).toBe('under');
		expect(weeklyHoursBreakdown(rows, null)).toBeNull();
	});
	it('weeklyWriteBlocked', () => {
		expect(weeklyWriteBlocked(null, 0.5, 1)).toBe(true);
		expect(weeklyWriteBlocked(0.5, 1, 1)).toBe(false);
		expect(weeklyWriteBlocked(1, 1, 1)).toBe(false);
	});
	it('weeklySessionCount', () => {
		expect(weeklySessionCount([{ schedule_days: 'MWF', schedule_start_time: '09:00', schedule_end_time: '10:00' }])).toBe(3);
	});
	it('totalExpectedSessions', () => {
		expect(totalExpectedSessions('3', '16')).toBe(48);
		expect(totalExpectedSessions('0', '16')).toBeNull();
		expect(totalExpectedSessions('abc', '16')).toBeNull();
	});
	it('findOverlappingMeetings', () => {
		const rows = [
			{ schedule_days: 'M', schedule_start_time: '09:00', schedule_end_time: '10:00' },
			{ schedule_days: 'M', schedule_start_time: '09:30', schedule_end_time: '10:30' }
		];
		const o = findOverlappingMeetings(rows);
		expect(o).toHaveLength(1);
	});
	it('findDuplicateMeetings', () => {
		const rows = [
			{ session_type: 'lecture', schedule_days: 'M', schedule_start_time: '09:00' },
			{ session_type: 'lecture', schedule_days: 'M', schedule_start_time: '09:00' }
		];
		expect(findDuplicateMeetings(rows)).toHaveLength(1);
	});
	it('dayLabels canonical order', () => {
		expect(dayLabels('FMW')).toEqual(['Monday', 'Wednesday', 'Friday']);
	});
	it('formatWallClock', () => {
		expect(formatWallClock('09:00:00')).toBe('9:00 AM');
		expect(formatWallClock('13:30:00')).toBe('1:30 PM');
		expect(formatWallClock('bad')).toBe('bad');
	});
	it('parseDateOnly', () => {
		expect(parseDateOnly('2026-10-21')).not.toBeNull();
		expect(parseDateOnly('bad')).toBeNull();
	});
	it('formatInZone', () => {
		expect(formatInZone(null, 'UTC', {})).toBe('');
		expect(formatInZone('bad', 'UTC', {})).toBe('');
		expect(typeof formatInZone('2026-10-21T10:30:00Z', 'UTC', { hour: '2-digit', minute: '2-digit' })).toBe('string');
	});
});