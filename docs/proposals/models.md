# Models Used

This document catalogs every model the system relies on. Honest summary: **zero trained models are introduced for anti-spoofing** — the security core is pretrained landmark tracking plus geometric/statistical heuristics that run fully offline and produce auditable evidence. **Zero trained models are used for analytics in the MVP** — at-risk prediction starts as heuristic thresholds (env-configurable); ML (logistic regression) is a planned upgrade using the identical feature vector. The face embedding pipeline uses pretrained models exclusively; we train nothing.

| Component                     | Model / Library                                          | Type                                                              | Where it runs                  | Trained by us?      |
| ----------------------------- | -------------------------------------------------------- | ----------------------------------------------------------------- | ------------------------------ | ------------------- |
| Face landmark tracking        | MediaPipe Face Mesh                                      | Pretrained deep regression (468 landmarks)                        | Client browser (WASM)          | No                  |
| Face liveness grading         | EAR + Perspective-n-Point (PnP) heuristics               | Geometric/statistical algorithm                                   | Client captures, server grades | No (designed by us) |
| Enrolled-face matching        | face-api.js Face Recognition (ResNet-34-like embeddings) | Pretrained face embedding net                                     | Client / server                | No                  |
| Face embedding generation     | face-api.js (pretrained ResNet-34-like)                  | Pretrained 128-d embedding from 3-angle photos (front/left/right) | Server                         | No                  |
| At-risk forecasting (MVP)     | Heuristic thresholds (env-configurable)                  | Rule-based scoring (absence_rate, streak, sync_lag, trend_slope)  | Server (Python)                | No (rule-based)     |
| At-risk forecasting (upgrade) | Logistic regression (scikit-learn)                       | Classical ML, interpretable                                       | Server (Python)                | Planned (future)    |
| Analytics visualization       | Chart.js (+ date client adapter)                         | Non-ML charting library                                           | Client browser                 | No                  |
| QR decoding                   | html5-qrcode                                             | Decoder (non-ML)                                                  | Client browser                 | No                  |

---

## 1. MediaPipe Face Mesh (face landmark tracking)

- **What**: pretrained neural network that regresses **468 3D facial landmarks** from a single RGB frame (proposal.md:88).
- **Role in the system**: the only model in the anti-spoofing pipeline. It is _input to_ liveness reasoning, never the decision-maker itself.
- **Why it**: runs fully client-side (WASM) — no network round-trip, which is mandatory for the offline-first constraint; on-device, no student video ever leaves the phone.
- **Outputs consumed**: the 68-keypoint subset — eye contours for EAR, nose/chin anchors for head-pose.
- **Used as-is**: no fine-tuning, no retraining on our data.

## 2. EAR + PnP Liveness Grading (the protocol, not a model)

The decision layer is deliberately **not** a presentation-attack-detection classifier. Instead, deterministic geometry:

- **Eye Aspect Ratio (EAR)**: ratio of vertical to horizontal eye-contour distances per frame; a blink is a sustained EAR dropout across consecutive frames (proposal.md:187).
- **Head-pose estimation**: Perspective-n-Point over stable landmarks (eye corners, nose tip, chin) yields yaw/pitch/roll angles per frame; a "turn head" challenge grades pose-angle excursion and return (proposal.md:87).

A scan passes only if the landmark transcript correlates with the **fixed** challenge sequence (blink → left → right, chosen for offline operability per D31) — blink timing, EAR depth, pose dynamics, and inter-event timing must all be plausible.

**Why heuristics, not a CNN**: (a) determinism — the same transcript always yields the same verdict, so every decision is explainable and appealable; (b) auditability — the transcript _is_ the evidence bundle, adversarial examples don't apply; (c) offline operability and near-zero runtime cost.

## 3. face-api.js (enrolled-face match + embedding generation)

- **What**: face detection (SSD MobileNet) + 68-point landmarks + face recognition embeddings (ResNet-34-like) producing 128-dimensional vectors.
- **Role**: (1) At enrollment, the admin captures **3 photos** (front, left, right) per student (D43); the server runs the pretrained model on each photo to produce three 128-d embeddings. These are stored as an encrypted JSON blob in `students.face_embedding` (BYTEA): `{"mean":[128f],"angles":{"front":[128f],"left":[128f],"right":[128f]}}` (D28). The mean vector is used for primary comparison; per-angle vectors for tie-breaking. (2) During scan verification, the student's live face embedding is compared against the stored embedding(s) using cosine similarity (threshold ≥ 0.7, configurable via `FACE_MATCH_THRESHOLD`).
- **Scope constraint**: face matching here is an _additional anti-spoofing layer only_ — facial recognition as a standalone identity system is explicitly out of scope.
- **Trained by us?** No. The model runs as-is; we generate embeddings from it but do not fine-tune or retrain it. The `face_embedding_version` field tracks enrollment version (bumped on every write, D28).

## 4. At-Risk Forecasting

### MVP: Heuristic Threshold Engine (rule-based, not trained)

- **Algorithm**: env-configurable heuristic thresholds, not a trained model.
- **Features** (per student): absence_rate = absences / expected_sessions; max_consecutive_misses (streak); sync_lag_pending_count; 4-week linear trend_slope (D35).
- **Thresholds** (D35): absence_rate > 0.30 → high; > 0.15 → medium; streak ≥ 3 → high; sync_lag_pending ≥ 5 → medium; trend_slope < −0.05/week → medium. Order of evaluation: high overrides medium overrides low.
- **Expected sessions** derived from course metadata: `semester_weeks × sessions_per_week` (e.g. 3 units ≈ 2 meetings/week × 1.5h → 30 expected sessions per semester).
- **Output**: rows in `student_risk_scores` with risk_probability (numeric score), risk_level (low/medium/high), and features JSONB. Unique per (student, course, semester, computed_date).
- **Batch schedule**: daily at 02:00 (configurable via `RISK_BATCH_CRON`). Manual refresh endpoint available for admins.
- **Interpretability**: deterministic, explainable, auditable — same input always produces same output.

### Upgrade Path: Logistic Regression (planned, not yet implemented)

- **Algorithm**: logistic regression via scikit-learn — deliberately lightweight, non-black-box.
- **Feature vector**: identical to heuristic engine (absence_rate, streak, sync_lag, trend_slope) — the upgrade path preserves the same feature space.
- **Training**: requires longitudinal deployment data (months of attendance). Will be trained on historical data once sufficient volume exists.
- **Interpretability requirement**: deliberately chosen over gradient boosting or deep models for defensibility and explainability.

### Trained by us?

- **MVP (heuristic)**: No. Rule-based, not trained. The thresholds are environment-configurable constants.
- **Future (logistic regression)**: Will be. But not in the MVP; the contribution is the feature engineering over sync-corrupted data, not the model itself.

## 5. Non-ML components (for completeness)

- **html5-qrcode** — QR decoding and live-detection heuristics. Not ML.
- **HMAC-SHA256** — session-code generation/verification. Not ML.
- **Chart.js** (+ date client adapter) — analytics dashboards (Overview, Course Comparison, Trends, At-Risk, Export). Wrapped in a reusable Svelte component (`ChartCanvas.svelte`). Non-ML charting library; produces bar, line, area, and pie charts from aggregated data. No model inference.

---

## What Is NOT Used

- No trained presentation-attack-detection (anti-spoofing) model — no Silent-Face-Anti-Spoofing or similar CNN; liveness is protocol-based (see section 2).
- No trained at-risk model in the MVP — prediction uses heuristic thresholds (section 4); logistic regression is a planned upgrade, not yet implemented.
- No deep forecasting models — accuracy-vs-interpretability tradeoff resolved in favor of the latter.
- No models are trained on student biometric data; MediaPipe and face-api.js run as-is.
- No ML in Chart.js — it is a pure visualization library.

