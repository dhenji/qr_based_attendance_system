<script lang="ts">
	import { formatPercentage } from '$lib/shared/utils/format';

	interface Props {
		// 0–100 from GET /student/dashboard.
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
		background: #1e3a5f;
		border-radius: 8px;
		color: white;
		box-shadow: 0 8px 24px rgba(30, 58, 95, 0.25);
		text-align: center;
	}

	.rate-value {
		font-family: system-ui, sans-serif;
		font-size: 3.5rem;
		font-weight: 700;
		line-height: 1;
	}

	.rate-value.placeholder {
		font-size: 2.5rem;
		color: rgba(255, 255, 255, 0.9);
	}

	.rate-label {
		font-size: 1rem;
		font-weight: 700;
		letter-spacing: 0.02em;
	}

	.rate-hint {
		font-size: 0.8125rem;
		color: rgba(255, 255, 255, 0.85);
	}
</style>
