<script lang="ts">
	// Two-factor authentication settings, shared by every role's personal
	// settings surface (student/settings, professor/settings, admin/profile).
	//
	// One component for all three because MFA is one account-level control with
	// one backend implementation — the per-role pages previously each rendered
	// their own read-only "Configured / Not configured" line, which meant there
	// was no way to actually turn it on.
	//
	// The field is TWO-WRITER on the backend and this component never patches it
	// directly: `verify_mfa` is the only writer of True, `disable_mfa` the only
	// path back to False. So enabling is deliberately a two-call flow — setup
	// mints a secret but enables nothing, and only the confirm step flips the
	// flag. Reading `authState.user.mfaEnabled` to decide which buttons to show
	// is fine; writing it is not, and the store actions own that.
	import { browser } from '$app/environment';
	import QRCode from 'qrcode';
	import { APIError } from '$lib/api/client';
	import {
		authState,
		doMfaConfirmSetup,
		doMfaDisable,
	} from '$lib/features/auth/store.svelte';
	import {
		generateBackupCodes,
		listBackupCodes,
		setupMfa,
	} from '$lib/features/auth/service';
	import type { BackupCodesSummaryResponse } from '$lib/shared/types';
	import { trapFocus } from '$lib/shared/actions/focusTrap';

	const mfaEnabled = $derived(authState.user?.mfaEnabled === true);

	// Backup-code counts are readable whether or not MFA is on (the route has no
	// state gate), so pre-emptive generation before enabling is possible.
	let summary = $state<BackupCodesSummaryResponse | null>(null);

	// Setup modal.
	let setupOpen = $state(false);
	let setup = $state<{ secret: string; qr_url: string; manual_entry_key: string } | null>(null);
	let qrDataUrl = $state<string | null>(null);
	let setupBusy = $state(false);
	let setupError = $state<string | null>(null);
	let setupCode = $state('');
	let secretCopied = $state(false);

	// Backup codes modal.
	let codesOpen = $state(false);
	let issuedCodes = $state<string[] | null>(null);
	let codesBusy = $state(false);
	let codesError = $state<string | null>(null);
	let codesCopied = $state(false);

	// Disable modal.
	let disableOpen = $state(false);
	let disablePassword = $state('');
	let disableBusy = $state(false);
	let disableError = $state<string | null>(null);

	const refreshSummary = async () => {
		try {
			summary = await listBackupCodes();
		} catch {
			summary = null;
		}
	};

	$effect(() => {
		void refreshSummary();
	});

	// The backend returns `qr_url` as a raw otpauth:// provisioning URI, not an
	// image, so the browser renders it. If that fails we fall through to the
	// manual key rather than re-calling setup: a second setup call silently
	// overwrites the secret the user may already have scanned.
	const renderQr = async (uri: string) => {
		if (!browser) return;
		try {
			qrDataUrl = await QRCode.toDataURL(uri, { margin: 1, width: 220 });
		} catch {
			qrDataUrl = null;
		}
	};

	const openSetup = async () => {
		setupOpen = true;
		setupBusy = true;
		setupError = null;
		setup = null;
		qrDataUrl = null;
		setupCode = '';
		try {
			setup = await setupMfa();
			await renderQr(setup.qr_url);
		} catch (e: unknown) {
			setupError = describe(e, 'Could not start MFA setup.');
		} finally {
			setupBusy = false;
		}
	};

	const closeSetup = () => {
		setupOpen = false;
		setup = null;
		qrDataUrl = null;
		setupCode = '';
		setupError = null;
	};

	const confirmSetup = async () => {
		const code = setupCode.trim();
		if (!code || setupBusy) return;
		setupBusy = true;
		setupError = null;
		try {
			await doMfaConfirmSetup(code);
			closeSetup();
			await refreshSummary();
		} catch (e: unknown) {
			setupError = describe(e, 'That code was not accepted.');
		} finally {
			setupBusy = false;
		}
	};

	const openCodes = async () => {
		codesOpen = true;
		issuedCodes = null;
		codesError = null;
		codesCopied = false;
		await generateCodes();
	};

	const generateCodes = async () => {
		if (codesBusy) return;
		codesBusy = true;
		codesError = null;
		try {
			const result = await generateBackupCodes();
			issuedCodes = result.codes;
			await refreshSummary();
		} catch (e: unknown) {
			codesError = describe(e, 'Could not generate backup codes.');
		} finally {
			codesBusy = false;
		}
	};

	const closeCodes = () => {
		codesOpen = false;
		issuedCodes = null;
		codesError = null;
		codesCopied = false;
	};

	// Shared by the Cancel button and the Escape key on the disable dialog, so
	// the password field and error never survive a dismissal.
	const closeDisable = () => {
		disableOpen = false;
		disablePassword = '';
		disableError = null;
	};

	const confirmDisable = async () => {
		if (!disablePassword || disableBusy) return;
		disableBusy = true;
		disableError = null;
		try {
			await doMfaDisable(disablePassword);
			disableOpen = false;
			disablePassword = '';
			await refreshSummary();
		} catch (e: unknown) {
			disableError = describe(e, 'Could not disable MFA.');
		} finally {
			disableBusy = false;
		}
	};

	// Domain codes worth wording precisely; anything else falls through to the
	// server's message.
	const describe = (e: unknown, fallback: string): string => {
		if (e instanceof APIError) {
			switch (e.code) {
				case 'mfa_already_enabled':
					return 'MFA is already enabled on this account. Reload the page to see the current settings.';
				case 'mfa_not_enabled':
					return 'MFA is not enabled on this account.';
				case 'current_password_invalid':
					return 'That password is not correct.';
				case 'invalid_mfa_code':
					return 'That code was not accepted. Check your authenticator and try the next code.';
				default:
					return e.message || fallback;
			}
		}
		return e instanceof Error && e.message ? e.message : fallback;
	};

	// Clipboard is gated on insecure origins; the secret and codes are both on
	// screen and selectable, so a copy failure is not worth surfacing.
	const copy = async (text: string, onDone: (ok: boolean) => void) => {
		try {
			await navigator.clipboard.writeText(text);
			onDone(true);
		} catch {
			onDone(false);
		}
	};
</script>

<section class="card">
	<div class="head">
		<div>
			<h2>Two-factor authentication</h2>
			<p class="muted">
				{#if mfaEnabled}
					Enabled. Your account asks for an authenticator code at every sign-in.
				{:else}
					Not enabled. Add a second step so a stolen password alone cannot sign in.
				{/if}
			</p>
		</div>
		<span class="pill" class:on={mfaEnabled}>{mfaEnabled ? 'Enabled' : 'Off'}</span>
	</div>

	{#if summary && summary.total > 0}
		<p class="muted codes-count">
			{summary.remaining} of {summary.total} backup codes remaining.
		</p>
	{/if}

	<div class="actions">
		{#if mfaEnabled}
			<button class="btn btn-secondary" onclick={openCodes}>Regenerate backup codes</button>
			<button class="btn btn-danger" onclick={() => ((disableOpen = true), (disableError = null))}>
				Disable MFA
			</button>
		{:else}
			<button class="btn btn-primary" onclick={openSetup}>Enable MFA</button>
		{/if}
	</div>
</section>

{#if setupOpen}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="mfa-setup-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: closeSetup }}
		>
			<h2 id="mfa-setup-title" class="modal-title">Set up MFA</h2>

			{#if setupBusy && !setup}
				<p class="muted">Generating your secret…</p>
			{:else if setupError && !setup}
				<p class="error" role="alert">{setupError}</p>
				<div class="modal-actions">
					<button class="btn btn-ghost" onclick={closeSetup}>Cancel</button>
				</div>
			{:else if setup}
				<p class="modal-text">
					Scan this with an authenticator app (Google Authenticator, Authy, 1Password), then
					enter the six-digit code it shows.
				</p>

				{#if qrDataUrl}
					<div class="qr">
						<img src={qrDataUrl} alt="Authenticator setup QR code" />
					</div>
				{/if}

				<label class="field">
					Manual entry key
					<span class="key-row">
						<code class="key">{setup.manual_entry_key}</code>
						<button
							class="btn btn-secondary copy"
							onclick={() => copy(setup!.manual_entry_key, (ok) => (secretCopied = ok))}
						>
							{secretCopied ? 'Copied' : 'Copy'}
						</button>
					</span>
				</label>

				<label class="field">
					Authenticator code
					<input
						class="input mono"
						inputmode="numeric"
						autocomplete="one-time-code"
						maxlength="16"
						bind:value={setupCode}
						placeholder="123456"
					/>
					<span class="hint">
						A backup code works here too, if you generated one before enabling.
					</span>
				</label>

				{#if setupError}
					<p class="error" role="alert">{setupError}</p>
				{/if}

				<p class="hint">
					{#if qrDataUrl}
						Nothing is enabled yet — confirming the code is what turns MFA on.
					{:else}
						The QR could not be drawn, so use the manual key above.
					{/if}
				</p>

				<div class="modal-actions">
					<button class="btn btn-ghost" onclick={closeSetup}>Cancel</button>
					<button
						class="btn btn-primary"
						data-testid="mfa-confirm"
						disabled={setupBusy || !setupCode.trim()}
						onclick={confirmSetup}
					>
						{setupBusy ? 'Verifying…' : 'Verify and enable'}
					</button>
				</div>
			{/if}
		</div>
	</div>
{/if}

{#if codesOpen}
	<div class="modal-overlay" role="presentation">
		<!-- Escape closes only the pre-issue step. Once the codes are on screen
		     they are shown exactly once, so the dialog becomes Escape-inert
		     rather than letting a stray keypress discard them. -->
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="mfa-codes-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: issuedCodes ? undefined : closeCodes }}
		>
			<h2 id="mfa-codes-title" class="modal-title">
				{issuedCodes ? 'Save your backup codes' : 'Generate backup codes'}
			</h2>

			{#if codesBusy && !issuedCodes}
				<p class="muted">Generating…</p>
			{:else if issuedCodes}
				<p class="modal-text">
					Each code works once, in place of an authenticator code. They are shown only now —
					closing this discards them.
				</p>
				<ul class="codes">
					{#each issuedCodes as code (code)}
						<li><code>{code}</code></li>
					{/each}
				</ul>
				<div class="modal-actions">
					<button
						class="btn btn-secondary"
						onclick={() => copy(issuedCodes!.join('\n'), (ok) => (codesCopied = ok))}
					>
						{codesCopied ? 'Copied' : 'Copy all'}
					</button>
					<button class="btn btn-primary" data-testid="codes-done" onclick={closeCodes}>
						Done
					</button>
				</div>
			{:else}
				{#if codesError}
					<p class="error" role="alert">{codesError}</p>
				{/if}
				<div class="modal-actions">
					<button class="btn btn-ghost" onclick={closeCodes}>Cancel</button>
					<button class="btn btn-primary" disabled={codesBusy} onclick={generateCodes}>
						Generate
					</button>
				</div>
			{/if}
		</div>
	</div>
{/if}

{#if disableOpen}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="mfa-disable-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: closeDisable }}
		>
			<h2 id="mfa-disable-title" class="modal-title">Disable MFA?</h2>
			<p class="modal-text">
				Your account will be protected by password alone again, and any unused backup codes are
				voided in the same step. This needs your password, not just this session.
			</p>
			<label class="field">
				Password
				<input
					class="input"
					type="password"
					autocomplete="current-password"
					bind:value={disablePassword}
				/>
			</label>
			{#if disableError}
				<p class="error" role="alert">{disableError}</p>
			{/if}
			<div class="modal-actions">
				<button
					class="btn btn-ghost"
					onclick={closeDisable}
				>
					Cancel
				</button>
				<button
					class="btn btn-danger"
					disabled={disableBusy || !disablePassword}
					onclick={confirmDisable}
				>
					{disableBusy ? 'Disabling…' : 'Disable MFA'}
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.card {
		padding: 1.5rem;
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 12px;
	}

	.head {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 1rem;
	}

	h2 {
		margin: 0 0 0.25rem;
		font-size: 1.0625rem;
		font-weight: 700;
		color: var(--text);
	}

	.muted {
		margin: 0;
		font-size: 0.875rem;
		color: var(--text-muted);
	}

	.codes-count {
		margin-top: 0.75rem;
	}

	.pill {
		flex-shrink: 0;
		padding: 0.25rem 0.625rem;
		border-radius: 999px;
		background: var(--bg-subtle, #f1f5f9);
		color: var(--text-muted);
		font-size: 0.75rem;
		font-weight: 600;
	}

	.pill.on {
		background: #dcfce7;
		color: #15803d;
	}

	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		margin-top: 1.25rem;
	}

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

	.qr {
		display: flex;
		justify-content: center;
		margin: 0 0 1.25rem;
	}

	.qr img {
		width: 220px;
		height: 220px;
		background: #fff;
		padding: 8px;
		border: 1px solid var(--border, #e2e8f0);
		border-radius: 8px;
	}

	.field {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
		margin-bottom: 1rem;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-secondary);
	}

	.key-row {
		display: flex;
		align-items: stretch;
		gap: 0.5rem;
	}

	.key {
		flex: 1;
		min-width: 0;
		padding: 0.625rem 0.75rem;
		background: var(--bg-subtle, #f1f5f9);
		border: 1px solid var(--border, #e2e8f0);
		border-radius: 8px;
		font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
		font-size: 0.875rem;
		word-break: break-all;
		user-select: all;
		color: var(--text);
	}

	.input {
		padding: 0.625rem 0.75rem;
		background: var(--bg-card);
		border: 1px solid var(--border, #e2e8f0);
		border-radius: 8px;
		font-size: 0.9375rem;
		font-family: inherit;
		color: var(--text);
	}

	.mono {
		font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
	}

	.copy {
		flex-shrink: 0;
		white-space: nowrap;
	}

	.hint {
		margin: 0;
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.error {
		margin: 0 0 1rem;
		font-size: 0.8125rem;
		color: var(--danger, #dc2626);
	}

	.codes {
		list-style: none;
		margin: 0 0 1rem;
		padding: 0.75rem;
		background: var(--bg-subtle, #f1f5f9);
		border: 1px solid var(--border, #e2e8f0);
		border-radius: 8px;
		font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
		font-size: 0.875rem;
		/* Two columns so ten codes stay readable without scrolling. */
		columns: 2;
	}

	.codes li {
		padding: 0.125rem 0;
		break-inside: avoid;
	}

	.modal-actions {
		display: flex;
		gap: 0.75rem;
		justify-content: flex-end;
		margin-top: 1.5rem;
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
</style>