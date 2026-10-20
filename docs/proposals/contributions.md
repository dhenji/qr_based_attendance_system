# CS Contributions

This document states the project's contributions to computer science honestly. The framing is **systems and security-protocol engineering plus empirical evaluation** — not novel machine learning. The system uses zero trained models for anti-spoofing; liveness grading is built on open landmark tracking (MediaPipe Face Mesh) and geometric/statistical heuristics, chosen deliberately for offline capability, transparency, and auditability.

Every claim below is written against the code that ships. Where a mechanism is designed but not built, it is labelled **Planned** and is not a claim the project can defend today.

---

## How to read this document

| Status | Meaning |
| --- | --- |
| **Implemented** | The described mechanism ships, and it is the one the code actually runs. |
| **Partial** | The mechanism ships in a weaker form than described. The gap is stated inline, with the file that carries it. |
| **Planned** | Designed, not built. Not a claim the project can defend today. |

**Folder mapping** — each contribution maps to a specific backend feature folder and frontend directory:

| Contribution | Backend | Frontend |
| --- | --- | --- |
| C1 | `features/sync/` (model only) + `features/attendance/` | `lib/features/liveness/`, `lib/features/sync/`, `src/service-worker.ts` |
| C2 | `features/attendance/` | `lib/features/liveness/components/FaceScanner.svelte` |
| C3 | — | — (would live in `backend/src/tests/`) |
| C4 | `features/analytics/` | `lib/features/admin/analytics/`, `lib/features/report/` |
| C5 | `features/session/`, `features/attendance/service.py` | `lib/features/session/` |
| C6 | `features/excuse/` | `routes/professor/excuse-requests/`, `routes/admin/excuses/`, `routes/student/history/` |
| C7 | `features/face_enrollment/`, `features/student/` | `lib/features/student/face.svelte.ts`, `lib/features/sync/service.ts` |
| C8 | `features/program/`, `features/course/`, `features/enrollment/` | `routes/admin/programs/`, `routes/admin/offerings/` |

---

## C1 — Offline-First Liveness Protocol (flagship) — **Partial**

Standard liveness detection assumes an always-reachable server. Our defining constraint is offline-first: students' scans must be captured and trusted even when no server responds.

### What ships

- **The client captures the complete scan** — GPS, the liveness transcript, and the device clock — and, when the submission cannot reach the server, writes it to an IndexedDB outbox (`frontend/src/lib/features/sync/service.ts`). A verified session's configuration is cached alongside it, so a student who loses signal after verifying the code can still complete the scan.
- **The outbox is a real queue, not a buffer.** Rows move `pending → syncing → synced/rejected`; transient failures (offline, 429, timeout, 5xx) go back to `pending` with exponential backoff (30 s × 2^attempts, capped at 30 minutes) and a 25-attempt ceiling, while a server *decision* (duplicate, mismatch, validation) is terminal and keeps its reason code. The drain is oldest-first, single-flight, and recovers rows stranded in `syncing` by a tab that died mid-drain.
- **A service worker precaches the app shell** and relays Background Sync `attendly-outbox` wake-ups to open pages (`frontend/src/service-worker.ts`). The worker never replays scans itself — the auth token lives in `localStorage`, which a worker cannot read, so a closed app cannot authenticate.
- **The server re-validates every replayed scan against the device timestamp** (D16). `AttendanceService._get_active_session` raises `session_expired` (410) when `scanned_at` is past the session's `expires_at`; `AttendanceService._compute_status` then grades the timestamp against the present/late windows, so an in-window replay is recorded as `present`/`late` and an out-of-window one as `rejected`. The device clock is the one under the student's control, which is exactly why the window check runs on it and not on arrival time.
- **Anti-replay is an idempotency registry** keyed `user_id:session_id:X-Idempotency-Key` with a 15-minute TTL, backed by the one-scan-per-session constraint (409 `duplicate_scan`).
- **Online and offline are graded the same way.** The same payload meets the same server-side rules on both paths, so a queued scan is never judged by a different standard than a live one. The only thing the offline path skips is the read-only pre-check gate, which needs the server.

### What is not built yet

- **There is no signed bundle and no nonce registry.** The evidence on the wire is `{blink_detected, head_turn_left, head_turn_right, ear_samples, pnp_evidence}` plus the GPS accuracy the server adds — no `scan_id`, no `nonce`, no `session_ref`, no HMAC over the transcript, and no server-side nonce registry to reject a re-submitted bundle. The anti-replay guarantee comes from the idempotency registry above, not from a signed evidence trail.
- **The idempotency registry is process-local.** A multi-instance deployment needs a shared store, or two instances can both accept the same key.
- **`backend/src/features/sync/` is `model.py` only.** The `sync_queue` table records replays for audit and reconciliation; it is drained by `POST /admin/system/sync/flush` (`features/system/service.py::flush_sync_queue`), not by a per-student sync endpoint.

### What this buys

The liveness gate no longer requires connectivity at capture time — the evidence is captured, queued and re-graded on arrival by the same server-side rules, and the replay path is idempotent, so a queued scan can never double-record. It does not yet make the evidence *provable* in the strong sense the design intended: without a nonce and a signature, the trail is auditable but not self-authenticating.

---

## C2 — Challenge-Response Liveness Grading (flagship) — **Partial**

### What ships

- **A fixed challenge sequence** — blink → head left → head right — chosen for offline operability: no server round-trip is needed to know what to ask (D31).
- **The client tracks MediaPipe Face Mesh landmarks** (478 points) and produces an evidence transcript: an Eye Aspect Ratio time series, head-pose yaw from the facial transformation matrix with a landmark-geometry fallback, and the derived per-stage evidence (`source`, `baseline_yaw`, `yaw`, `peak_left_yaw`, `peak_right_yaw`, `yaw_samples`).
- **The server grades the transcript** in `AttendanceService._validate_liveness_evidence`, in four checks:
  1. all three challenge stages completed,
  2. an EAR series is present,
  3. the **mean** EAR falls inside `[0.05, 0.50]`,
  4. the PnP evidence is non-empty.
- **The grade is deterministic, explainable and reproducible.** Every rejected scan keeps the evidence that produced the decision, and the liveness-review queue (`/admin/attendance`) shows that evidence to the reviewer who has to act on it.

### What is not built yet

- **The server does not do challenge-response correlation, EAR-dropout analysis, temporal plausibility or pose-dynamics checking.** It reads the *mean* EAR and the presence of a PnP blob; the yaw values inside that blob are never inspected, and the blob is a free-form dict, so `{"x": 1}` satisfies check 4.
- **The claim that this defeats printed photos, screen/video replay and distorted prints is therefore not supported by the implemented grade.** A client that asserts `blink_detected=true, head_turn_left=true, head_turn_right=true, ear_samples=[0.2], pnp_evidence={"x": 1}` passes every check. The client-side challenge is real work; the server-side verification of it is the shallow half.
- **The inter-event timing the transcript could carry is not recorded** — the client sends the flags, the EAR series and the pose samples, but no per-stage timestamps.

The contribution is the _grading protocol_ — deterministic, explainable and offline-verifiable — versus black-box classifier approaches that cannot produce auditable evidence. That property holds today; the depth of the grading is the part still to build.

---

## C3 — Evaluation Methodology: Attack Corpus + APCER/BPCER — **Planned**

**Contribution (design)**: a reproducible evaluation protocol for the liveness layers, following ISO/IEC 30107-3 presentation-attack metrics — rare in comparable student-built systems.

- A constructed attack corpus: printed photos, device-screen replays, recorded video, distorted prints, and replay of captured evidence bundles.
- Metrics: Attack Presentation Classification Error Rate (APCER) and Bona Fide Presentation Classification Error Rate (BPCER) per attack type.
- Evaluation of the protocol layer too: replay-rejection rate and challenge-guessing resistance.

This separates _what the protocol guarantees_ (replay, photo, distortion) from _what it cannot claim_ (biometric identity, twin separation) — a defensible, quantitative boundary.

**Status: none of this exists yet.** There is no corpus, no APCER/BPCER computation, and no replay-rejection metric. The harness it would run on does exist — `backend/src/tests/` is 75 test files and 968 collected cases, pytest is configured, and CI runs it — so the gap is the corpus and the metric, not the infrastructure.

Until it lands, the honest statement is that the liveness layers are **unmeasured**: this project cannot yet say what fraction of printed photos or screen replays it rejects, because it has never tried any.

---

## C4 — Heuristic At-Risk Analytics over Sync-Corrupted Attendance Data — **Implemented** (and it exceeds the original description)

### What ships

- **The feature engineering is built for this data regime, not for a clean table.** Standard forecasting assumes complete, timely, trusted data; this source is delayed, batched and partially pending (D16).
- **Heuristic thresholds, env-configurable** (D35) — `core/config.py`: `risk_absence_rate_high=0.30` → high, `risk_streak_gaps_high=3` → high, `risk_sync_lag_high=5` → medium, `risk_trend_negative=-0.05` → medium, plus an added `risk_absence_rate_medium=0.15`. First matching rule wins, higher severity first.
- **A daily batch job** (`features/analytics/batch.py`, APScheduler cron `RISK_BATCH_CRON`, default `0 2 * * *`) scores every active enrollment and writes `student_risk_scores`. It commits its own transaction — the services only `flush()`, and a cron run has no request to commit for it. `RISK_BATCH_WORKERS` shards the scoring across threads, order-preservingly.
- **The implementation goes beyond the original description**: a weighted `risk_probability` blend (weights summing to 1.0) alongside the categorical level, a `student_risk_scores_staging` table with a scoped `promote` action, a `refresh_risk` recompute, an at-risk list, and a CSV export.
- **Two rate metrics everywhere** (D36), from a single definition (`shared/rates.py::attendance_rates`): **Compliance Rate** = present / enrolled (the default, strict — present and nothing else) and **Participation Rate** = (present + late + excused) / enrolled.
- **Visualization is hand-rolled SVG, not Chart.js** — `frontend/src/lib/features/report/components/ReportTrendChart.svelte` and `ReportBarChart.svelte`. ADR-041 specified Chart.js; ADR-091 amends it to describe what ships, and this entry follows the code.

The dashboard layers (descriptive: what happened, diagnostic: why, predictive: what's next, prescriptive: what to do) are the product surface; the contribution is the _forecasting-under-data-quality-regime_ work underneath.

### What is not built yet

- **The prescriptive rule engine** — no professor alerts, no student reminders, no effectiveness tracking. The analytics slice sends no notifications at all, so the loop that would produce the longitudinal data is designed but not running.
- **The logistic-regression upgrade path** — there is no `scikit-learn` dependency. The feature vector is deliberately kept separate from the rule evaluation so a model can be dropped in behind the same interface, but that has not happened.

---

## C5 — Window-Based Attendance Policy Engine — **Implemented**

- **Session creation** takes `duration_minutes`, `present_window_minutes` and `late_window_minutes`; the server computes `expires_at = min(created_at + duration, scheduled_end_time)` (D12, D49). The anchor is the session's **creation** time, not the moment of the request.
- **The constraint `present_window + late_window ≤ duration` is enforced twice** — at the API layer (`SessionService._check_windows`) and by the database (`ck_session_window_sum_lte_duration`), so a write that bypasses the service still cannot violate it.
- **Offering-level defaults** (`default_present_window_minutes`, `default_late_window_minutes`) are prefilled per D14 and resolved in `SessionService._resolve_windows` with a global config fallback; a per-session override wins.
- **Status determination**: a scan inside the present window → `present`; inside the late window after that → `late`; outside both → `rejected` (`AttendanceService._compute_status`). A student who never scanned reads as `absent` in the session roster — a **derived** roster value, not a persisted attendance row (D13).
- **Both entry modes are supported**: `scanned_via` is `qr_camera` or `manual_code` (D18).

---

## C6 — Excuse State Machine with Three-Path Workflow — **Implemented**

**Folders**: `backend/src/features/excuse/` + the route pages `frontend/src/routes/professor/excuse-requests/`, `routes/admin/excuses/`, and the student-initiated submit inside `routes/student/history/`. There is no `features/excuse/components/` directory — the excuse UI is route-level.

- **State machine**: `pending` → `approved` | `rejected` (D21), with a direct-approved path for professor-initiated excuses. The slice also supports editing a decision and revoking one, and a revoke restores the previous status.
- **Three paths**: (a) professor quick-excuse (absent/late student → excused with a reason); (b) professor-initiated with evidence (holds the excuse letter → files and approves it immediately); (c) student-initiated request (submits reason + evidence → professor approves or rejects).
- **Effects**: excusing overrides the scanned status while `attendance_records.original_status` preserves what actually happened (D22). The final status is `excused`, which counts toward the participation rate but not the compliance rate (D36).
- **Bulk action**: "Excuse All Absent" for a session (typical: a cancelled class) (D23).
- **Attachments**: uploaded straight to S3-compatible storage (Supabase Storage / R2 / S3) through a presigned URL; the database stores URL references only (D24). Files never pass through the API.
- **Notifications**: four events notify — a student request was submitted, a request was approved, a request was rejected, and a bulk excuse was issued. The professor-initiated paths are deliberately silent, and so are editing and revoking a decision.

---

## C7 — Biometric Template Protection with Pull-on-Distribution — **Partial**

**Folders**: `backend/src/features/face_enrollment/` (service + router mounted at `/admin/face-enrollment`) + the face columns on `backend/src/features/student/` + `frontend/src/lib/features/student/face.svelte.ts` + `frontend/src/lib/features/sync/service.ts` (the device cache).

### What ships

- **Enrollment**: `POST /admin/face-enrollment/{student_id}` takes the three photos — front, left, right (D43) — and gates each on non-empty content, a size cap and an `image/*` content type. The enrollment is audited, the server-side cache is invalidated, and `face_embedding_version` is bumped so stale device copies cannot match.
- **Storage shape**: `students.face_embedding` (BYTEA) holds `{"mean":[128f],"angles":{"front":[128f],"left":[128f],"right":[128f]}}` (D28).
- **Distribution is pull-on-login** (D29): `GET /student/me/face-embedding?current_version=N` returns the blob when the client's copy is stale, 204 when it is current, and 404 `face_embedding_not_found` when there is no enrollment. The client caches it in IndexedDB, encrypted with an AES-GCM key generated on the device and stored as a non-extractable `CryptoKey` — the ciphertext alone is not enough to decrypt it. No push or WebSocket infrastructure.
- **Revocation**: archiving a student clears the blob and bumps the version (`StudentService.archive`), so an archived identity cannot stay matchable; re-enrollment supersedes the old vectors, and the version bump tells every device to drop its copy.

### What is not built yet

This is where the contribution is currently weakest.

- **No embedding generation.** The stored blob comes from `_stub_embedding_blob`: the documented shape, filled with zeros and tagged `"stub": true`. The pretrained face-api.js model never runs, and nothing is fine-tuned — but nothing is generated either.
- **No encryption at rest on the server.** The blob is stored as plain JSON bytes. Only the *device* copy is encrypted.
- **No similarity comparison.** `face_match_score` is a client assertion; the server band-checks the number (`≥ 0.70` pass, `0.65–0.70` review-flag into the liveness-review queue, `< 0.65` fail) but never compares it to the stored embedding, and the embedding is not read during a scan at all. The live scan path computes no score, so `submitAttendanceScan` substitutes a placeholder of `1` on every scan. Until the comparison lands, the face step is decorative and the liveness transcript is the only thing actually being checked.
- **No offline local compare** — explicitly deferred in the client, for the same reason.
- **The quality gates are transport-level, not biometric**: brightness, face-size and single-face checks are not implemented.
- **No capture UI.** The admin endpoint exists, but the frontend has no enrollment screen — the admin student page shows enrollment state as read-only text.

---

## C8 — Academic Hierarchy with Multi-Program Course Sharing — **Implemented**

- **Hierarchy**: Programs → Year Levels (own term structures as JSONB) → Courses. Strict FK constraints — `year_levels` cascades from `programs`, everything else is `RESTRICT` (D1).
- **Term structures** are per-program-per-year: e.g. BSCS Y1/Y2 = 2 semesters; BSCS Y3 = 1st, 2nd + Midyear; BSIT defines its own (D3). A term's session weeks resolve through one function (`shared/schedule.py::term_weeks`), so an orphaned semester value resolves to a default instead of raising.
- **Course sharing**: a course carries no program FK of its own — sharing happens through `course_offerings`, so one course runs in several programs and year levels (D6). Filters and analytics slice the same course by program and year throughout.
- **Enrollment validation**: `enrollments.semester` is copied from the offering, so an enrollment row can never disagree with the offering it belongs to (D5). The offering's semester is **free text at the API layer** — `OfferingCreate.semester` is length-checked, not term-checked — and the term structure's role is to supply the term's session-week count, with a shared default for an unmatched code. The one hard constraint runs the other way: renaming or removing a term that existing offerings reference is refused.
- **Admin management**: CRUD flows for programs, year levels, courses and offerings, replacing year-level promotion with intentional academic structure updates, audited through the same trail as everything else (D38).

---

## Deliberately NOT Contributions

These are standard engineering with off-the-shelf components; presenting them as research invites challenge in defense:

- QR decoding/live-detection heuristics (`html5-qrcode`)
- GPS geofencing (Haversine)
- HMAC session-code generation/verification
- Duplicate-scan (one-per-session) enforcement
- The 4-level descriptive/diagnostic/predictive/prescriptive taxonomy itself (standard BI framework)
- PWA offline storage (IndexedDB + Service Workers)
- Chart rendering (the hand-rolled SVG chart components — standard visualization work)
- Argon2id password hashing
- AES-256-GCM backup encryption (standard cryptographic primitive)

---

## Limitations

- **Identical-twin separation** — a live twin passes face-liveness by definition; only cross-modal fusion mitigates (open research problem, acknowledged per D31).
- **No novel ML claim** — anti-spoofing is protocol- and heuristic-based; no trained presentation-attack detection model is introduced. At-risk prediction is heuristic thresholds today; ML is a planned upgrade.
- **The liveness layers are unmeasured** — the attack corpus and the APCER/BPCER metrics (C3) do not exist, so no claim about a rejection rate can be made. The protocol claims are design claims, and the depth of the server-side grade is known to be shallower than intended (C2).
- **The face-match step is currently inert** — no embedding is generated and no similarity is computed (C7), so the liveness transcript is the only biometric check actually in force.
- **The offline path is not multi-instance safe** — the idempotency registry is process-local, so a deployment behind more than one API instance needs a shared store before the replay guarantees hold (C1).
- **Generalization** — contributions are protocol/design claims, and they do not claim robustness to unmodelled attack types (e.g. 3D-masked presentation).
- **Analytics evaluation** — forecasting claims require deployment-length longitudinal data; the effectiveness-tracking loop that would produce it is designed but not implemented.
