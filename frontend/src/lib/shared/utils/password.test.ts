import { describe, it, expect } from 'vitest';
import { evaluatePassword, isPasswordStrong, PASSWORD_MIN_LENGTH } from './password';

describe('password', () => {
	it('PASSWORD_MIN_LENGTH is 8', () => {
		expect(PASSWORD_MIN_LENGTH).toBe(8);
	});
	it('strong password passes all', () => {
		const req = evaluatePassword('Abcdef1!');
		expect(req).toEqual({ length: true, upper: true, lower: true, number: true, symbol: true });
		expect(isPasswordStrong(req)).toBe(true);
	});
	it('short password fails length', () => {
		expect(evaluatePassword('Ab1!').length).toBe(false);
	});
	it('missing uppercase', () => {
		expect(evaluatePassword('abcdef1!').upper).toBe(false);
	});
	it('missing lowercase', () => {
		expect(evaluatePassword('ABCDEF1!').lower).toBe(false);
	});
	it('missing number', () => {
		expect(evaluatePassword('Abcdefg!').number).toBe(false);
	});
	it('missing symbol', () => {
		expect(evaluatePassword('Abcdefg1').symbol).toBe(false);
	});
	it('space is not a symbol', () => {
		expect(evaluatePassword('Abcdefg1 ').symbol).toBe(false);
	});
	it('isPasswordStrong false when any requirement false', () => {
		const req = evaluatePassword('abc');
		expect(isPasswordStrong(req)).toBe(false);
	});
});