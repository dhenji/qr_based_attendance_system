<script lang="ts">
	// Two-step modal for admin-initiated password resets, shared by the users,
	// students, and professors rosters.
	//
	// One component for all three because the backend has one implementation
	// behind all three routes (`AuthService.admin_reset_password`), so the copy
	// below — including the parts that are deliberately *not* true, like MFA
	// being untouched — is identical everywhere. The page supplies only the
	// label and the call.
	//
	// The generated password arrives in the response and nowhere else: there is
	// no endpoint that reads it back. So it is rendered inline, monospaced, and
	// selectable, and the UI is explicit that closing this modal loses it. It is
	// never stored anywhere.
	import { APIError } from '$lib/api/client';

	interface Props {
		/** Display name of the account being reset, e.g. "Jose P. Rizal (24-0001)". */
		subject: string;
		/** 'student' | 'professor' | 'account' — drives the wording of the copy. */
		subjectKind: 'student' | 'professor' | 'account';
		/** Resolves to the new temp password. Rejects with APIError on failure. */
		onconfirm: () => Promise<string>;
		onclose: () => void;
	}

	let { subject, subjectKind, onconfirm, onclose }: Props = $props();

	const KIND_NOUN: Record<Props['subjectKind'], string> = {
		student: 'student',
		professor: 'professor',
		account: 'account',
	};

	let busy = $state(false);
	let issued = $state<string | null>(null);
	let error = $state<string | null>(null);
	let copied = $state(false);

	const subjectNoun = $derived(KIND_NOUN[subjectKind]);

	// The two roster routes resolve the roster row to a `users.id` server-side
	// and 409 when there is no linked account — there is no password to reset
	// in that case, and re-trying will not help.
	const describe = (e: unknown): string => {
		if (e instanceof APIError) {
			if (e.code === 'student_account_unlinked' || e.code === 'professor_account_unlinked') {
				return `This ${subjectNoun} has no linked login account, so there is no password to reset.`;
			}
			if (e.status === 403) {
				return 'You do not have permission to reset this account password.';
			}
			if (e.code === 'user_not_found') return 'That account no longer exists.';
			return e.message;
		}
		return e instanceof Error ? e.message : 'Password reset failed. Please try again.';
	};

	const confirm = async () => {
		if (busy || issued !== null) return;
		busy = true;
		error = null;
		try {
			issued = await onconfirm();
		} catch (e: unknown) {
			error = describe(e);
		} finally {
			busy = false;
		}
	};

	const copy = async () => {
		if (issued === null) return;
		try {
			await navigator.clipboard.writeText(issued);
			copied = true;
			setTimeout(() => (copied = false), 2000);
		} catch {
			// Clipboard is gated on some browsers and insecure origins; the
			// password is on screen and selectable either way, so a failure here
			// is not worth an error state.
			copied = false;
		}
	};
</script>

<div class="modal-overlay" role="presentation">
	<div class="modal" role="dialog" aria-modal="true" aria-labelledby="reset-password-title">
		<h2 id="reset-password-title" class="modal-title">
			{issued === null ? 'Reset password?' : 'New temporary password'}
		</h2>

		{#if issued === null}
			<p class="modal-text">
				This sets a new temporary password for <strong>{subject}</strong> and clears any login
				lockout. They will be required to change it the next time they sign in, and the audit
				trail records the reset against your admin account.
			</p>
			<p class="modal-text muted">
				Two-factor authentication is not affected. If they cannot get past the MFA prompt, that
				has to be cleared separately with a password-verified request — a reset is not a way
				around it.
			</p>
			{#if error}
				<p class="error" role="alert">{error}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={onclose}>Cancel</button>
				<button class="btn btn-danger" disabled={busy} onclick={confirm}>
					{busy ? 'Resetting…' : 'Reset password'}
				</button>
			</div>
		{:else}
			<p class="modal-text">
				Give this to <strong>{subject}</strong> directly. It is shown only once — closing this
				window discards it, and you will have to reset again to get a new one.
			</p>
			<div class="temp-row">
				<code class="temp-value" data-testid="temp-password">{issued}</code>
				<button class="btn btn-secondary copy" onclick={copy}>
					{copied ? 'Copied' : 'Copy'}
				</button>
			</div>
			<p class="modal-text muted">
				They must change it at their next sign-in, and it should not be sent over email or chat.
			</p>
			<div class="modal-actions">
				<button class="btn btn-primary" data-testid="reset-done" onclick={onclose}>Done</button>
			</div>
		{/if}
	</div>
</div>

<style>
	.modal-overlay {
		position: fixed;
		inset: 0;
		z-index: 100;
		background: var(--overlay);
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1rem;
	}

	.modal {
		width: 100%;
		max-width: 520px;
		max-height: 90vh;
		overflow-y: auto;
		background: var(--bg-card);
		border-radius: 12px;
		box-shadow: var(--shadow-lg);
		padding: 1.75rem 1.5rem;
		font-family: system-ui, sans-serif;
	}

	.modal-title {
		margin: 0 0 1rem;
		font-size: 1.25rem;
		font-weight: 700;
		color: var(--text);
	}

	.modal-text {
		margin: 0 0 1rem;
		font-size: 0.9375rem;
		color: var(--text-secondary);
	}

	.modal-text.muted {
		font-size: 0.8125rem;
		color: var(--text-muted);
	}

	.error {
		margin: 0 0 1rem;
		font-size: 0.8125rem;
		color: var(--danger, #dc2626);
	}

	.temp-row {
		display: flex;
		align-items: stretch;
		gap: 0.5rem;
		margin: 0 0 1rem;
	}

	/* Long enough to break anywhere beats horizontal scrolling for a string an
	   admin has to read aloud and retype. */
	.temp-value {
		flex: 1;
		min-width: 0;
		padding: 0.75rem;
		background: var(--bg-subtle, #f1f5f9);
		border: 1px solid var(--border, #e2e8f0);
		border-radius: 8px;
		font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
		font-size: 1rem;
		word-break: break-all;
		user-select: all;
		color: var(--text);
	}

	.copy {
		flex-shrink: 0;
		white-space: nowrap;
	}

	.btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		padding: 0.625rem 1.125rem;
		border: 1px solid transparent;
		border-radius: 8px;
		font-size: 0.875rem;
		font-weight: 600;
		font-family: inherit;
		cursor: pointer;
		transition: background 0.15s ease;
	}

	.btn:focus-visible {
		outline: 2px solid var(--primary, #2563eb);
		outline-offset: 2px;
	}

	.btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.btn-primary {
		background: var(--primary, #2563eb);
		color: #fff;
	}

	.btn-secondary {
		background: var(--bg-card);
		border-color: var(--border, #e2e8f0);
		color: var(--text);
	}

	.btn-ghost {
		background: transparent;
		color: var(--text-secondary);
	}

	.btn-danger {
		background: var(--danger, #dc2626);
		color: #fff;
	}

	.modal-actions {
		display: flex;
		gap: 0.75rem;
		justify-content: flex-end;
		margin-top: 1.5rem;
	}
</style>