<script lang="ts">
	// DashboardStats
	// Attendance-rate summary card. Currently shows an empty-state placeholder
	// ("No data") because there are no real scans yet; once history exists this
	// will render the computed compliance rate from the student store.
	const hasData = $derived(false);
</script>

<div class="attendance-rate">
	<span class="rate-value" class:placeholder={!hasData}>{hasData ? '0%' : 'No data'}</span>
	<span class="rate-label">Attendance Rate</span>
	<span class="rate-hint">Your rate will appear after your first scans.</span>
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