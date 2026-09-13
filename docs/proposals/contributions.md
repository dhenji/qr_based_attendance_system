# CS Contributions

This document states the project's contributions to computer science honestly. The framing is **systems and security-protocol engineering plus empirical evaluation** — not novel machine learning. The system uses zero trained models for anti-spoofing; liveness grading is built on open landmark tracking (MediaPipe Face Mesh) and geometric/statistical heuristics, chosen deliberately for offline capability, transparency, and auditability.

**Folder mapping**: each contribution maps to a specific backend feature folder and frontend component directory per the project structure.

---

## C1 — Offline-First Liveness Protocol (flagship)

**Folder**: `frontend/src/lib/features/liveness/` (frontend-only feature — no backend `features/liveness/` dir) + `backend/src/features/sync/` (model.py only — router pending) + `frontend/src/lib/features/sync/` + `frontend/src/service-worker.ts` (both proposed — deferred per frontend-architecture.md)

Standard liveness detection assumes an always-reachable server. Our defining constraint is offline-first: students' scans must be captured and provably trusted even when no server responds.

**Contribution**: an asynchronous liveness protocol where full validation is deferred, never skipped.

- Every scan produces a signed evidence bundle `{scan_id, nonce, timestamp, session_ref, challenge transcript, landmark series, QR liveness score, GPS, HMAC}`.
- Offline bundles are stored locally in `pending` state and re-validated server-side after sync (D16). Expired-window offline scans → `rejected` with reason `session_expired`.
- A server-side nonce registry rejects replayed or re-submitted bundles (anti-replay).
- The protocol is backward-compatible with online operation: the same bundle is validated immediately when connectivity exists.

This transforms liveness verification from an online gate into a provable, replay-resistant evidence trail — enabling anti-spoofing guarantees in environments (classrooms, rural connectivity) where prior work simply fails.

## C2 — Challenge-Response Liveness Grading (flagship)

**Folder**: `frontend/src/lib/features/liveness/` (frontend-only) + `frontend/src/lib/features/liveness/components/FaceChallenge.svelte` (proposed)

**Contribution**: a fixed-sequence, statistically graded challenge-response protocol for face liveness, verifiable entirely from a landmark transcript — no image classification model required.

- The system uses a **fixed challenge sequence** (blink → turn head left → turn head right) — chosen for offline operability (no server round-trip needed) per D31.
- The client tracks MediaPipe Face Mesh landmarks and returns an evidence transcript: Eye Aspect Ratio (EAR) time series, head-pose angles (Perspective-n-Point), and inter-event timing.
- The server grades the transcript: challenge-response correlation, EAR dropout during blinks, temporal plausibility, and pose dynamics.
- This defeats printed photos (no live blink), screen/video replay (fixed sequence cannot be pre-recorded for unknown challenge), and distorted prints (fail 3D pose/motion checks).

The contribution is the _grading protocol_ — deterministic, explainable, and offline-verifiable — versus black-box classifier approaches that cannot produce auditable evidence.

## C3 — Evaluation Methodology: Attack Corpus + APCER/BPCER

**Folder**: `backend/src/tests/` (empty scaffolding — no test runner configured yet; planned)

**Contribution**: a reproducible evaluation protocol for the liveness layers, following ISO/IEC 30107-3 presentation-attack metrics — rare in comparable student-built systems.

- A constructed attack corpus: printed photos, device-screen replays, recorded video, distorted prints, and replay of captured evidence bundles.
- Metrics: Attack Presentation Classification Error Rate (APCER) and Bona Fide Presentation Classification Error Rate (BPCER) per attack type.
- Evaluation also covers the protocol layer: nonce-replay rejection rate and challenge-guessing resistance.

This separates _what the protocol guarantees_ (replay, photo, distortion) from _what it cannot claim_ (biometric identity, twin separation) — a defensible, quantitative boundary.

## C4 — Heuristic At-Risk Analytics over Sync-Corrupted Attendance Data

**Folder**: `backend/src/features/analytics/` + `backend/src/features/analytics/tasks.py` (planned) + `frontend/src/lib/features/analytics/components/ChartCanvas.svelte` (planned)

**Contribution**: predictive/prescriptive analytics adapted to the data regime this system itself creates — sparse, batch-arriving, sync-gapped attendance enriched with an untrusted-evidence pipeline.

- Standard forecasting assumes complete, timely, trusted data; our source is delayed, batched, and partially pending (D16).
- **MVP**: heuristic thresholds (env-configurable) — absence_rate > 0.30 → high; streak ≥ 3 → high; sync_lag ≥ 5 → medium; trend_slope < −0.05/week → medium (D35). Runs as a daily batch job writing to `student_risk_scores`. Deterministic, explainable, auditable.
- **Upgrade path**: logistic regression (scikit-learn) using the identical feature vector — preserving backward compatibility of the feature engineering.
- A prescriptive rule engine converts predictions into actions (professor alerts, student reminders) with effectiveness tracking — closing the loop so the analytics layer is itself evaluated.
- Two rate metrics: **Compliance Rate** = present / total (default) and **Participation Rate** = (present + late + excused) / total (D36).
- Visualization via Chart.js wrapped in reusable `ChartCanvas.svelte` (D41).

The dashboard layers (descriptive: what happened, diagnostic: why, predictive: what's next, prescriptive: what to do) are the product surface; the contribution is the _forecasting-under-data-quality-regime_ work underneath.

## C5 — Window-Based Attendance Policy Engine

**Folder**: `backend/src/features/session/` + `backend/src/features/attendance/service.py`

**Contribution**: a time-window policy engine that determines attendance status (present/late/absent) from configurable windows, duration expiry, and scheduled class end — with per-session overrides of offering defaults.

- Session creation: professor sets `duration_minutes`, `present_window_minutes`, `late_window_minutes`; server computes `expires_at = min(now + duration, scheduled_end_time)` (D12).
- Constraint: `present_window + late_window ≤ duration` — enforced at the API layer.
- Offering-level defaults (`default_present_window_minutes`, `default_late_window_minutes`) are prefilled per D14; per-session overrides allow fine-tuning.
- Status determination: scans within present_window → `present`; within late_window after that → `late`; no-scan when session expires → `absent` (D13).
- Supports both code-entry and QR-scan session entry modes (D18).

## C6 — Excuse State Machine with Three-Path Workflow

**Folder**: `backend/src/features/excuse/` + `frontend/src/lib/features/excuse/components/` (planned)

**Contribution**: a formal state machine for attendance excuses with three initiation paths, each producing an auditable trail — not a simple status flip.

- **State machine**: `pending` → `approved` | `rejected` (D21). Direct-approved path for professor-initiated excuses.
- **Three paths**: (a) professor quick-excuse (absent/late student → excused with reason); (b) professor-initiated with evidence (holds excuse letter → files + approves immediately); (c) student-initiated request (submits reason + evidence → professor approves/rejects).
- **Effects**: excusing overrides scanned status; `original_status` preserves what actually happened (D22). Final status = `excused` (treated as present for compliance rate, D36).
- **Bulk action**: "Excuse All Absent" for a session (typical: cancelled class) (D23).
- **Attachments**: stored in S3-compatible storage (Supabase Storage / R2 / S3); DB stores URL references only (D24).
- **Notifications**: fired at each state transition.

## C7 — Biometric Template Protection with Pull-on-Distribution

**Folder**: `backend/src/features/student/` (face columns; admin face-enrollment service/router planned) + `frontend/src/lib/features/student/components/FaceEnrollmentModal.svelte` (proposed) + `frontend/src/lib/features/sync/` (proposed — deferred per frontend-architecture.md)

**Contribution**: a biometric enrollment and distribution pipeline that generates, encrypts, and distributes face embeddings without training any model — using pretrained embeddings with versioned pull-on-login.

- **Enrollment**: admin captures **3 photos** (front, left, right) per D43. Quality gates: brightness, face-size, single-face check. Server runs pretrained face-api.js ResNet-34-like model → 128-d embedding per photo. Stored as encrypted JSON blob in `students.face_embedding` (BYTEA): `{"mean":[128f],"angles":{"front":[128f],"left":[128f],"right":[128f]}}` (D28).
- **Encryption**: face embedding encrypted at rest (pgcrypto/AES) on server; cached encrypted on device via WebCrypto device key.
- **Distribution**: pull-on-login — client checks `face_embedding_version`, downloads if newer; cached in IndexedDB (D29). No push/WebSocket infrastructure.
- **Verification**: cosine similarity ≥ `FACE_MATCH_THRESHOLD` (default 0.7). Score bands: ≥ 0.70 → pass; 0.65–0.70 → review-flag → liveness-review queue; < 0.65 → fail. Offline: compares against cached embedding locally; only scores/evidence sync to server (D30).
- **Revocation**: on student archive; re-enrollment supersedes old vectors.
- **No model training**: the pretrained face-api.js model runs as-is; we generate embeddings but do not fine-tune it.

## C8 — Academic Hierarchy with Multi-Program Course Sharing

**Folder**: `backend/src/features/program/` + `backend/src/features/course/`

**Contribution**: a structured academic hierarchy (Program → Year Level → Course) with per-year term structures, enabling the same course to be shared across multiple programs and year levels — with all filters and analytics supporting program/year slicing.

- **Hierarchy**: Programs → Year Levels (own term structures as JSONB) → Courses. Strict FK constraints (CASCADE/RESTRICT) (D1).
- **Term structures**: per-program-per-year — e.g., BSCS Y1/Y2 = 2 semesters; BSCS Y3 = 1st, 2nd + Midyear; BSIT defines its own (D3).
- **Course sharing**: a course can belong to multiple programs/year levels (D6); filters everywhere support program/year slicing of the same course.
- **Enrollment validation**: `enrollments.semester` validated against the year level's term structure (D5).
- **Admin management**: CRUD flows for programs, year levels, courses; replacing year-level promotion with intentional academic structure updates (D38).

---

## Deliberately NOT Contributions

These are standard engineering with off-the-shelf components; presenting them as research invites challenge in defense:

- QR decoding/live-detection heuristics (`html5-qrcode`)
- GPS geofencing (Haversine)
- HMAC session-code generation/verification
- Duplicate-scan (one-per-session) enforcement
- The 4-level descriptive/diagnostic/predictive/prescriptive taxonomy itself (standard BI framework)
- PWA offline storage (IndexedDB + Service Workers)
- Chart.js charting (standard visualization library)
- Argon2id password hashing
- AES-256-GCM backup encryption (standard cryptographic primitive)

---

## Limitations

- **Identical-twin separation** — a live twin passes face-liveness by definition; only cross-modal fusion mitigates (open research problem, acknowledged per D31).
- **No novel ML claim** — anti-spoofing is protocol- and heuristic-based; no trained presentation-attack detection model is introduced. At-risk prediction starts as heuristic thresholds; ML is a planned upgrade.
- **Generalization** — contributions are protocol/design claims evaluated against the constructed attack corpus; they do not claim robustness to unmodelled attack types (e.g., 3D-masked presentation).
- **Analytics evaluation** — forecasting claims require deployment-length longitudinal data; the effectiveness-tracking loop is designed to produce it.

