// debounce.ts
// One trailing-edge debounce for live-search inputs.
//
// Every migrated search used to carry its own timer variable and cleanup;
// keeping the timer here means the delay, latest-argument behavior, and
// cancellation semantics cannot drift between pages.

// Keystrokes pause this long before a live-search request goes out. The
// previous 250 ms / 300 ms split was accidental drift, so every search
// interaction now uses this one value.
export const SEARCH_DEBOUNCE_MS = 300;

export interface Debounced<Args extends unknown[]> {
	(...args: Args): void;
	cancel: () => void;
}

export const debounce = <Args extends unknown[]>(
	fn: (...args: Args) => unknown,
	delay: number = SEARCH_DEBOUNCE_MS
): Debounced<Args> => {
	let timer: ReturnType<typeof setTimeout> | null = null;
	let pendingArgs: Args | null = null;

	const cancel = (): void => {
		if (timer !== null) {
			clearTimeout(timer);
			timer = null;
		}
		pendingArgs = null;
	};

	const debounced = (...args: Args): void => {
		pendingArgs = args;
		if (timer !== null) clearTimeout(timer);
		timer = setTimeout(() => {
			timer = null;
			const callArgs = pendingArgs;
			pendingArgs = null;
			if (callArgs) void fn(...callArgs);
		}, delay);
	};

	return Object.assign(debounced, { cancel });
};
