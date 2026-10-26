# MobileFaceNet model license

Model file: `backend/models/mobilefacenet.onnx`

- Source: InsightFace model zoo, `buffalo_sc.zip` → `w600k_mbf.onnx`
  (https://github.com/deepinsight/insightface/releases/tag/model-zoo)
- Model: MobileFaceNet (w600k_mbf), ArcFace-trained, 112x112 input, 512-d
  embedding output.
- License: InsightFace model zoo license (research/non-commercial; verify
  before commercial use).
- SHA-256: `9cc6e4a75f0e2bf0b1aed94578f144d15175f357bdc05e815e5c4a02b319eb4f`
- Verified: 2026-10-26

Notes:
- Input preprocessing in this project: BGR->RGB, resize to 112x112,
  normalize (x-127.5)/128.0, NCHW layout (ArcFace standard).
- Output is L2-normalized by `shared/face_embedding_generator.py`.
EOF