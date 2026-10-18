<script lang="ts">
	import { formatPercentage } from '$lib/shared/utils/format';

	interface Props {
		// Already scaled to 0–100 by `complianceRate()` in the student store —
		// the wire value is a 0-1 fraction.
		complianceRate: number;
		// False while the student has no scans, so we can say "No data" instead of
		// implying a genuine 0% attendance record.
		hasData: boolean;
	}

	let { complianceRate, hasData }: Props = $props();
</script>

<div class="attendance-rate">
	<span class="rate-value" class:placeholder={!hasData}>
		{hasData ? formatPercentage(complianceRate) : 'No data'}
	</span>
	<span class="rate-label">Attendance Rate</span>
	<span class="rate-hint">
		{hasData
			? 'Present scans across all expected sessions.'
			: 'Your rate will appear after your first scans.'}
	</span>
</div>

<style>
	.attendance-rate {
		display: flex;
		flex-direction: column;
		justify-content: center;
		align-items: center;
		gap: 0.5rem;
		padding: 2.5rem 1.5rem;
		background: var(--brand);
		border-radius: 8px;
		color: var(--on-brand);
		box-shadow: var(--shadow-sm);
		text-align: center;
	}

	.rate-value {
		font-family: var(--font-data);
		font-variant-numeric: tabular-nums;
		font-size: 3.75rem;
		font-weight: 500;
		letter-spacing: -0.01em;
		line-height: 1;
	}

	/* "No data" is a sentence, not a number — it keeps the UI face. */
	.rate-value.placeholder {
		font-family: var(--font-ui);
		font-size: 2.5rem;
		color: color-mix(in srgb, var(--on-brand) 90%, transparent);
	}

	.rate-label {
		font-size: 1rem;
		font-weight: 700;
		letter-spacing: 0.02em;
	}

	.rate-hint {
		font-size: 0.8125rem;
		color: color-mix(in srgb, var(--on-brand) 85%, transparent);
	}
</style>
