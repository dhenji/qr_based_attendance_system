# CS Contributions

This document states the project's contributions to computer science honestly. The framing is **systems and security-protocol engineering plus empirical evaluation** — not novel machine learning. The system uses zero trained models for anti-spoofing; liveness grading is built on open landmark tracking (MediaPipe Face Mesh) and geometric/statistical heuristics, chosen deliberately for offline capability, transparency, and auditability.

---

## C1 — Offline-First Liveness Protocol (flagship)

Standard liveness detection assumes an always-reachable server. Our defining constraint is offline-first: students' scans must be captured and provably trusted even when no server responds.

**Contribution**: an asynchronous liveness protocol where full validation is deferred, never skipped.

- Every scan produces a signed evidence bundle `{scan_id, nonce, timestamp, session_ref, challenge transcript, landmark series, QR liveness score, GPS, HMAC}`.
- Offline bundles are stored locally in `pending-liveness` state and re-validated server-side after sync (proposal.md:94).
- A server-side nonce registry rejects replayed or re-submitted bundles (anti-replay).
- The protocol is backward-compatible with online operation: the same bundle is validated immediately when connectivity exists.

This transforms liveness verification from an online gate into a provable, replay-resistant evidence trail — enabling anti-spoofing guarantees in environments (classrooms, rural connectivity) where prior work simply fails.

## C2 — Challenge-Response Liveness Grading (flagship)

**Contribution**: a server-issued, statistically graded challenge-response protocol for face liveness, verifiable entirely from a landmark transcript — no image classification model required.

- The server issues one or more random challenges per scan (blink, turn head left/right); the attacker cannot know the challenge sequence in advance (proposal.md:88).
- The client tracks MediaPipe Face Mesh landmarks and returns an evidence transcript: Eye Aspect Ratio (EAR) time series, head-pose angles (Perspective-n-Point), and inter-event timing (proposal.md:87).
- The server grades the transcript: challenge-response correlation, EAR dropout during blinks, temporal plausibility, and pose dynamics.
- This defeats printed photos (no live blink), screen/video replay (unknown random challenge), and distorted prints (fail 3D pose/motion checks) (proposal.md:89).

The contribution is the *grading protocol* — deterministic, explainable, and offline-verifiable — versus black-box classifier approaches that cannot produce auditable evidence.

## C3 — Multi-Layer Risk-Fusion Decision Framework

**Contribution**: a weighted multi-layer scoring architecture that fuses heterogeneous signals — QR liveness, face liveness, GPS proximity, per-session uniqueness, and enrollment match — into a composite risk score mapped to decision bands `accept / flag-for-review / reject`, computable in O(1) per scan (proposal.md:100).

- Each layer emits an independent confidence score; the fuse weights them.
- `flag-for-review` creates a human-in-the-loop tier backed by the stored evidence bundle — an audit trail for every decision, not just rejections.
- The framework treats identical twins honestly: a live twin passes face liveness by definition; the mitigation is cross-modal fusion (physical card, GPS, uniqueness), documented as a limitation rather than a solved claim (proposal.md:105).

## C4 — Evaluation Methodology: Attack Corpus + APCER/BPCER

**Contribution**: a reproducible evaluation protocol for the liveness layers, following ISO/IEC 30107-3 presentation-attack metrics — rare in comparable student-built systems (proposal.md:401).

- A constructed attack corpus: printed photos, device-screen replays, recorded video, distorted prints, and replay of captured evidence bundles.
- Metrics: Attack Presentation Classification Error Rate (APCER) and Bona Fide Presentation Classification Error Rate (BPCER) per attack type.
- Evaluation also covers the protocol layer: nonce-replay rejection rate and challenge-guessing resistance.

This separates *what the protocol guarantees* (replay, photo, distortion) from *what it cannot claim* (biometric identity, twin separation) — a defensible, quantitative boundary.

## C5 — At-Risk Forecasting over Sync-Corrupted Attendance Data

**Contribution**: predictive/prescriptive analytics adapted to the data regime this system itself creates — sparse, batch-arriving, sync-gapped attendance enriched with an untrusted-evidence pipeline (proposal.md:122; presentation-slides.md:190).

- Standard forecasting assumes complete, timely, trusted data; our source is delayed, batched, and partially `pending-liveness`.
- Per-student features built from scan-streak gaps, per-session absence patterns, and explicit sync-lag corrections.
- A lightweight interpretable model (logistic regression / gradient boosting — deliberately not a black box) predicts at-risk students for upcoming sessions.
- A prescriptive rule engine converts predictions into actions (professor alerts, student reminders) with effectiveness tracking — closing the loop so the analytics layer is itself evaluated.

The dashboard layers (descriptive: what happened, diagnostic: why, predictive: what's next, prescriptive: what to do) are the product surface; the contribution is the *forecasting-under-data-quality-regime* work underneath.

---

## Deliberately NOT Contributions

These are standard engineering with off-the-shelf components; presenting them as research invites challenge in defense:

- QR decoding/live-detection heuristics (`html5-qrcode`)
- GPS geofencing
- HMAC session-code generation/verification
- Duplicate-scan (one-per-session) enforcement
- The 4-level descriptive/diagnostic/predictive/prescriptive taxonomy itself (standard BI framework)
- PWA offline storage (IndexedDB + Service Workers)

---

## Limitations

- **Identical-twin separation** — a live twin passes face-liveness by definition; only cross-modal fusion mitigates (open research problem).
- **No novel ML claim** — anti-spoofing is protocol- and heuristic-based; no trained presentation-attack detection model is introduced.
- **Generalization** — contributions are protocol/design claims evaluated against the constructed attack corpus; they do not claim robustness to unmodelled attack types (e.g., 3D-masked presentation).
- **Analytics evaluation** — forecasting claims require deployment-length longitudinal data; the effectiveness-tracking loop is designed to produce it.