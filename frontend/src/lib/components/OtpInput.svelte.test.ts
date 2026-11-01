import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import OtpInput from './OtpInput.svelte';

describe('OtpInput', () => {
	it('renders 6 inputs', () => {
		render(OtpInput);
		const inputs = screen.getAllByRole('textbox');
		expect(inputs).toHaveLength(6);
	});

	it('disables all inputs when disabled', () => {
		render(OtpInput, { props: { disabled: true } });
		for (const input of screen.getAllByRole('textbox')) {
			expect(input).toBeDisabled();
		}
	});

	it('typing a digit advances focus to the next input', async () => {
		render(OtpInput);
		const inputs = screen.getAllByRole('textbox') as HTMLInputElement[];
		inputs[0].focus();
		await fireEvent.input(inputs[0], { target: { value: '5' } });
		expect(inputs[0].value).toBe('5');
		expect(document.activeElement).toBe(inputs[1]);
	});

	it('backspace clears the current digit', async () => {
		render(OtpInput, { props: { digits: ['5', '', '', '', '', ''] } });
		const inputs = screen.getAllByRole('textbox') as HTMLInputElement[];
		inputs[0].focus();
		await fireEvent.keyDown(inputs[0], { key: 'Backspace' });
		expect(inputs[0].value).toBe('');
	});

	it('backspace on empty moves to previous and clears it', async () => {
		render(OtpInput, { props: { digits: ['5', '', '', '', '', ''] } });
		const inputs = screen.getAllByRole('textbox') as HTMLInputElement[];
		inputs[1].focus();
		await fireEvent.keyDown(inputs[1], { key: 'Backspace' });
		expect(inputs[0].value).toBe('');
		expect(document.activeElement).toBe(inputs[0]);
	});

	it('paste spreads digits across boxes', async () => {
		render(OtpInput);
		const inputs = screen.getAllByRole('textbox') as HTMLInputElement[];
		inputs[0].focus();
		const event = new Event('paste', { bubbles: true, cancelable: true });
		Object.defineProperty(event, 'clipboardData', {
			value: { getData: () => '123456' }
		});
		await fireEvent(inputs[0], event);
		for (let i = 0; i < 6; i++) {
			expect(inputs[i].value).toBe(String(i + 1));
		}
	});
});