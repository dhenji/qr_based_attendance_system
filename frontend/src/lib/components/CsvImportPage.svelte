<script lang="ts">
	import { goto } from '$app/navigation';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import { csvFileSchema } from '$lib/features/admin/schema';
	import { notifyEntityChanged, type AdminEntity } from '$lib/shared/utils/entityEvents';
	import { downloadTextFile } from '$lib/shared/utils/file';

	// Shared CSV import page (students/professors pattern, reused by
	// programs/courses): Step 1 download template, Step 2 upload file,
	// Step 3 preview + confirm against a POST /admin/*/import endpoint.
	// The backend creates NEW records; duplicates are skipped and errors
	// are reported per line as { imported, duplicates, errors }.

	interface ImportResult {
		imported: number;
		duplicates: number;
		errors: { line: number; reason: string }[];
	}

	interface Props {
		title: string;
		subtitle: string;
		columnsHelp: string;
		templateFilename: string;
		errorsFilename: string;
		expectedHeaders: string[];
		endpointNote: string;
		templateNote: string;
		backLabel: string;
		backHref: string;
		/** Entity key for notifyEntityChanged on success (e.g. 'programs'). */
		entityEvent?: AdminEntity;
		downloadTemplate: () => Promise<string>;
		importFile: (file: File) => Promise<ImportResult>;
	}

	let {
		title,
		subtitle,
		columnsHelp,
		templateFilename,
		errorsFilename,
		expectedHeaders,
		endpointNote,
		templateNote,
		backLabel,
		backHref,
		entityEvent,
		downloadTemplate: fetchTemplate,
		importFile,
	}: Props = $props();

	let file = $state<File | null>(null);
	let fileError = $state<string | null>(null);
	let templateBusy = $state(false);
	let importBusy = $state(false);
	let importError = $state<string | null>(null);
	let result = $state<ImportResult | null>(null);
	let isDragging = $state(false);
	let fileInput = $state<HTMLInputElement | null>(null);
	let showAllErrors = $state(false);

	// Client pre-flight preview: parsed locally before POST so a bad header
	// or empty file is caught without paying an upload.
	type CsvPreview = {
		headers: string[];
		rowCount: number;
		firstRows: string[][];
		headerOk: boolean;
	};
	let preview = $state<CsvPreview | null>(null);

	const parseCsvPreview = (text: string): CsvPreview => {
		const lines = text.split(/\r?\n/).filter((line) => line.trim().length > 0);
		// Quote-aware split: commas inside "..." (e.g. "Doe, Jr.") must not
		// split cells. Doubled quotes ("") collapse to one.
		const splitRow = (line: string): string[] => {
			const cells: string[] = [];
			let current = '';
			let inQuotes = false;
			for (let i = 0; i < line.length; i += 1) {
				const ch = line[i];
				if (ch === '"') {
					if (inQuotes && line[i + 1] === '"') {
						current += '"';
						i += 1;
					} else {
						inQuotes = !inQuotes;
					}
				} else if (ch === ',' && !inQuotes) {
					cells.push(current.trim());
					current = '';
				} else {
					current += ch;
				}
			}
			cells.push(current.trim());
			return cells;
		};
		const headers = lines.length > 0 ? splitRow(lines[0]) : [];
		const rows = lines.slice(1).map(splitRow);
		const normalized = headers.map((h) => h.toLowerCase());
		return {
			headers,
			rowCount: rows.length,
			firstRows: rows.slice(0, 5),
			headerOk: expectedHeaders.every((h, i) => normalized[i] === h),
		};
	};

	// Single validation path shared by the file picker and drag-and-drop, so
	// both surface the same csvFileSchema errors (extension, empty, 5 MB cap).
	// Rapid picks overlap on the async text read; a stale read must not
	// clobber a newer file's preview (seq counter, same pattern as
	// student/history's loadSeq).
	let pickSeq = 0;
	const handleFile = async (picked: File | null) => {
		const seq = ++pickSeq;
		fileError = null;
		importError = null;
		result = null;
		preview = null;
		showAllErrors = false;
		if (!picked) {
			file = null;
			return;
		}
		const parsed = csvFileSchema.safeParse(picked);
		if (!parsed.success) {
			file = null;
			fileError = parsed.error.issues[0]?.message ?? 'Invalid file.';
			return;
		}
		file = parsed.data;
		try {
			const previewData = parseCsvPreview(await picked.text());
			if (seq !== pickSeq) return;
			preview = previewData;
		} catch {
			if (seq !== pickSeq) return;
			preview = null;
		}
	};

	const onFileChange = (e: Event) => {
		const input = e.currentTarget as HTMLInputElement;
		void handleFile(input.files?.[0] ?? null);
	};

	const onDragOver = (e: DragEvent) => {
		// preventDefault is what stops the browser from navigating to the file.
		e.preventDefault();
		isDragging = true;
	};

	const onDrop = (e: DragEvent) => {
		e.preventDefault();
		isDragging = false;
		// Multi-file drops keep the first entry and ignore the rest.
		void handleFile(e.dataTransfer?.files?.[0] ?? null);
	};

	// Clear the attachment (✕ button). The input value is reset too, so
	// picking the same file again still fires a change event. Result state is
	// cleared with it — it described the removed file's import.
	const clearFile = () => {
		file = null;
		fileError = null;
		importError = null;
		result = null;
		preview = null;
		showAllErrors = false;
		if (fileInput) fileInput.value = '';
	};

	const downloadTemplateFile = async () => {
		templateBusy = true;
		try {
			// fetchTemplate never throws for static fallbacks (server text
			// when reachable, matching static header otherwise) — only the
			// DOM download below could.
			const text = await fetchTemplate();
			downloadTextFile(text, templateFilename, 'text/csv');
		} finally {
			templateBusy = false;
		}
	};

	const downloadErrorsCsv = () => {
		if (!result || result.errors.length === 0) return;
		const lines = ['line,reason', ...result.errors.map((e) => `${e.line},"${String(e.reason).replace(/"/g, '""')}"`)];
		downloadTextFile(lines.join('\r\n'), errorsFilename, 'text/csv');
	};

	const confirmImport = async () => {
		if (!file) {
			fileError = 'Choose a CSV file first.';
			return;
		}
		importBusy = true;
		importError = null;
		// Clear the previous result so a retry never shows stale counts
		// alongside the spinner.
		result = null;
		showAllErrors = false;
		try {
			result = await importFile(file);
			// The list page remounts fresh on Back, but emit anyway so any
			// mounted table updates.
			if (result.imported > 0 && entityEvent) notifyEntityChanged(entityEvent);
		} catch (e: unknown) {
			importError = e instanceof Error && e.message ? e.message : 'Import failed. Please try again.';
		} finally {
			importBusy = false;
		}
	};
</script>

<div class="page">
	<header class="header">
		<div>
			<h1>{title}</h1>
			<p class="muted">{subtitle}</p>
		</div>
	</header>

	<section class="card">
		<h2 class="section-title">Step 1: Download Template</h2>
		<p class="muted">{columnsHelp}</p>
		<div class="actions">
			<button class="btn btn-secondary" disabled={templateBusy} onclick={downloadTemplateFile}>
				<AppIcon name="file" size={18} />
				{templateBusy ? 'Preparing…' : 'Download CSV Template'}
			</button>
		</div>
		<p class="muted">{templateNote}</p>
	</section>

	<section class="card">
		<h2 class="section-title">Step 2: Upload File</h2>
		<label
			class="drop"
			class:dragging={isDragging}
			for="csv-input"
			ondragover={onDragOver}
			ondragleave={() => (isDragging = false)}
			ondrop={onDrop}
		>
			<input
				id="csv-input"
				type="file"
				accept=".csv,text/csv"
				bind:this={fileInput}
				onchange={onFileChange}
			/>
			{#if file}
				<span class="file-row">
					<span class="file-name">{file.name} · {(file.size / 1024).toFixed(1)} KB</span>
					<button
						type="button"
						class="icon-x"
						aria-label="Remove file"
						data-testid="remove-file"
						onclick={(e) => {
							// The button sits inside the picker label — without this the
							// click would bubble up and reopen the file dialog.
							e.preventDefault();
							e.stopPropagation();
							clearFile();
						}}
					>
						✕
					</button>
				</span>
			{:else if isDragging}
				<span class="file-name">Drop your CSV to attach it</span>
			{:else}
				<span class="muted">Drag &amp; drop your CSV here or click to browse</span>
			{/if}
		</label>
		{#if fileError}
			<p class="error" role="alert">{fileError}</p>
		{/if}
	</section>

	<section class="card">
		<h2 class="section-title">Step 3: Preview &amp; Confirm</h2>
		{#if result === null}
			<p class="muted">
				{file
					? preview
						? `Ready to import ${file.name} — ${preview.rowCount} data row${preview.rowCount === 1 ? '' : 's'}. Confirm sends it to ${endpointNote}.`
						: `Reading ${file.name}… Confirm sends it to ${endpointNote}.`
					: 'Upload a file to enable the import button.'}
			</p>
			{#if preview && file}
				{#if !preview.headerOk}
					<p class="error" role="alert">
						Header mismatch — expected: {expectedHeaders.join(', ')}. Found: {preview.headers.join(', ') || '(none)'}.
					</p>
				{/if}
				<ul class="errors preview-list">
					{#each preview.firstRows as row, i (i)}
						<li>Row {i + 2}: {row.join(' · ')}</li>
					{/each}
				</ul>
				{#if preview.rowCount > preview.firstRows.length}
					<p class="muted">…and {preview.rowCount - preview.firstRows.length} more rows.</p>
				{/if}
			{/if}
		{:else}
			<div class="result">
				<span class="pill ok">{result.imported} new</span>
				<span class="pill">{result.duplicates} duplicates</span>
				<span class="pill warn">{result.errors.length} errors</span>
			</div>
			{#if result.errors.length > 0}
				<ul class="errors errors-scroll">
					{#each (showAllErrors ? result.errors : result.errors.slice(0, 10)) as err, i (i)}
						<li>Line {err.line}: {err.reason}</li>
					{/each}
				</ul>
				<div class="actions">
					{#if result.errors.length > 10}
						<button class="btn btn-secondary" type="button" onclick={() => (showAllErrors = !showAllErrors)}>
							{showAllErrors ? 'Show fewer' : `Show all ${result.errors.length}`}
						</button>
					{/if}
					<button class="btn btn-secondary" type="button" onclick={downloadErrorsCsv}>
						Download errors.csv
					</button>
				</div>
				{#if !showAllErrors && result.errors.length > 10}
					<p class="muted">…and {result.errors.length - 10} more.</p>
				{/if}
			{/if}
		{/if}
		{#if importError}
			<p class="error" role="alert">{importError}</p>
		{/if}
		<div class="actions">
			<button
				class="btn btn-primary"
				data-testid="confirm-import"
				disabled={!file || importBusy}
				onclick={confirmImport}
			>
				{importBusy ? 'Importing…' : result ? 'Import again' : 'Confirm Import'}
			</button>
			<button class="btn btn-secondary" onclick={() => goto(backHref)}>
				{backLabel}
			</button>
		</div>
	</section>
</div>

<style>
	.page {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
	}

	.header h1 {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.625rem;
		font-weight: 700;
		color: var(--text);
		margin: 0 0 0.25rem;
	}

	.muted {
		color: var(--text-muted);
		font-size: 0.875rem;
		margin: 0;
	}

	.card {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 1.5rem;
		box-shadow: var(--shadow-sm);
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.section-title {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.0625rem;
		font-weight: 700;
		color: var(--text);
		margin: 0;
	}

	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
	}

	.drop {
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 2rem 1rem;
		border: 2px dashed var(--border-strong);
		border-radius: 8px;
		background: var(--bg-page);
		cursor: pointer;
		text-align: center;
	}

	.drop input {
		display: none;
	}

	.drop.dragging {
		border-style: solid;
		border-color: var(--accent);
		background: var(--info-bg);
	}

	.file-name {
		font-weight: 600;
		color: var(--text-strong);
		font-size: 0.9375rem;
	}

	.file-row {
		display: inline-flex;
		align-items: center;
		gap: 0.625rem;
	}

	.icon-x {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 1.75rem;
		height: 1.75rem;
		border: 1px solid var(--border-strong);
		border-radius: 50%;
		background: var(--bg-card);
		color: var(--text-muted);
		font-size: 0.875rem;
		line-height: 1;
		cursor: pointer;
		flex-shrink: 0;
		transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
	}

	.icon-x:hover {
		background: var(--danger-bg);
		border-color: var(--danger-strong);
		color: var(--danger);
	}

	.icon-x:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.result {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.pill {
		display: inline-block;
		padding: 0.25rem 0.625rem;
		border-radius: 99px;
		background: var(--divider);
		border: 1px solid var(--border);
		color: var(--text-secondary);
		font-size: 0.8125rem;
		font-weight: 700;
	}

	.pill.ok {
		background: var(--success-bg);
		border-color: var(--success-bg);
		color: var(--success);
	}

	.pill.warn {
		background: var(--warning-bg);
		border-color: var(--warning-bg);
		color: var(--warning-text);
	}

	.errors {
		margin: 0;
		padding-left: 1.25rem;
		color: var(--danger-strong);
		font-size: 0.875rem;
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.errors-scroll {
		max-height: 15rem;
		overflow-y: auto;
	}

	.preview-list {
		color: var(--text-secondary);
	}

	.error {
		color: var(--danger);
		font-size: 0.875rem;
		margin: 0;
	}

	@media (max-width: 640px) {
		.card {
			padding: 1.25rem;
		}
	}
</style>
