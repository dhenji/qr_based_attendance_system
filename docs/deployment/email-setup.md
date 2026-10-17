# Email / OTP Delivery — Production Setup & Runbook

> Enable, verify, and operate outbound email for the production deployment:
> login OTP codes, claim-registration and forgot-password codes, and excuse
> notifications. Related: [Production Checklist](production-checklist.md) §7,
> [Deployment Workflow](deployment-workflow.md) §3,
> [Operations Runbooks](../operations/runbooks.md) (Runbook 7), and the code's
> single delivery path `backend/src/shared/email.py`.

---

## Table of Contents

1. [What sends email](#1-what-sends-email)
2. [Why this is production-critical](#2-why-this-is-production-critical)
3. [How delivery behaves](#3-how-delivery-behaves)
4. [Choosing a relay](#4-choosing-a-relay)
5. [Configure on Fly.io](#5-configure-on-flyio)
6. [Verify end-to-end](#6-verify-end-to-end)
7. [Troubleshooting](#7-troubleshooting)
8. [Runbook: rotate relay credentials](#8-runbook-rotate-relay-credentials)
9. [Runbook: email delivery is down](#9-runbook-email-delivery-is-down)
10. [Deliverability & security notes](#10-deliverability--security-notes)
11. [Monitoring](#11-monitoring)
12. [Appendix: local development](#appendix-local-development)

---

## 1. What sends email

Everything below goes through one path (`shared/email.py`); nothing else in
the system sends mail.

| Flow | Trigger | Notes |
| --- | --- | --- |
| Claim-registration OTP | `POST /auth/otp/request` (purpose `claim`), then `POST /auth/register` | 6-digit code, `OTP_EXPIRES_MINUTES` (default 5). Stored Argon2id-hashed in `otp_codes` — never readable back. Resending burns the previous code. |
| Login OTP | `POST /auth/login`, then `POST /auth/login/verify` | Mandatory second factor for every account **except** students/professors with MFA enabled (they use TOTP only). Admins with MFA get the email OTP **then** TOTP. Resend: `POST /auth/login/resend`. |
| Forgot-password OTP | Step 3: `POST /auth/otp/request` (purpose `forget_password`, requires the step-2 recovery grant), then step 4 `POST /auth/reset-password` | The recovery grant expires in 5 minutes. |
| Excuse notifications | `features/excuse/service.py` | Four events only: request submitted (→ assigned professors), approved / rejected (→ student), bulk Excuse All (→ students). Sent off the request thread. `quick_excuse`, `excuse_with_evidence`, `edit_excuse`, `revoke_excuse` send nothing. |

Not sent: admin password resets (the admin communicates the temp password
out-of-band), and any kind of in-app notification (no table exists).

---

## 2. Why this is production-critical

- **Login depends on it.** Outside the MFA exception above, every login needs an
  emailed OTP, as do registration and password recovery. With no working relay,
  most of the user base cannot sign in.
- **Failure is silent.** `request_otp` discards the delivery result, so
  `POST /auth/otp/request` and `POST /auth/login` return success even when the
  SMTP call failed. The only signals are the log lines in §3.
- **There is no queue or retry.** A failed send is dropped; the user's only
  recovery is to resend once email works again.
- **`DEBUG=true` must never be set in production.** It logs the full message
  (including OTP codes) instead of sending it.

---

## 3. How delivery behaves

`shared/email.py::send_email` is the single delivery path. Branches, in order:

1. `DEBUG=true` → logs `DEBUG email to=…` and returns without opening a
   connection.
2. `SMTP_HOST` empty → logs `SMTP_HOST unset; not sending email to=…` and
   returns. This is how a deployment "disables" email without failing requests.
3. Otherwise: `smtplib` against the relay — implicit TLS when
   `SMTP_USE_SSL=true` (port 465), plain + STARTTLS when `SMTP_START_TLS=true`
   (port 587). STARTTLS is skipped automatically when implicit TLS is on.
   `SMTP_USER` present → AUTH login; absent → anonymous relay.

A failure is logged and never raised:

| Log line | Level | Means |
| --- | --- | --- |
| `Email sent to=<addr> subject=…` | INFO | Relay accepted the message. |
| `Email delivery failed to=<addr> subject=…: <error>` | WARNING | Connect/auth/send failed; the message is dropped. |
| `SMTP_HOST unset; not sending email to=…` | INFO | Email disabled by config. |
| `DEBUG email to=…` | INFO | `DEBUG=true`; code written to logs, nothing sent. |
| `Email dispatch failed: …` | WARNING | An executor job (notification path) raised. |

Timing: OTP emails are sent **inline**, so the request waits up to
`SMTP_TIMEOUT_SECONDS` (default 10) for the relay. Excuse notifications are
handed to an executor thread and return immediately; nothing survives a
process restart.

---

## 4. Choosing a relay

Any SMTP-capable relay works. For a deployment without a custom domain,
**Brevo** is the recommended free option; **Gmail app passwords** are a quick
alternative. Once you own a domain, a transactional provider
(Resend / SendGrid / Mailgun / Amazon SES) with SPF/DKIM/DMARC configured is
the right long-term home.

| Provider | Host:Port | Credentials | Watch out for |
| --- | --- | --- | --- |
| **Brevo** (recommended) | `smtp-relay.brevo.com:587` (STARTTLS) or `:465` (SSL) | Username = Brevo account email; password = SMTP **key** | Free plan ≈300 emails/day; the From sender must be verified first. |
| **Gmail** | `smtp.gmail.com:587` or `:465` | Full address + 16-char **app password** | Requires 2-Step Verification; free ≈500 recipients/day, Workspace ≈2,000; Google keeps tightening SMTP auth — verify it works before relying on it; From must be the account or a "Send mail as" alias. |
| Institutional relay | from campus IT | usually credentials or an IP allow-list | Often the best deliverability; ask IT for host/port and whether the Fly egress addresses must be allow-listed. |
| Resend / SendGrid / Mailgun / SES | provider-specific | API key / SMTP credentials | Require a verified **domain** for arbitrary recipients. Resend's sandbox sender (or a fresh account without a domain) only mails the account owner; the SES sandbox only mails verified recipients. |
| Mailtrap / Mailpit / smtp4dev | local | — | Sandboxes: they never deliver to a real inbox. Local development only. |

### Brevo — enable in four steps

1. Create a free account at brevo.com.
2. **Verify the sender**: *Senders, Domains & Dedicated IPs → Senders → add the
   From address* (a school address, or a mailbox you control) and click the
   verification link Brevo emails you. Unverified senders are rejected.
3. **Create an SMTP key**: *SMTP & API → SMTP → Generate a new SMTP key*. The
   key is the SMTP password; the username is your Brevo login email.
4. Configure the vars from §5 with `SMTP_HOST=smtp-relay.brevo.com`. Optional
   later: authenticate your own domain (SPF/DKIM/DMARC) for better
   deliverability.

### Gmail app password — when it works

1. Use a **dedicated** Google account for the app.
2. Enable 2-Step Verification, then create an *App password*
   (`myaccount.google.com/apppasswords`; 16 characters). With 2SV on, the
   regular account password is rejected for SMTP.
3. `SMTP_USER` = the full Gmail address; `SMTP_PASSWORD` = the app password.
4. Google Workspace admins can disable app passwords org-wide; if yours does —
   or if a valid app password still yields a 535 — switch to a transactional
   relay.

---

## 5. Configure on Fly.io

Preconditions: API deployed and reachable, `flyctl` authenticated, a relay
account ready, and a short change window — `fly secrets set` triggers a rolling
restart.

1. Confirm `DEBUG=false` is set:

   ```bash
   fly secrets list --app attendance-system-api
   ```

2. Set the vars. Port 587 (STARTTLS — the common case):

   ```bash
   fly secrets set --app attendance-system-api \
     SMTP_HOST="smtp-relay.brevo.com" \
     SMTP_PORT="587" \
     SMTP_USER="you@example.com" \
     SMTP_PASSWORD="<smtp-key>" \
     SMTP_FROM="attendance@example.com" \
     SMTP_START_TLS="true" \
     SMTP_USE_SSL="false"
   ```

   Port 465 (implicit TLS): `SMTP_PORT=465`, `SMTP_USE_SSL=true`,
   `SMTP_START_TLS=false`.

3. Check `fly secrets list` for the names (values are shown as digests only)
   and `fly logs` for the restart.

Full config reference:

| Variable | Value / behavior |
| --- | --- |
| `SMTP_HOST` | Relay hostname. **Empty disables email** (logged; requests still succeed). |
| `SMTP_PORT` | `587` (STARTTLS) or `465` (implicit TLS). |
| `SMTP_USER` | Relay username. Empty = no AUTH (anonymous relay). |
| `SMTP_PASSWORD` | Relay password / SMTP key / app password. |
| `SMTP_FROM` | From header. Falls back to `SMTP_USER`, then `noreply@localhost` (undeliverable — always set it). Must be accepted by the relay (e.g. Brevo-verified). |
| `SMTP_START_TLS` | `true` for 587. Ignored when `SMTP_USE_SSL=true` (STARTTLS is skipped by the code); set it `false` on 465 for clarity. |
| `SMTP_USE_SSL` | `true` **only** for 465. |
| `SMTP_TIMEOUT_SECONDS` | Per-send timeout (default 10). Adds directly to OTP request latency. |

On any other host: set the same variables in the process environment
(systemd `EnvironmentFile=`, Compose `env_file:`, etc.) and restart the API.

> Never put relay credentials in `fly.toml` `[env]` or committed files —
> `fly secrets` only. `backend/.env` is for local development and is
> git-ignored.

---

## 6. Verify end-to-end

Verification has three legs: the relay accepts the message, the log says so,
and the mailbox actually receives it.

### 6.1 Relay smoke test (console)

```bash
fly ssh console --app attendance-system-api
# inside the machine — the app keeps its code under /app/src:
cd /app/src
python -c "from shared.email import send_email; print('sent:', send_email('you@example.com', 'SMTP smoke test', 'hello from prod'))"
```

`sent: True` plus `INFO Email sent to=` in `fly logs` means the deployed
environment authenticated to the relay. `sent: False` means check §7 — the
warning line names the failure. (No SSH access? Skip to 6.2.)

### 6.2 Real flow (recommended)

Do it against the deployed frontend or API — this exercises the exact path a
user takes.

1. Pick a controlled account. Any non-MFA login sends an OTP; password
   recovery works for any account whose security answer you know; claim
   registration needs an unclaimed roster row.
2. Trigger a send:

   ```bash
   # Login OTP (any non-MFA account):
   curl -s -X POST https://attendance-system-api.fly.dev/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email":"test.student@example.edu","password":"..."}'
   # Expect {"otp_pending": true, "otp_token": "..."} AND an email.
   ```

   Forgot-password path: step 1 `POST /api/auth/forgot-password` `{email}` →
   step 2 `POST /api/auth/forgot-password/verify` `{email, answer}` returns a
   `recovery_token` → step 3 `POST /api/auth/otp/request` `{email,
   purpose: "forget_password", recovery_token}` sends the code.

3. Confirm the message arrived (check spam on the first send).
4. Confirm the log side:

   ```bash
   fly logs --app attendance-system-api | grep "Email sent to="
   ```

### 6.3 Database sanity check

```sql
SELECT purpose, email, created_at, expires_at, consumed_at
FROM otp_codes
WHERE email = 'test.student@example.edu'
ORDER BY id DESC
LIMIT 5;
```

A fresh row shows the code was minted (it is Argon2id-hashed — you cannot read
the code back). Code-present plus no log line means issuance worked and
delivery did not; the reverse is impossible. The system cleanup
(`POST /admin/system/cleanup`) prunes OTP rows older than 7 days.

### 6.4 Excuse notification (optional)

Submit an excuse as a student (or approve one as a professor) and grep the logs
for the notification's `Email sent to=`. Notifications are the executor path —
the API returns before the send completes, so give it a moment.

### Success checklist

- [ ] `fly ssh console` smoke test prints `sent: True`.
- [ ] A real login/recovery request produces `Email sent to=`.
- [ ] The message lands in an inbox (check spam once).
- [ ] `otp_codes` shows a fresh row for the attempt.
- [ ] No `Email delivery failed to=` lines in `fly logs` around the test.

---

## 7. Troubleshooting

| What you see | Likely cause | Fix |
| --- | --- | --- |
| `DEBUG email to=…` in logs, no delivery | `DEBUG=true` in production | `fly secrets set DEBUG=false` and restart. Revert immediately — codes are in the logs. |
| `SMTP_HOST unset; not sending…` | Secret missing, or set after the last boot | `fly secrets set` (triggers restart); confirm with `fly secrets list`. |
| API returns 200, user got nothing, logs silent | `SMTP_HOST` unset or `DEBUG=true` | Check the two markers above. The API never surfaces send failures. |
| Gmail: `535 Username and Password not accepted` | Regular account password, or 2SV/app-password not set up | Create an app password; username must be the full address. |
| Brevo: `535 authentication failed` | Using the account password instead of an SMTP key, or wrong username | Regenerate the SMTP key; username is the Brevo login email. |
| `OSError` / connection timeout | Wrong host or port, or network egress blocked | Use 587/465 only — never port 25 (blocked or unreliable on cloud hosts). |
| `ssl.SSLError` / "wrong version number" | TLS mode does not match the port | 587 → `SMTP_START_TLS=true, SMTP_USE_SSL=false`; 465 → `SMTP_USE_SSL=true, SMTP_START_TLS=false`. |
| Sent OK but not received anywhere | Spam filtering, unverified sender, or From ≠ authenticated sender | Check spam; verify the sender at the relay (Brevo); align `SMTP_FROM` with the account/alias (Gmail). |
| Some recipients receive, others never | Provider sandbox | Resend without a domain mails only the account owner; SES sandbox only verified recipients; Mailtrap/Mailpit deliver nowhere. |
| `429 rate_limited` while testing | OTP-request limiter (5/60s per email) | Wait 60 seconds. |
| `423 login_otp_locked` | 3 wrong login-OTP codes inside the 5-minute window | Use "resend" — it mints a fresh code and resets the per-email budget (a separate per-IP failure cap of 15 lasts 5 minutes). |
| A student/professor with MFA gets no OTP email | By design: TOTP is stronger than an emailed code | Expected; admins with MFA still receive the OTP before TOTP. |
| Emails arrive ~10 s late | Inline send against a slow relay | Check `SMTP_TIMEOUT_SECONDS` and the relay's latency. |

---

## 8. Runbook: rotate relay credentials

**Preconditions:** provider access, `flyctl` authenticated, a change window
(rolling restart), and the current variable names from `fly secrets list`.

### Steps

1. Create the new credential at the provider (Brevo: *SMTP & API → SMTP →
   generate key*; Gmail: create a new app password).
2. Update the secret:

   ```bash
   fly secrets set --app attendance-system-api SMTP_PASSWORD="<new-secret>"
   ```

3. Verify with §6.1 (console smoke test) or §6.2 (real flow).
4. Revoke the old credential at the provider only after the new one works.
5. If the host or port changed, update `SMTP_HOST`/`SMTP_PORT` (and the TLS
   flags) the same way; the rolling restart picks them up.

### Verification

- [ ] Smoke test prints `sent: True`; a real request shows `Email sent to=`.
- [ ] The old credential is revoked at the provider.
- [ ] No `Email delivery failed` lines after the rotation.

---

## 9. Runbook: email delivery is down

**Preconditions:** reports of missing OTP codes, or `Email delivery failed`
lines in the logs.

### Impact, before touching anything

- Non-MFA users cannot log in, register, or recover passwords.
- MFA-enabled students/professors can still sign in with TOTP; admins with MFA
  still need an emailed OTP first, so they are blocked too.
- Excuse notifications during the outage are dropped silently — nothing is
  queued and there is nothing to replay.

There is no admin bypass for OTP and codes are hashed, so they cannot be read
from the database. **Do not "fix" this by enabling `DEBUG=true`**: it writes
codes to the application log. If it is ever used as a declared emergency
measure, revert it the moment the relay works again (§10).

### Steps

1. Confirm where it broke:

   ```bash
   fly logs --app attendance-system-api | grep -E "Email (sent to|delivery failed|dispatch failed)|SMTP_HOST unset|DEBUG email"
   ```

   - `SMTP_HOST unset` → configuration disabled the mailer; set the secrets
     (§5) and retest.
   - `DEBUG email` → `DEBUG=true`; fix the config.
   - `Email delivery failed … 535` → credential problem; rotate (§8).
   - timeouts / connection errors → relay reachability; continue below.
2. Run the console smoke test (§6.1) to separate an app problem from a relay
   problem.
3. Check the provider's status page and your account (sending suspended?
   quota exhausted? sender unverified?).
4. If the relay is down or the account is blocked, **switch relays**: create an
   account at an alternative provider (Brevo and Gmail both work without a
   domain), then `fly secrets set` the new host/credentials and verify. The
   configuration is provider-agnostic; nothing in the code changes.
5. Once sends work again, watch `Email sent to=` through the next
   class-time login spike.

### Verification

- [ ] Real login OTP arrives end-to-end; no `Email delivery failed` during
      five minutes of normal traffic.
- [ ] Users reporting the outage are told to retry (each retry re-mints a
      code; resending is safe).
- [ ] Post-incident note: what failed, how long, and which users were blocked
      during the window.

---

## 10. Deliverability & security notes

- **Own a domain soon.** SPF + DKIM + DMARC on the sending domain (or the
  relay's default domain) is what keeps codes out of spam. Brevo and friends
  provide the DNS records; align `SMTP_FROM` with the authenticated domain.
- **Sender identity:** relays reject a From they haven't authorized. Brevo
  requires a verified sender; Gmail requires the account or a verified "Send
  mail as" alias. Keep `SMTP_FROM` aligned with `SMTP_USER`.
- **Secrets:** `SMTP_PASSWORD` (or SMTP key / app password) lives in
  `fly secrets` only; rotate on any suspicion, and remember an app password is
  a full account credential for that mailbox.
- **Never enable `DEBUG=true` in production.** It logs full OTP codes and
  changes boot validation (a missing `JWT_SECRET` no longer fails the boot).
  As an emergency lever it sacrifices the second factor for whoever can read
  the logs; revert the moment the relay is healthy and treat any code exposed
  in the window as compromised.
- **PII:** recipient addresses come from `users.email` (falling back to the
  roster `students.email` / `professors.email`) and are visible to the relay
  provider.
- **Rate limits do double duty:** they protect accounts and keep relay quotas
  from being burned by retry storms.

---

## 11. Monitoring

The only signal for a broken relay is the log. Add an alert on it (see
[Monitoring](../operations/monitoring.md) §7):

```bash
# Failure lines:
fly logs --app attendance-system-api | grep "Email delivery failed"

# Successes — should be continuous around class start times:
fly logs --app attendance-system-api | grep "Email sent to=" | tail -20
```

Any sustained `Email delivery failed` rate is an authentication incident:
treat it like an outage (§9).

---

## Appendix: local development

- Default local behavior is **log, don't send**: `backend/.env.example` ships
  `DEBUG=true` and an empty `SMTP_HOST`, so codes appear in the API log via the
  `shared.email` logger:

  ```bash
  docker compose -f docker-compose.dev.yml logs -f api | grep "DEBUG email"
  ```

- To send for real from dev, set `SMTP_*` in `backend/.env` (git-ignored) and
  restart the API — the same variables as production.
- Sandboxes (Mailtrap/Mailpit/smtp4dev) are great for local UI testing but
  never deliver to real inboxes; do not use them for the production acceptance
  test.
- `backend/src/tests/shared/test_email.py` covers the transport with fake SMTP
  clients — no network required.

---

## See also

- [Production Checklist](production-checklist.md) §7 — pre-launch checklist
  for this pipeline.
- [Deployment Workflow](deployment-workflow.md) — Fly.io / Vercel / Supabase
  deploy steps.
- [Operations Runbooks](../operations/runbooks.md) — all runbooks, including
  Runbook 7 (email delivery down).
- [Excuse Workflow](../architecture/excuse-workflow.md) §8 — the notification
  events and their copy.
- [Monitoring](../operations/monitoring.md) — log-based metrics and alerts.
