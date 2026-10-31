# Models Used

> **Implementation status (2026-10-31):** client-side MediaPipe liveness with
> server-side evidence grading ships, and face enrollment now generates a real
> embedding server-side via MobileFaceNet ONNX (InsightFace `w600k_mbf`,
> 512-d) with a landmark-based fallback (`backend/src/shared/face_embedding_generator.py`).
> Scan-time matching runs server-side via cosine similarity against the stored
> embedding; `face_match_score` is no longer client-asserted.> See ADR-068 and ADR-083.
> This document catalogs every model the system relies on. Honest summary: **zero trained models are introduced for anti-spoofing** — the security core is pretrained landmark tracking plus geometric/statistical heuristics that run fully offline and produce auditable evidence. **Zero trained models are used for analytics in the MVP** — at-risk prediction starts as heuristic thresholds (env-configurable); ML (logistic regression) is a planned upgrade using the identical feature vector. The face embedding pipeline uses pretrained models exclusively; we train nothing.

| Component                     | Model / Library                               | Type                                                              | Where it runs                  | Trained by us?      |
| ----------------------------- | --------------------------------------------- | ----------------------------------------------------------------- | ------------------------------ | ------------------- |
| Face landmark tracking        | MediaPipe Face Mesh                           | Pretrained deep regression (468 landmarks)                        | Client browser (WASM)          | No                  |
| Face liveness grading         | EAR + Perspective-n-Point (PnP) heuristics    | Geometric/statistical algorithm                                   | Client captures, server grades | No (designed by us) |
| Enrolled-face matching        | MobileFaceNet cosine similarity (512-d)      | Cosine similarity between stored and live embeddings              | Server                         | No                  || Face embedding generation     | MobileFaceNet ONNX (`w600k_mbf`, InsightFace) | Pretrained 512-d embedding from 3-angle photos (front/left/right) | Server                         | No                  |     | At-risk forecasting (MVP) | Heuristic thresholds (env-configurable) | Rule-based scoring (absence_rate, streak, sync_lag, trend_slope) | Server (Python) | No (rule-based) |
| At-risk forecasting (upgrade) | Logistic regression (scikit-learn)            | Classical ML, interpretable                                       | Server (Python)                | Planned (future)    |
| Analytics visualization       | Chart.js (+ date client adapter)              | Non-ML charting library                                           | Client browser                 | No                  |
| QR decoding                   | html5-qrcode                                  | Decoder (non-ML)                                                  | Client browser                 | No                  |

---

## 1. MediaPipe FaceLandmarker (detection + landmarks) — the only model

- **What**: a pretrained bundle that regresses **478 3D facial landmarks** from a single RGB frame. The shipped asset bundles three things: a BlazeFace **short-range face detector**, the **478-landmark landmark model**, and the canonical face-geometry module that produces the facial transformation matrix.
- **Asset inventory** — the repository contains exactly one model file:

  | File                                                       | Size   | sha256                                                             |
  | ---------------------------------------------------------- | ------ | ------------------------------------------------------------------ |
  | `frontend/static/models/face_landmarker.task`              | 1.4 MB | `af23fc7c1ff21d034deaa2b7fc1d56bb670ce69a4cbdc9579b6f1afd680835f4` |
  | `frontend/static/wasm/vision_wasm_internal.wasm` (runtime) | 12 MB  | — (the WASM runtime, not a model)                                  |

  Verified by `sha256sum frontend/static/models/face_landmarker.task` and
  `find . \( -name "*.task" -o -name "*.tflite" -o -name "*.onnx" \) -not -path "*/node_modules/*"`
  → one hit.

- **Runtime**: `@mediapipe/tasks-vision` 1.0.1, loaded through
  `FilesetResolver.forVisionTasks('/wasm')` against the vendored WASM runtime in
  `frontend/static/wasm/`. `frontend/src/lib/features/liveness/model.ts` holds one shared
  instance (a module-level promise) so the ~13 MB load happens once per session, not once
  per scan.
- **Configuration** (`liveness/model.ts:42-51`): `runningMode: 'VIDEO'`, `numFaces: 1`,
  `outputFacialTransformationMatrixes: true`, detection/presence/tracking confidence `0.5`,
  and a GPU delegate with a CPU fallback when the device refuses the GPU delegate.
  `outputFaceBlendshapes` is **not** enabled today.
- **Role in the system**: the only model in the anti-spoofing pipeline. It is _input to_
  liveness reasoning, never the decision-maker itself.
- **Outputs consumed**:
  - **EAR** — the 6-point eye contours, left `[362, 385, 387, 263, 373, 380]` and right
    `[33, 160, 158, 133, 153, 144]` (`FaceScanner.svelte:110-111`).
  - **Head yaw** — the facial transformation matrix (`FaceScanner.svelte:172-193`), with a
    landmark-geometry fallback that offsets the nose tip against the outer eye corners
    (`:195-200`).
  - **Face-to-camera distance** — the inter-eye spread (landmarks `33` ↔ `263`) through a
    pinhole model with an assumed IPD of 0.063 m and a 70° horizontal field of view
    (`:52-53, 160-168`).
- **Used as-is**: no fine-tuning, no retraining on our data. The model runs in the browser, so
  no student video ever leaves the phone — a hard requirement for the offline-first design.

## 2. EAR + PnP liveness grading (the protocol, not a model)

The decision layer is deliberately **not** a presentation-attack-detection classifier. Instead, deterministic geometry:

- **Eye Aspect Ratio (EAR)**: ratio of vertical to horizontal eye-contour distances per frame; a blink is a sustained EAR dropout across consecutive frames.
- **Head-pose estimation**: Perspective-n-Point over stable landmarks yields yaw per frame; a "turn head" challenge grades pose-angle excursion and return.

A scan passes only if the landmark transcript satisfies the **fixed** challenge sequence (blink → left → right, per D31) — blink timing, EAR depth, pose dynamics, and inter-event timing must all be plausible.

**Why heuristics, not a CNN**: (a) determinism — the same transcript always yields the same verdict, so every decision is explainable and appealable; (b) auditability — the transcript _is_ the evidence bundle; (c) offline operability and near-zero runtime cost.

**What the server actually enforces** (`backend/src/features/attendance/service.py:147-162`): all three challenge booleans are true, `ear_samples` is non-empty, the **mean** EAR sits inside `[0.05, 0.50]`, and `pnp_evidence` is non-empty. Four checks — the yaw values inside `pnp_evidence` are never inspected, and the blob is a free-form dict, so `{"x": 1}` satisfies the last one.

## 3. Face embedding generation and matching — **implemented (MobileFaceNet ONNX, server-side)**

Shipped asset:

| File                                | Size  | sha256                                                             | License                                         |
| ----------------------------------- | ----- | ------------------------------------------------------------------ | ----------------------------------------------- |
| `backend/models/mobilefacenet.onnx` | 13 MB | `9cc6e4a75f0e2bf0b1aed94578f144d15175f357bdc05e815e5c4a02b319eb4f` | InsightFace model zoo (research/non-commercial) |

This is the honest state of the biometric identity layer.

**What ships:**

- The enrollment route `POST /admin/face-enrollment/{student_id}` takes three photos
  (front, left, right — D43) and validates each for non-empty content, a size cap and an
  `image/*` content type (`backend/src/features/face_enrollment/service.py:41-60`).
- The enrollment is audited, the server-side cache is invalidated, and `face_embedding_version`
  is bumped so stale device copies cannot match (`face_enrollment/service.py:121-129`).
- The stored blob is now a real 512-d MobileFaceNet embedding serialized by
  `shared/face_embeddings.serialize_embedding` (header + algorithm + vector), generated
  from the three photos via `shared/face_embedding_generator.generate_embedding_from_images`.
  A landmark-based fallback is used when the ONNX model is unavailable.- Distribution is pull-on-login (D29): `GET /student/me/face-embedding?current_version=N`
  returns the blob when the client's copy is stale, 204 when it is current, and 404
  `face_embedding_not_found` when there is no enrollment
  (`backend/src/features/student/service.py:330-357`). The client caches it in IndexedDB,
  encrypted with an AES-GCM key generated on the device and stored as a non-extractable
  `CryptoKey` (`frontend/src/lib/features/student/face.svelte.ts:46-74`).

**What does not ship:**

- **No recognition model.** MediaPipe FaceLandmarker produces landmarks and (optionally)
  blendshapes — it does not produce an identity embedding. Adding one means a second model
  family (e.g. an ArcFace/InsightFace ONNX model) that must run in the browser for the
  offline path.
- **No encryption at rest**: the embedding blob is stored as serialized bytes
  (`shared/face_embeddings.serialize_embedding`); at-rest encryption is not implemented.- **Similarity comparison now ships.** `submit_scan` generates a live embedding and
  compares it to the stored reference via `cosine_similarity` (see
  `attendance/service.py`); the resulting score drives the pass/review/fail bands. The
  client no longer asserts `face_match_score`.- **No offline local compare** — explicitly deferred in the client for the same reason
  (`face.svelte.ts:15-17`).
- **Client- and server-side biometric quality gates are now implemented.** The six
  documented gates (brightness, face size, single face, centred, sharpness, eyes
  open) run in `shared/face_quality.py` on the server and are mirrored in the
  client (`FaceEnrollmentCamera.svelte`, `features/admin/enrollment/quality.ts`).

**What a real pipeline needs:** a recognition model; a documented decrypt scheme for the
cached blob; AES-256-GCM at rest with a server-side key; and the comparison itself —
ideally server-side, so the score is computed from a stored reference rather than asserted
by the client. `face_embedding_version` already exists to force a re-enrollment when the
embedding format changes.

## 4. At-Risk Forecasting

### MVP: Heuristic Threshold Engine (rule-based, not trained)

- **Algorithm**: env-configurable heuristic thresholds, not a trained model.
- **Features** (per student): absence_rate = absences / expected_sessions; max_streak (consecutive misses); sync_lag (pending syncs >24h); 4-week linear trend_slope (D35).
- **Thresholds** (D35): absence_rate > 0.30 → high; > 0.15 → medium; max_streak ≥ 3 → high; sync_lag ≥ 5 → medium; trend_slope < −0.05/week → medium. Order of evaluation: high overrides medium overrides low.
- **Expected sessions** derived from course metadata: `semester_weeks × sessions_per_week` (e.g. 3 units ≈ 2 meetings/week × 1.5h × 16 weeks → 32 expected sessions per semester).
- **Output**: rows in `student_risk_scores` with risk_probability (numeric score), risk_level (low/medium/high), and features JSONB. Unique per (student_id, offering_id, semester, computed_day).
- **Batch schedule**: daily at 02:00 (configurable via `RISK_BATCH_CRON`). Manual refresh endpoint available for admins.
- **Interpretability**: deterministic, explainable, auditable — same input always produces same output.

### Upgrade Path: Logistic Regression (planned, not yet implemented)

- **Algorithm**: logistic regression via scikit-learn — deliberately lightweight, non-black-box.
- **Feature vector**: identical to heuristic engine (absence_rate, max_streak, sync_lag, trend_slope) — the upgrade path preserves the same feature space.
- **Training**: requires longitudinal deployment data (months of attendance). Will be trained on historical data once sufficient volume exists.
- **Interpretability requirement**: deliberately chosen over gradient boosting or deep models for defensibility and explainability.

### Trained by us?

- **MVP (heuristic)**: No. Rule-based, not trained. The thresholds are environment-configurable constants.
- **Future (logistic regression)**: Will be. But not in the MVP; the contribution is the feature engineering over sync-corrupted data, not the model itself.

## 5. Non-ML components (for completeness)

- **html5-qrcode** — QR decoding and live-detection heuristics. Not ML.
- **HMAC-SHA256** — session-code generation/verification. Not ML.
- **OpenCV (`opencv-python-headless`)** — backend image decode/resize/color conversion/affine alignment (`shared/face_embedding_generator.py`) and sharpness/quality checks (`shared/face_quality.py`). Not ML.
- **Hand-rolled SVG charts** — analytics dashboards (Overview, Course Comparison, Trends, At-Risk, Export). Two reusable components: `frontend/src/lib/features/report/components/ReportTrendChart.svelte` and `ReportBarChart.svelte`. Non-ML; they draw `<svg>` primitives from the aggregated rows. ADR-041 specified Chart.js; ADR-091 records that the library was never adopted.
---

## What Is NOT Used

- **Face embedding model shipped:** `backend/models/mobilefacenet.onnx` (InsightFace `w600k_mbf`, research/non-commercial, 112×112 → 512-d). No face-api.js, ResNet, dlib, or TensorFlow.js. Scan-time matching runs server-side via cosine similarity against the stored embedding.
- No trained presentation-attack-detection (anti-spoofing) model — no Silent-Face-Anti-Spoofing or similar CNN; liveness is protocol-based (see section 2).
- No trained at-risk model in the MVP — prediction uses heuristic thresholds (section 4); logistic regression is a planned upgrade, not yet implemented.- No deep forecasting models — accuracy-vs-interpretability tradeoff resolved in favor of the latter.
- No models are trained on student biometric data; MediaPipe FaceLandmarker runs as-is.
- **No Chart.js.** The charts are hand-rolled SVG; `chart.js` is not a dependency.
- No ML in the charts — they are a pure visualization layer.
