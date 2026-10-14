<script lang="ts">
	// Six one-digit inputs with the same handling the auth pages had each
	// reimplemented: digits only, auto-advance, Backspace steps back, paste of a
	// whole code spreads across the boxes.
	//
	// The parent owns the value (`digits`, a 6-element array) and clears it when
	// a code is rejected — a single-use code must never sit in the field.
	import { onMount } from 'svelte';

	let {
		digits = $bindable(['', '', '', '', '', '']),
		disabled = false,
		onChange,
	}: {
		digits?: string[];
		disabled?: boolean;
		onChange?: () => void;
	} = $props();

	let inputs: HTMLInputElement[] = $state([]);

	const count = 6;

	// The code step is the whole screen, so the cursor starts on digit one
	// unless the caller wants a different box (paste resets it deliberately).
	onMount(() => inputs[0]?.focus());

	export function clear(): void {
		digits = Array.from({ length: count }, () => '');
		queueMicrotask(() => inputs[0]?.focus());
	}

	export function focus(): void {
		inputs[0]?.focus();
	}

	function setDigit(i: number, value: string) {
		const v = value.replace(/\D/g, '').slice(-1);
		if (!v) return;
		digits = digits.map((d, index) => (index === i ? v : d));
		onChange?.();
		inputs[Math.min(i + 1, count - 1)]?.focus();
	}

	function handlePaste(i: number, event: ClipboardEvent) {
		const pasted = (event.clipboardData?.getData('text') ?? '').replace(/\D/g, '').slice(0, count);
		if (!pasted) return;
		event.preventDefault();
		const next = [...digits];
		// Fill forward from the focused box so pasting into any box works,
		// not just box one.
		for (let j = 0; j < pasted.length && i + j < count; j++) next[i + j] = pasted[j];
		digits = next;
		onChange?.();
		inputs[Math.min(i + pasted.length, count - 1)]?.focus();
	}

	function handleKeydown(i: number, event: KeyboardEvent) {
		if (event.key === 'Backspace') {
			if (digits[i]) {
				digits = digits.map((d, index) => (index === i ? '' : d));
				onChange?.();
			} else if (i > 0) {
				// Clear the previous box as well as moving to it — one press
				// deletes, not just navigates.
				digits = digits.map((d, index) => (index === i - 1 ? '' : d));
				onChange?.();
				inputs[i - 1]?.focus();
			}
		}
		if (event.key === 'ArrowLeft' && i > 0) inputs[i - 1]?.focus();
		if (event.key === 'ArrowRight' && i < count - 1) inputs[i + 1]?.focus();
	}
</script>

<div class="otp-row">
	{#each digits as digit, i}
		<input
			class="otp-input"
			maxlength="1"
			inputmode="numeric"
			autocomplete="one-time-code"
			aria-label={`Digit ${i + 1}`}
			{disabled}
			value={digit}
			bind:this={inputs[i]}
			oninput={(e) => setDigit(i, (e.currentTarget as HTMLInputElement).value)}
			onkeydown={(e) => handleKeydown(i, e)}
			onpaste={(e) => handlePaste(i, e)}
		/>
	{/each}
</div>

<style>
	.otp-row {
		display: flex;
		gap: 0.5rem;
		justify-content: center;
		margin-bottom: 1.25rem;
	}

	.otp-input {
		width: 46px;
		height: 52px;
		text-align: center;
		font-size: 1.25rem;
		font-family: monospace;
		font-weight: 700;
		color: var(--brand);
		border: 1.5px solid var(--border-strong);
		border-radius: 8px;
		outline: none;
		transition: border-color 0.15s;
		background: var(--bg-card);
	}

	.otp-input:focus {
		border-color: var(--accent);
	}

	.otp-input:disabled {
		opacity: 0.6;
	}
</style>
