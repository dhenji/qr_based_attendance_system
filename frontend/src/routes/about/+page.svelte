<script lang="ts">
</script>

<svelte:head>
	<title>About · Attendly</title>
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
		<h1>About Attendly</h1>
		<p class="lead">Attendly is a QR-based attendance system built for ISU classrooms. It replaces paper sign-in sheets with a five-step scan flow that runs on the student's phone.</p>

		<h2>How a check-in works</h2>
		<p class="body">
			When a professor opens a session, the class gets a unique QR code. A student records attendance in five steps:
		</p>
		<ol class="list">
			<li>The student scans the session QR code on the board.</li>
			<li>The student scans the QR code on their own student ID.</li>
			<li>The app checks the student's location against the classroom geofence.</li>
			<li>The app runs a live face check (blink, then turn left, then turn right).</li>
			<li>The app compares the live face against the student's enrolled face and records the check-in.</li>
		</ol>
		<p class="body">
			Every step must pass before the check-in is recorded. None of the steps can be skipped.
		</p>

		<h2>Works offline</h2>
		<p class="body">
			Lecture halls often have weak signals. When a student scans without a connection, the evidence is saved on the device and submitted automatically once the signal returns. The server re-validates the scan before it counts.
		</p>

		<h2>Built for three roles</h2>
		<p class="body">
			Students scan, view their schedule, and track their attendance rate. Professors create sessions and review attendance for every meeting. Administrators manage rosters, courses, and attendance records.
		</p>

		<h2>Your data stays protected</h2>
		<p class="body">
			Attendance is tied to your identity with location and live-face checks, so a friend cannot scan for you. Face embeddings are encrypted at rest and never stored as plaintext. Passwords are hashed with Argon2id, and repeated failed logins trigger a temporary lockout.
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