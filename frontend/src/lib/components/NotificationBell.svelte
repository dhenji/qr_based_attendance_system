<script lang="ts">
	// NotificationBell
	// Bell toggle + dropdown panel shared by the student, professor, and
	// admin topbars. The bell shows the live badge count; clicking it opens a
	// small panel under the icon instead of navigating away, so the user
	// previews first and follows the action button only when ready.
	//
	// Data stays with the caller: layouts pass the badge count and a lazy
	// `onOpen` preview fetch (existing list endpoints only — no new API).
	// This component owns open state, outside-click/Escape dismissal, and
	// panel markup/styling (layout styles are scoped, so the bell + badge +
	// panel styles live here, not in the layouts).

	export interface NotificationBellItem {
		id: number | string;
		title: string;
		sub?: string;
	}

	let {
		count,
		buttonLabel,
		panelTitle,
		items = [],
		loading = false,
		emptyText,
		actionLabel,
		onOpen,
		onAction,
	}: {
		count: number;
		buttonLabel: string;
		panelTitle: string;
		items?: NotificationBellItem[];
		loading?: boolean;
		emptyText: string;
		actionLabel: string;
		onOpen?: () => void;
		onAction: () => void;
	} = $props();

	let open = $state(false);
	let wrap: HTMLDivElement | null = $state(null);

	const toggle = () => {
		open = !open;
		if (open) onOpen?.();
	};

	const close = () => {
		open = false;
	};

	const act = () => {
		close();
		onAction();
	};

	// svelte:window only runs in the browser, so no SSR guard is needed.
	const onWindowMouseDown = (e: MouseEvent) => {
		if (!open || !wrap) return;
		if (!wrap.contains(e.target as Node)) close();
	};

	const onWindowKeyDown = (e: KeyboardEvent) => {
		if (open && e.key === 'Escape') close();
	};
</script>

<svelte:window onmousedown={onWindowMouseDown} onkeydown={onWindowKeyDown} />

<div class="notif-wrap" bind:this={wrap}>
	<button
		type="button"
		class="bell"
		aria-haspopup="menu"
		aria-expanded={open}
		aria-label={buttonLabel}
		onclick={toggle}
	>
		<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
			<path d="M6 9a6 6 0 0 1 12 0c0 4 2 5 2 6H4c0-1 2-2 2-6Z" />
			<path d="M10 19a2 2 0 0 0 4 0" />
		</svg>
		{#if count > 0}
			<span class="badge" aria-hidden="true">{count > 9 ? '9+' : count}</span>
		{/if}
	</button>

	{#if open}
		<div class="panel" role="menu" aria-label={panelTitle}>
			<p class="panel-title">{panelTitle}</p>
			{#if loading}
				<p class="panel-muted">Loading…</p>
			{:else if items.length === 0}
				<p class="panel-muted">{emptyText}</p>
			{:else}
				<ul class="panel-list">
					{#each items as item (item.id)}
						<li>
							<p class="item-title">{item.title}</p>
							{#if item.sub}
								<p class="item-sub">{item.sub}</p>
							{/if}
						</li>
					{/each}
				</ul>
			{/if}
			<button type="button" class="panel-action" onclick={act}>{actionLabel}</button>
		</div>
	{/if}
</div>

<style>
	.notif-wrap {
		position: relative;
		flex-shrink: 0;
	}

	.bell {
		position: relative;
		display: flex;
		align-items: center;
		justify-content: center;
		width: 40px;
		height: 40px;
		border: none;
		border-radius: 8px;
		background: transparent;
		color: var(--border-strong);
		cursor: pointer;
		flex-shrink: 0;
	}

	.bell:hover {
		background: rgba(255, 255, 255, 0.1);
		color: var(--on-brand);
	}

	.bell:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.badge {
		position: absolute;
		top: 2px;
		right: 2px;
		min-width: 18px;
		height: 18px;
		padding: 0 5px;
		border-radius: 999px;
		background: var(--danger);
		color: #fff;
		font-size: 0.6875rem;
		font-weight: 700;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.panel {
		position: absolute;
		top: calc(100% + 8px);
		right: 0;
		z-index: 50;
		width: min(320px, 80vw);
		background: var(--bg-card);
		border: 1px solid var(--border-strong);
		border-radius: 12px;
		box-shadow: var(--shadow-lg);
		padding: 0.875rem;
	}

	.panel-title {
		margin: 0 0 0.5rem;
		font-size: 0.875rem;
		font-weight: 700;
		color: var(--text);
	}

	.panel-muted {
		margin: 0 0 0.75rem;
		font-size: 0.8125rem;
		color: var(--text-muted);
	}

	.panel-list {
		list-style: none;
		margin: 0 0 0.75rem;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		max-height: 240px;
		overflow-y: auto;
	}

	.panel-list li {
		padding: 0.5rem 0.625rem;
		border: 1px solid var(--divider);
		border-radius: 8px;
	}

	.item-title {
		margin: 0;
		font-size: 0.8125rem;
		font-weight: 700;
		color: var(--text-strong);
	}

	.item-sub {
		margin: 0.125rem 0 0;
		font-size: 0.75rem;
		color: var(--text-muted);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.panel-action {
		width: 100%;
		padding: 0.625rem 1rem;
		border: none;
		border-radius: 8px;
		background: var(--brand);
		color: var(--on-brand);
		font-size: 0.875rem;
		font-weight: 600;
		font-family: inherit;
		cursor: pointer;
	}

	.panel-action:hover {
		background: var(--brand-hover);
	}

	.panel-action:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}
</style>
