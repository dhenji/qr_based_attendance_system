<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { Routes } from '$lib/shared/constants/routes';

	// /admin lands on the dashboard; the layout owns the nav shell.
	onMount(() => {
		goto(Routes.ADMIN_DASHBOARD, { replaceState: true });
	});
</script>

<p>Redirecting to the admin dashboard…</p>
