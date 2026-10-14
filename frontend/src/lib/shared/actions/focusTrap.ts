// lib/shared/actions/focusTrap.ts
// Keyboard containment for modal dialogs.
//
// `use:trapFocus={{ onEscape }}` on the dialog element:
//   - moves focus into the dialog on mount (first focusable control, else the
//     dialog node itself, which needs `tabindex="-1"`)
//   - keeps Tab / Shift+Tab cycling inside the dialog instead of escaping to the
//     page behind it
//   - restores focus to whatever was focused before, on destroy
//   - optionally locks body scroll while open
//   - calls `onEscape` when Escape is pressed (omit it to make the dialog
//     non-dismissible, which is what the shown-once dialogs want)
//
// Applied as an action rather than a wrapper component on purpose: the app has
// 20+ hand-rolled modals whose class names and CSS all differ, so retrofitting
// is one attribute per dialog instead of a markup + stylesheet rewrite. New
// dialogs should prefer `lib/components/Modal.svelte`, which wraps this.
//
// Pairs with `aria-modal="true"` — that attribute promises focus cannot leave
// the dialog, which is only true once this action is attached.

export interface TrapFocusOptions {
	/** Called on Escape. Omit to make the dialog Escape-inert. */
	onEscape?: () => void;
	/** Set false to allow the page behind to scroll. Default true. */
	lockScroll?: boolean;
}

const FOCUSABLE_SELECTOR = [
	'a[href]',
	'button:not([disabled])',
	'input:not([disabled])',
	'select:not([disabled])',
	'textarea:not([disabled])',
	'[tabindex]:not([tabindex="-1"])',
].join(',');

// offsetParent is null for position:fixed elements, so measure boxes instead —
// that also filters out display:none subtrees, which are common in these forms.
const focusableWithin = (node: HTMLElement): HTMLElement[] =>
	Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
		(el) => el.getClientRects().length > 0
	);

let lockCount = 0;
let savedOverflow = '';

export function trapFocus(node: HTMLElement, options: TrapFocusOptions = {}) {
	const { onEscape, lockScroll = true } = options;

	const previouslyFocused =
		document.activeElement instanceof HTMLElement ? document.activeElement : null;

	// Stack-aware scroll lock: nested dialogs each push; only the outermost
	// restores. Without the count, closing an inner dialog re-enables scroll
	// while the outer dialog is still open.
	lockCount += lockScroll ? 1 : 0;
	if (lockScroll && lockCount === 1) {
		savedOverflow = document.body.style.overflow;
		document.body.style.overflow = 'hidden';
	}

	const focusFirst = () => {
		const targets = focusableWithin(node);
		(targets[0] ?? node).focus();
	};
	focusFirst();

	const onFocusIn = (event: FocusEvent) => {
		// Click-outside (or programmatic) focus escaping the dialog gets
		// pulled back in, so aria-modal's promise holds for pointer users too.
		const target = event.target as HTMLElement | null;
		if (target && !node.contains(target)) {
			const targets = focusableWithin(node);
			(targets[0] ?? node).focus();
		}
	};

	const onKeydown = (event: KeyboardEvent) => {
		if (event.key === 'Escape') {
			if (onEscape) {
				event.preventDefault();
				onEscape();
			}
			return;
		}
		if (event.key !== 'Tab') return;

		const targets = focusableWithin(node);
		if (targets.length === 0) {
			event.preventDefault();
			node.focus();
			return;
		}

		const first = targets[0];
		const last = targets[targets.length - 1];
		const active = document.activeElement;

		if (event.shiftKey) {
			if (active === first || !node.contains(active)) {
				event.preventDefault();
				last.focus();
			}
			return;
		}
		if (active === last || !node.contains(active)) {
			event.preventDefault();
			first.focus();
		}
	};

	node.addEventListener('keydown', onKeydown);
	document.addEventListener('focusin', onFocusIn);

	return {
		destroy() {
			node.removeEventListener('keydown', onKeydown);
			document.removeEventListener('focusin', onFocusIn);
			if (lockScroll) {
				lockCount = Math.max(0, lockCount - 1);
				if (lockCount === 0) document.body.style.overflow = savedOverflow;
			}
			// Only restore if the trigger is still in the document and focusable.
			if (previouslyFocused?.isConnected) previouslyFocused.focus();
		},
	};
}