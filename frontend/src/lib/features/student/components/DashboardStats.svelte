<script lang="ts">
	import { studentState, complianceRate, participationRate } from '$lib/features/student/store.svelte';
	import { formatPercentage } from '$lib/shared/utils/format';

	const todayPresent = $derived(0);
</script>

<div class="dashboard-stats">
	<div class="stat-card">
		<h3>Today</h3>
		<p>Present: {todayPresent}</p>
	</div>
	<div class="stat-card">
		<h3>This Week</h3>
		<p>Attendance Rate: {formatPercentage(complianceRate())}</p>
	</div>
	<div class="stat-card">
		<h3>This Month</h3>
		<p>Participation: {formatPercentage(participationRate())}</p>
	</div>
</div>
