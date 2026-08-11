# Models Used

This document catalogs every model the system relies on. Honest summary: **zero trained models are introduced for anti-spoofing** — the security core is pretrained landmark tracking plus geometric/statistical heuristics that run fully offline and produce auditable evidence. The only models we train ourselves are the lightweight analytics forecasting models.

| Component | Model / Library | Type | Where it runs | Trained by us? |
| --------- | --------------- | ---- | ------------- | -------------- |
| Face landmark tracking | MediaPipe Face Mesh | Pretrained deep regression (468 landmarks) | Client browser (WASM) | No |
| Face liveness grading | EAR + Perspective-n-Point (PnP) heuristics | Geometric/statistical algorithm | Client captures, server grades | No (designed by us) |
| Enrolled-face matching (optional) | face-api.js Face Recognition (ResNet-34-like embeddings) | Pretrained face embedding net | Client / server | No |
| At-risk forecasting | Logistic regression / gradient boosting (scikit-learn) | Classical ML, interpretable | Server (Python) | **Yes** |
| QR decoding | html5-qrcode | Decoder (non-ML) | Client browser | No |

---

## 1. MediaPipe Face Mesh (face landmark tracking)

- **What**: pretrained neural network that regresses **468 3D facial landmarks** from a single RGB frame (proposal.md:88).
- **Role in the system**: the only model in the anti-spoofing pipeline. It is *input to* liveness reasoning, never the decision-maker itself.
- **Why it**: runs fully client-side (WASM) — no network round-trip, which is mandatory for the offline-first constraint; on-device, no student video ever leaves the phone.
- **Outputs consumed**: the 68-keypoint subset — eye contours for EAR, nose/chin anchors for head-pose.
- **Used as-is**: no fine-tuning, no retraining on our data.

## 2. EAR + PnP Liveness Grading (the protocol, not a model)

The decision layer is deliberately **not** a presentation-attack-detection classifier. Instead, deterministic geometry:

- **Eye Aspect Ratio (EAR)**: ratio of vertical to horizontal eye-contour distances per frame; a blink is a sustained EAR dropout across consecutive frames (proposal.md:187).
- **Head-pose estimation**: Perspective-n-Point over stable landmarks (eye corners, nose tip, chin) yields yaw/pitch/roll angles per frame; a "turn head" challenge grades pose-angle excursion and return (proposal.md:87).

A scan passes only if the landmark transcript correlates with the server-issued random challenge sequence — blink timing, EAR depth, pose dynamics, and inter-event timing must all be plausible (proposal.md:88).

**Why heuristics, not a CNN**: (a) determinism — the same transcript always yields the same verdict, so every decision is explainable and appealable; (b) auditability — the transcript *is* the evidence bundle, adversarial examples don't apply; (c) offline operability and near-zero runtime cost.

## 3. face-api.js (enrolled-face match — anti-spoofing layer, optional)

- **What**: face detection (SSD MobileNet) + 68-point landmarks + face recognition embeddings (ResNet-34-like) (proposal.md:251).
- **Role**: produces the `face_embedding` vector stored at enrollment for each student (proposal.md:320) and an enrollment-match confidence (`Enrolled-face match` layer in the risk-fusion scorer).
- **Scope constraint**: face matching here is an *additional anti-spoofing layer only* — facial recognition as a standalone identity system is explicitly out of scope (proposal.md:383).

## 4. At-Risk Forecasting (the one model type we train)

- **Algorithm**: logistic regression or gradient boosting via scikit-learn (proposal.md:122, 252).
- **Input features** (per student): scan-streak gaps, per-session absence patterns, sync-lag corrections — engineered for the sparse, batch-arriving, partially `pending-liveness` data regime this system creates.
- **Output**: at-risk probability per student for upcoming sessions; consumed by the prescriptive rule engine (alerts, reminders) which tracks its own effectiveness.
- **Interpretability requirement**: deliberately lightweight and non-black-box; the goal is a defensible, explainable risk flag, not state-of-the-art accuracy.

## 5. Non-ML components (for completeness)

- **html5-qrcode** — QR decoding and live-detection heuristics (proposal.md:250). Not ML.
- **HMAC-SHA256** — session-code generation/verification. Not ML.

---

## What Is NOT Used

- No trained presentation-attack-detection (anti-spoofing) model — no Silent-Face-Anti-Spoofing or similar CNN; liveness is protocol-based (see section 2).
- No deep forecasting models — accuracy-vs-interpretability tradeoff resolved in favor of the latter.
- No models are trained on student biometric data; MediaPipe and face-api.js run as-is.