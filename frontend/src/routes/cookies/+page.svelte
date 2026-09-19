<script lang="ts">
</script>

<svelte:head>
	<title>Cookies · Attendly</title>
</svelte:head>

<main class="page">
	<header class="nav">
		<a class="nav-brand" href="/">
			<img src="/qr-attend-logo.svg" alt="Attendly logo" class="nav-logo" />
			<span class="nav-name">Attendly</span>
		</a>
		<a class="back-link" href="/">Back to home</a>
	</header>

	<section class="content">
		<h1>Cookies</h1>
		<p class="lead">Attendly uses a small number of browser storage tools so you can stay signed in and keep working without a connection. It does not use third-party tracking cookies.</p>

		<h2>What we use</h2>
		<ul class="list">
			<li>Session tokens: short-lived access token (15 minutes) and a refresh token (7 days). These keep you signed in while the app is in use.</li>
			<li>Local storage: remembers the last signed-in account and general app preferences on this device.</li>
			<li>IndexedDB: the offline scan queue, the cached session list, and the encrypted face data used for scans without a signal.</li>
		</ul>

		<h2>What each one is for</h2>
		<p class="body">
			Session tokens expire quickly so a stolen token cannot be used for long. The offline queue lets scans made without a connection submit themselves automatically once you are back online. The encrypted face data lets the app verify your identity during a scan even when the server is unreachable.
		</p>

		<h2>What we do not use</h2>
		<p class="body">
			There are no advertising cookies, no cross-site tracking, and no analytics beacons. Attendly does not follow you across other websites.
		</p>

		<h2>Managing these</h2>
		<p class="body">
			Clearing your browser's site data removes your tokens and local scans, and signs you out on this device. Offline scans that have not synced yet would be lost. Your attendance records on the server are not affected.
		</p>
	</section>
</main>

<style>
	.page {
		min-height: 100vh;
		font-family: 'DM Sans', system-ui, sans-serif;
		background: #f8fafc;
	}

	.nav {
		position: sticky;
		top: 0;
		z-index: 20;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		padding: 0.75rem 1.5rem;
		background: #1e3a5f;
		box-shadow: 0 2px 12px rgba(15, 23, 42, 0.25);
	}

	.nav-brand {
		display: flex;
		align-items: center;
		gap: 0.625rem;
		text-decoration: none;
	}

	.nav-logo {
		width: 34px;
		height: 34px;
		display: block;
	}

	.nav-name {
		color: white;
		font-weight: 700;
		font-size: 1.125rem;
	}

	.back-link {
		padding: 0.5rem 0.875rem;
		border-radius: 8px;
		color: #e2e8f0;
		font-size: 0.9375rem;
		font-weight: 500;
		text-decoration: none;
		transition: background 0.15s ease, color 0.15s ease;
	}

	.back-link:hover {
		background: rgba(255, 255, 255, 0.1);
		color: white;
	}

	.content {
		max-width: 720px;
		margin: 0 auto;
		padding: 3rem 1.5rem 4rem;
	}

	h1 {
		color: #1e293b;
		font-size: 2rem;
		font-weight: 700;
		margin: 0 0 0.75rem;
	}

	.lead {
		color: #475569;
		font-size: 1.125rem;
		line-height: 1.6;
		margin: 0 0 2rem;
	}

	h2 {
		color: #1e293b;
		font-size: 1.375rem;
		font-weight: 700;
		margin: 2rem 0 0.75rem;
	}

	.body {
		color: #64748b;
		font-size: 1rem;
		line-height: 1.7;
		margin: 0 0 1rem;
	}

	.list {
		color: #64748b;
		font-size: 1rem;
		line-height: 1.7;
		margin: 0 0 1rem;
		padding-left: 1.25rem;
	}

	.list li {
		margin-bottom: 0.375rem;
	}
</style>