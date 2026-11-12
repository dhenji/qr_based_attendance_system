# Demo Setup

Quick setup for the live demo: super_admin account, demo academic structure,
and roster CSVs.

## 1. Migrate the database

With `docker compose -f docker-compose.dev.yml up`, migrations run
automatically via the `migrate` service. Otherwise:

```bash
cd backend && .venv/bin/alembic upgrade head
```

## 2. Seed the super_admin + demo structure

```bash
python demo/seed_demo.py
```

The script bootstraps itself into the backend venv (`backend/.venv`) and
defaults `DATABASE_URL` to the compose Postgres on `localhost:5432`, so no
venv activation or `PYTHONPATH` is needed. It also defaults `DEBUG=true` and a dev
`JWT_SECRET` for app settings.

Default login: `super@attendly.demo` / `Demo!1234` (override with
`--email`, `--password`, or `DEMO_SUPER_ADMIN_PASSWORD`; `--update-password`
resets the password on an existing account). Safe to re-run — it reuses
existing rows.

The seed also sets a break-glass recovery code (`DemoRec1!234` by
default; override with `--recovery-code` or `DEMO_SUPER_ADMIN_RECOVERY_CODE`)
so the Super Admin forgot-password flow can be exercised without setting one
manually. After a recovery code is consumed it is cleared; set a new one via
`POST /api/auth/recovery-code` while logged in. For a guaranteed-clean slate instead, reset the database
first (`docker compose -f docker-compose.dev.yml down -v`, then `up` to
recreate and re-migrate before seeding).

This creates programs (BSCS/BSIT/BSECE) with year levels, demo courses, and
course offerings for `1st_sem`, `2026-2027`. Meeting schedules match their
course units exactly and session counts follow the meeting days, so the demo
opens with clean weekly-requirement panels. Re-running repairs previously
seeded offerings to match (skipped for offerings with opened sessions).

## 3. Import the rosters (as super_admin or admin)

```bash
TOKEN=<login token for superadmin>
curl -X POST http://localhost:8000/api/admin/students/import   -H "Authorization: Bearer $TOKEN" -F "file=@demo/rosters/students.csv"
curl -X POST http://localhost:8000/api/admin/professors/import -H "Authorization: Bearer $TOKEN" -F "file=@demo/rosters/professors.csv"
curl -X POST http://localhost:8000/api/admin/programs/import   -H "Authorization: Bearer $TOKEN" -F "file=@demo/rosters/programs.csv"
curl -X POST http://localhost:8000/api/admin/courses/import    -H "Authorization: Bearer $TOKEN" -F "file=@demo/rosters/courses.csv"
curl -X POST http://localhost:8000/api/admin/offerings/{id}/enrollments/bulk -H "Authorization: Bearer $TOKEN" -F "file=@demo/rosters/enrollments.csv"
```

The programs/courses CSVs use fresh codes on purpose: the seed already owns
`BSCS/BSIT/BSECE` and the `GE101/CS101/…` courses, and the import counts
existing codes as duplicates (skipped, 0 imported). Year levels for the new
programs and offerings for the new courses attach later via the detail pages
— the import creates the records only.

Find an offering id via `GET /api/admin/offerings`. The enrollments CSV column
order follows `docs/architecture/api-contracts.md` (bulk-enroll contract).

## 4. Claim student/professor accounts

Roster rows (from the CSVs) have no login until claimed:

1. Register with the same email as the roster row (frontend sign-up, or the
   `/api/auth` claim flow). Choose your own password.
2. Grab the OTP from the api logs — the compose stack runs the api with
   `DEBUG=true`, so full emails (including the code) are logged instead of
   sent:

   ```bash
   docker compose -f docker-compose.dev.yml logs api | grep -A 5 "DEBUG email"
   ```

3. Submit the code to finish the claim; that account then passes the
   student/professor login.

For a real deployment, configure `SMTP_*` in `backend/.env` so codes are
delivered by email instead of logged.

## 5. Open a session (as the professor)

Most demo offerings meet **lectures only**, so the professor's session form
offers "Lecture" and nothing else. **CS201** is the mixed one: it meets a
lecture (Monday & Wednesday, 10:30–12:00, Room 301) *and* a laboratory
(Wednesday, 13:00–14:00, Lab 201), so its form offers both types and its
admin badge reads "Mixed" (D95: an offering declares what it meets through
its active meetings, and a session of a type it does not meet is refused).

A session may also only be opened **while its class is running** (D94). When
the demo is presented outside the offering's scheduled hours, the form says so
and offers two ways forward:

- **Wait for Scheduled Time** — returns to My Courses; the session opens
  during the class.
- **Select Different Start Time** — opens the date/time picker, prefilled
  with the current time. Confirm it and the session opens with that start,
  recorded on the session as an override with the reason you gave.

## Demo with a public tunnel

For external access during the demo, use `docker-compose.demo.yml` instead of
the dev compose file:

```bash
docker compose -f docker-compose.demo.yml --profile tunnel up --build
docker compose -f docker-compose.demo.yml logs -f tunnel   # https://*.trycloudflare.com
```

This uses `backend/.env.demo` (gitignored). Set a strong `JWT_SECRET` and SMTP
values there if you want OTP codes delivered by email; otherwise the claim flow
cannot complete with `DEBUG=false`. See `docs/developer/demo-tunnel.md`.
