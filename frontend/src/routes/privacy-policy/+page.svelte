<script lang="ts">
</script>

<svelte:head>
	<title>Privacy Policy · Attendly</title>
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
		<h1>Privacy Policy</h1>
		<p class="lead">This policy explains what Attendly collects, why it collects it, and how the data is protected.</p>

		<h2>What we collect</h2>
		<ul class="list">
			<li>Account details: name, email, student or employee number, and role.</li>
			<li>Attendance records: session, course, time of scan, and result (present, late, excused, absent).</li>
			<li>Location: GPS coordinates captured at the moment of a scan, used to verify the student is inside the classroom geofence.</li>
			<li>Liveness evidence: short face-coordinate samples from the blink and head-turn checks. These are used to confirm a real person made the scan.</li>
			<li>Face embeddings: a mathematical representation of the enrolled face used to match the student at scan time.</li>
			<li>Excuse evidence: any documents or photos you attach to an excuse request.</li>
		</ul>

		<h2>Why we collect it</h2>
		<p class="body">
			Attendance data is collected so the school can track class participation accurately. Identity checks (face match and liveness) exist to make sure students cannot scan for each other. Location is collected only to confirm the scan happened inside the classroom.
		</p>

		<h2>How it is stored</h2>
		<ul class="list">
			<li>Passwords are hashed with Argon2id, never stored in plaintext.</li>
			<li>Face embeddings are encrypted at rest. The server stores them in encrypted form, and the device key needed to use them never leaves the student's phone.</li>
			<li>Backups are encrypted with AES-256-GCM before they leave the server.</li>
			<li>Session codes are generated from a server secret and cannot be reused after a session ends.</li>
		</ul>

		<h2>Who can see what</h2>
		<p class="body">
			Students see their own schedule, history, and attendance rate. Professors see attendance for the courses they teach. Administrators manage rosters and can view records as part of their duties. Attendance is not shared with other students.
		</p>

		<h2>Data security</h2>
		<p class="body">
			Every sensitive action is audit-logged, including logins, failed login attempts, roster changes, and excuse decisions. Authentication uses short-lived access tokens (15 minutes) with a longer refresh token, and optional MFA. Five failed login attempts lock the account for 15 minutes.
		</p>

		<h2>Data retention</h2>
		<p class="body">
			Attendance records are kept for the school's official retention period. When an account is archived, its face data is cleared from active use. Re-enrolling a student replaces the previous face embedding.
		</p>

		<h2>Not sold, not shared</h2>
		<p class="body">
			Attendly does not sell personal data and does not share attendance records with advertisers or other third parties. Data is only used to operate the system and to comply with school regulations.
		</p>

		<h2>Contact</h2>
		<p class="body">
			For questions about this policy or to request access to your records, contact your school's administrator.
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