# Exposing the local dev environment through a secure tunnel

For controlled live demonstrations only. This is **not** a production deployment.

## Prerequisites

Core tooling (from README):

- Python 3.12+
- Node.js 22+ (`.npmrc` sets `engine-strict=true`)
- Docker & Docker Compose (required for this workflow)
- Git

Tunnel/demo tooling:

- Demo data seeded (`python demo/seed_demo.py` + roster CSV imports)
- Demo student accounts with face enrollment (otherwise scans fail with `face_not_enrolled`)
- A separate device/network (e.g. phone on mobile data) for external testing

Note: `cloudflared` runs as a container via the Compose `tunnel` profile, so no host installation is required.

Runtime configuration (demo env, gitignored):

- Backend uses `backend/.env.demo` (gitignored; copy from `backend/.env.demo.example`);
  set a strong `JWT_SECRET` and SMTP values there for real OTP emails.
- `CORS_ORIGINS` can stay `http://localhost:5173` because the Vite proxy rewrites the
  Origin header; `TRUSTED_PROXY_CIDRS=127.0.0.1/32,::1/128`.
- Frontend: leave `PUBLIC_API_URL` unset/empty so it falls back to the current origin.
  For manual dev, run `npm run dev -- --mode demo` (uses `frontend/.env.demo`).

## 1. Start the stack with the tunnel

```bash
docker compose -f docker-compose.demo.yml --profile tunnel up --build
```

This starts Postgres, migrations, the API, the frontend, and the Cloudflare
tunnel container. The backend (`:8000`) and Postgres (`:5432`) are **not**
exposed publicly; the Vite dev server proxies `/api` to the backend (see
`frontend/vite.config.ts`).

Verify:

```bash
curl -s http://localhost:8000/health   # {"status":"ok"}
```

Get the public URL from the tunnel container logs:

```bash
docker compose -f docker-compose.demo.yml logs -f tunnel
```

Copy the `https://<random>.trycloudflare.com` URL.

## 2. How demo users access the app

1. Share the `https://<random>.trycloudflare.com` URL with the demo user.
2. The demo user opens that URL in their browser (phone or laptop; a different
   network than the demo machine is best for a real external-access test).
3. The URL must be **HTTPS** — otherwise the camera (`getUserMedia`) and GPS
   (`navigator.geolocation`) used by the scan flow will not work.
4. They log in with a demo account and use the application normally.
5. The tunnel exposes only the frontend; `/api` requests are proxied by Vite to
   the local backend, and Postgres stays private.

## 3. Configure the backend for the demo

Secrets live in `backend/.env.demo` (gitignored) — the demo compose `api` and
`migrate` services load it via `env_file`:

```env
JWT_SECRET=<strong-random>
```

The compose pins the demo-safe runtime values in its `environment:` blocks
(those override the file): `DEBUG=false`, `SCHEDULER_ENABLED=false`,
`BENCHMARK_MODE=false`, `CORS_ORIGINS=http://localhost:5173`,
`TRUSTED_PROXY_CIDRS=127.0.0.1/32,::1/128`. The Vite proxy rewrites the Origin
header, so the tunnel hostname needs no CORS entry (see Runtime configuration
above). Restart the `api` service after editing the file:
`docker compose -f docker-compose.demo.yml up -d api`. `DEBUG=false` requires a
real `JWT_SECRET`.

## 4. Seed demo data and rosters (aligns with demo/README.md)

1. Migrate the database (automatic via the `migrate` service when using
   `docker-compose.demo.yml`).
2. Seed the super_admin + demo structure:
   ```bash
   python demo/seed_demo.py
   ```
   Default login: `super@attendly.demo` / `Demo!1234`.
3. Import rosters as super_admin/admin:
   ```bash
   TOKEN=<login token for superadmin>
   curl -X POST http://localhost:8000/api/admin/students/import   -H "Authorization: Bearer $TOKEN" -F "file=@demo/rosters/students.csv"
   curl -X POST http://localhost:8000/api/admin/professors/import -H "Authorization: Bearer $TOKEN" -F "file=@demo/rosters/professors.csv"
   curl -X POST http://localhost:8000/api/admin/programs/import   -H "Authorization: Bearer $TOKEN" -F "file=@demo/rosters/programs.csv"
   curl -X POST http://localhost:8000/api/admin/courses/import    -H "Authorization: Bearer $TOKEN" -F "file=@demo/rosters/courses.csv"
   ```
4. Claim student/professor accounts: register with the roster email; the OTP is
   delivered by SMTP (because `DEBUG=false` in the demo compose). With no SMTP
   configured, codes are not logged and cannot be delivered.

## 5. Prepare demo content

- Enroll faces for any student who will scan.
- Open sessions with `geofence_enabled=false` when participants are remote.
- Use seeded demo accounts only; never real student data.

## 6. Test from an external device

Use a phone on mobile data (not the demo machine's Wi-Fi):

1. Open the tunnel URL.
2. Log in with a demo account.
3. Open a session and scan (GPS + face).
4. Confirm the attendance record appears on the professor view.

## 7. Teardown

1. Stop the compose stack (this also stops the tunnel container).
2. Disable/rotate demo credentials; clear demo data if required.
3. Confirm the tunnel URL no longer resolves.

## Troubleshooting

- **Camera/GPS blocked:** the tunnel must be HTTPS; verify the URL starts with `https://`.
- **`outside_geofence`:** set `geofence_enabled=false` on the session or adjust classroom coordinates.
- **`face_not_enrolled`:** enroll the demo student's face first.
- **Scan throttled:** participants may share a NAT IP; raise `SCAN_RATE_LIMIT_MAX_CALLS` temporarily.
- **Backend won't boot:** Postgres must be healthy first (`SELECT 1` lifespan check).
