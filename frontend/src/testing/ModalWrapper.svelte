<script lang="ts">
	import Modal from '../lib/components/Modal.svelte';
	let { onclose, closeOnBackdrop = false, showFooter = false }: { onclose?: () => void; closeOnBackdrop?: boolean; showFooter?: boolean } = $props();
</script>

<Modal title="Test dialog" {onclose} {closeOnBackdrop}>
	<p>Modal body content</p>
	{#snippet footer()}
		{#if showFooter}<button type="button">OK</button>{/if}
	{/snippet}
</Modal>