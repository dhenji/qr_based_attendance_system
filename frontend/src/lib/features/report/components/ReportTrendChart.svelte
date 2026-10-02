<script lang="ts">
	// ReportTrendChart
	// Dependency-free multi-series SVG line chart. Rates are always scaled from
	// zero to 100% so separate courses remain visually comparable. The page also
	// renders the same points in a table.
	type TrendChartPoint = {
		x: string;
		y: number;
	};

	type TrendChartSeries = {
		label: string;
		color: string;
		points: TrendChartPoint[];
	};

	type ReportTrendChartProps = {
		title: string;
		description: string;
		series: TrendChartSeries[];
		emptyMessage?: string;
	};

	let {
		title,
		description,
		series,
		emptyMessage = 'No trend data for the selected filters.'
	}: ReportTrendChartProps = $props();

	const width = 640;
	const height = 300;
	const padLeft = 48;
	const padRight = 16;
	const padTop = 20;
	const padBottom = 48;
	const plotWidth = width - padLeft - padRight;
	const plotHeight = height - padTop - padBottom;

	const labels = $derived(
		[...new Set(series.flatMap((item) => item.points.map((point) => point.x)))]
	);
	const xFor = (index: number): number =>
		labels.length <= 1 ? padLeft + plotWidth / 2 : padLeft + (index / (labels.length - 1)) * plotWidth;
	const yFor = (rate: number): number => padTop + (1 - Math.min(1, Math.max(0, rate))) * plotHeight;
	const pathFor = (points: TrendChartPoint[]): string =>
		points
			.map((point, index) => `${index === 0 ? 'M' : 'L'}${xFor(labels.indexOf(point.x)).toFixed(1)},${yFor(point.y).toFixed(1)}`)
			.join(' ');
	const percent = (value: number): string => `${Math.round(value * 100)}%`;
	const titleId = $derived(`${title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}-trend`);
</script>

<div class="chart">
	{#if series.length === 0 || labels.length === 0}
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
			{#each [0, 0.25, 0.5, 0.75, 1] as grid (grid)}
				<line
					x1={padLeft}
					y1={yFor(grid)}
					x2={width - padRight}
					y2={yFor(grid)}
					class="grid"
				/>
				<text x={padLeft - 8} y={yFor(grid) + 4} text-anchor="end" class="axis">
					{percent(grid)}
				</text>
			{/each}
			{#each series as item (item.label)}
				<path d={pathFor(item.points)} fill="none" stroke={item.color} stroke-width="2.5" />
				{#each item.points as point (point.x)}
					<circle cx={xFor(labels.indexOf(point.x))} cy={yFor(point.y)} r="3.5" fill={item.color}>
						<title>{item.label}: {point.x}, {percent(point.y)}</title>
					</circle>
				{/each}
			{/each}
			{#each labels as label, index (label)}
				<text
					x={xFor(index)}
					y={height - 12}
					text-anchor="middle"
					class="axis"
				>
					{label}
				</text>
			{/each}
		</svg>
		<ul class="legend">
			{#each series as item (item.label)}
				<li>
					<span class="swatch" style={`background: ${item.color}`} aria-hidden="true"></span>
					{item.label}
				</li>
			{/each}
		</ul>
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
		min-width: 520px;
		height: auto;
	}

	.grid {
		stroke: var(--border);
		stroke-width: 1;
	}

	.axis {
		font-size: 12px;
		fill: var(--text-muted);
	}

	.legend {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem 1rem;
		list-style: none;
		margin: 0.75rem 0 0;
		padding: 0;
		font-size: 0.8125rem;
		color: var(--text-secondary);
	}

	.swatch {
		display: inline-block;
		width: 0.75rem;
		height: 0.75rem;
		border-radius: 999px;
		margin-right: 0.375rem;
	}

	.empty {
		margin: 0;
		color: var(--text-muted);
	}
</style>
