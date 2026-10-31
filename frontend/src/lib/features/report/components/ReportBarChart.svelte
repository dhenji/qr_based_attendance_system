<script lang="ts">
	// ReportBarChart
	// Dependency-free horizontal SVG bars for aggregate and comparison reports.
	// The page always renders an equivalent data table beside the chart, so the
	// SVG remains presentational while assistive technology uses the table.
	type BarDatum = {
		label: string;
		value: number;
		detail?: string;
	};

	type ReportBarChartProps = {
		title: string;
		description: string;
		bars: BarDatum[];
		average?: number | null;
		emptyMessage?: string;
	};

	let {
		title,
		description,
		bars,
		average = null,
		emptyMessage = 'No report data for the selected filters.'
	}: ReportBarChartProps = $props();

	const width = 640;
	const labelWidth = 230;
	const chartWidth = 370;
	const barHeight = 20;
	const gap = 10;
	const topPad = 32;
	const bottomPad = 16;
	const height = $derived(topPad + Math.max(1, bars.length) * (barHeight + gap) + bottomPad);
	const maxValue = $derived(Math.max(1, average ?? 0, ...bars.map((bar) => bar.value)));
	const barWidth = (value: number): number => Math.max(2, (value / maxValue) * chartWidth);
	const percent = (value: number): string => `${Math.round(value * 100)}%`;
	const truncate = (value: string): string =>
		value.length > 30 ? `${value.slice(0, 28)}…` : value;
	const titleId = $derived(`${title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}-chart`);
</script>

<div class="chart">
	{#if bars.length === 0}
		<p class="empty">{emptyMessage}</p>
	{:else}
		<svg
			viewBox={`0 0 ${width} ${height}`}
			role="img"
			aria-labelledby={titleId}
			aria-describedby={`${titleId}-description`}
		>
			<title id={titleId}>{title}</title>
			<desc id={`${titleId}-description`}>{description}</desc>
			{#each bars as bar, index (bar.label)}
				{@const y = topPad + index * (barHeight + gap)}
				{@const valueX = labelWidth + barWidth(bar.value)}
				<text x={labelWidth - 12} y={y + 15} text-anchor="end" class="label">
					<title>{bar.label}</title>
					{truncate(bar.label)}
				</text>
				<rect
					x={labelWidth}
					y={y}
					width={chartWidth}
					height={barHeight}
					rx="6"
					class="track"
				/>
				<rect
					x={labelWidth}
					y={y}
					width={barWidth(bar.value)}
					height={barHeight}
					rx="6"
					class="bar"
				/>
				<text x={valueX + 8} y={y + 15} class="value">
					{percent(bar.value)}{bar.detail ? ` · ${bar.detail}` : ''}
				</text>
			{/each}
			{#if average !== null}
				{@const averageX = labelWidth + (average / maxValue) * chartWidth}
				<line
					x1={averageX}
					y1={topPad - 6}
					x2={averageX}
					y2={height - bottomPad + 6}
					class="average"
				/>
				<text x={averageX} y={topPad - 10} text-anchor="middle" class="average-label">
					Average {percent(average)}
				</text>
			{/if}
		</svg>
	{/if}
</div>

<style>
	.chart {
		width: 100%;
		overflow-x: auto;
	}

	svg {
		display: block;
		width: 100%;
		min-width: 480px;
		height: auto;
	}

	.label,
	.value {
		font-size: 11px;
		fill: var(--text-secondary);
	}

	.value {
		font-weight: 700;
		fill: var(--text-strong);
	}

	.track {
		fill: var(--bg-page);
		stroke: var(--border);
		stroke-width: 1;
	}

	.bar {
		fill: var(--accent);
	}

	.average {
		stroke: var(--success);
		stroke-width: 2;
		stroke-dasharray: 6 4;
	}

	.average-label {
		font-size: 10px;
		font-weight: 700;
		fill: var(--success);
	}

	.empty {
		margin: 0;
		color: var(--text-muted);
	}
</style>
