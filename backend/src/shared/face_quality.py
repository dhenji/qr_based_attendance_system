from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None  # type: ignore[assignment]

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]

try:
    import mediapipe as mp
except Exception:  # pragma: no cover
    mp = None  # type: ignore[assignment]


# Quality-gate thresholds (single source of truth; mirrored by the client).
BRIGHTNESS_MIN = 40.0
BRIGHTNESS_MAX = 220.0
FACE_SIZE_MIN_RATIO = 0.15
CENTERING_MAX_OFFSET = 0.3
SHARPNESS_MIN_VARIANCE = 50.0
EAR_MIN = 0.2

_MAX_FACES = 10

_MODEL_CANDIDATES = [
    os.environ.get("FACE_LANDMARKER_MODEL_PATH"),
    "frontend/static/models/face_landmarker.task",
    "../frontend/static/models/face_landmarker.task",
    "/app/frontend/static/models/face_landmarker.task",
    "/app/face_landmarker.task",
    "face_landmarker.task",
]


def _model_path() -> str | None:
    for candidate in _MODEL_CANDIDATES:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


@dataclass(frozen=True)
class FaceQualityResult:
    """Outcome of running the quality gates on one image."""

    ok: bool
    code: str | None = None
    gate: str | None = None
    message: str | None = None
    face_count: int = 0
    metrics: dict[str, Any] = field(default_factory=dict)


_landmarker: Any = None
_landmarker_failed: bool = False


def _get_landmarker() -> Any:
    global _landmarker, _landmarker_failed
    if _landmarker is not None:
        return _landmarker
    if _landmarker_failed:
        return None
    path = _model_path()
    if path is None or cv2 is None or mp is None or np is None:
        _landmarker_failed = True
        return None
    try:
        from mediapipe.tasks.python import vision
        from mediapipe.tasks.python.core import base_options

        options = vision.FaceLandmarkerOptions(
            base_options=base_options.BaseOptions(model_asset_path=path),
            running_mode=vision.RunningMode.IMAGE,
            num_faces=_MAX_FACES,
        )
        _landmarker = vision.FaceLandmarker.create_from_options(options)
        return _landmarker
    except Exception:
        _landmarker_failed = True
        _landmarker = None
        return None


def decode_image(content: bytes):
    if cv2 is None or np is None:
        raise ValueError("opencv unavailable")
    arr = np.frombuffer(content, dtype=np.uint8)
    if arr.size == 0:
        raise ValueError("empty image")
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("invalid image")
    return img


def _landmarks_list(img) -> list[Any]:
    landmarker = _get_landmarker()
    if landmarker is None:
        raise RuntimeError("face landmarker unavailable")
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result = landmarker.detect(mp_image)
    if not getattr(result, "face_landmarks", None):
        return []
    return list(result.face_landmarks)


def _bbox(landmarks, width: int, height: int) -> tuple[float, float, float, float]:
    xs = [lm.x * width for lm in landmarks]
    ys = [lm.y * height for lm in landmarks]
    return (min(xs), min(ys), max(xs), max(ys))


_LEFT_EYE_IDX = (33, 160, 158, 133, 153, 144)
_RIGHT_EYE_IDX = (362, 385, 387, 263, 373, 380)


def _ear(landmarks, idx: tuple[int, ...]) -> float:
    p = landmarks
    a = np.array([p[idx[1]].x, p[idx[1]].y])
    b = np.array([p[idx[2]].x, p[idx[2]].y])
    c = np.array([p[idx[3]].x, p[idx[3]].y])
    d = np.array([p[idx[4]].x, p[idx[4]].y])
    e = np.array([p[idx[5]].x, p[idx[5]].y])
    f = np.array([p[idx[0]].x, p[idx[0]].y])
    vertical1 = float(np.linalg.norm(a - d))
    vertical2 = float(np.linalg.norm(b - e))
    horizontal = float(np.linalg.norm(f - c))
    if horizontal <= 1e-9:
        return 0.0
    return (vertical1 + vertical2) / (2.0 * horizontal)


def assess_image(img) -> FaceQualityResult:
    if cv2 is None or np is None:
        return FaceQualityResult(
            ok=False, code="invalid_image", gate="decode", message="opencv unavailable"
        )

    height, width = img.shape[:2]
    if height == 0 or width == 0:
        return FaceQualityResult(
            ok=False, code="invalid_image", gate="decode", message="empty image"
        )

    try:
        faces = _landmarks_list(img)
    except Exception:
        return FaceQualityResult(
            ok=False,
            code="no_face_detected",
            gate="detection",
            message="face detection failed",
        )

    face_count = len(faces)
    if face_count == 0:
        return FaceQualityResult(
            ok=False,
            code="no_face_detected",
            gate="detection",
            message="No face detected",
            face_count=0,
        )
    if face_count > 1:
        return FaceQualityResult(
            ok=False,
            code="multiple_faces",
            gate="single_face",
            message="Multiple faces detected",
            face_count=face_count,
        )

    face = faces[0]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    brightness = float(gray.mean())
    if brightness < BRIGHTNESS_MIN or brightness > BRIGHTNESS_MAX:
        return FaceQualityResult(
            ok=False,
            code="quality_too_low",
            gate="brightness",
            message="Image too dark / too bright",
            face_count=1,
            metrics={"brightness": brightness},
        )

    x0, y0, x1, y1 = _bbox(face, width, height)
    face_area = (x1 - x0) * (y1 - y0)
    image_area = float(width * height)
    size_ratio = face_area / image_area if image_area > 0 else 0.0
    if size_ratio < FACE_SIZE_MIN_RATIO:
        return FaceQualityResult(
            ok=False,
            code="quality_too_low",
            gate="face_size",
            message="Face too small",
            face_count=1,
            metrics={"face_size_ratio": size_ratio},
        )

    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    offset_x = abs(cx - width / 2.0) / (width / 2.0) if width > 0 else 1.0
    offset_y = abs(cy - height / 2.0) / (height / 2.0) if height > 0 else 1.0
    if offset_x > CENTERING_MAX_OFFSET or offset_y > CENTERING_MAX_OFFSET:
        return FaceQualityResult(
            ok=False,
            code="quality_too_low",
            gate="centering",
            message="Face not centered",
            face_count=1,
            metrics={"center_offset_x": offset_x, "center_offset_y": offset_y},
        )

    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if lap_var < SHARPNESS_MIN_VARIANCE:
        return FaceQualityResult(
            ok=False,
            code="quality_too_low",
            gate="sharpness",
            message="Image blurry",
            face_count=1,
            metrics={"sharpness": lap_var},
        )

    try:
        left_ear = _ear(face, _LEFT_EYE_IDX)
        right_ear = _ear(face, _RIGHT_EYE_IDX)
    except Exception:
        left_ear = 0.0
        right_ear = 0.0
    if left_ear <= EAR_MIN or right_ear <= EAR_MIN:
        return FaceQualityResult(
            ok=False,
            code="quality_too_low",
            gate="eyes_open",
            message="Please keep your eyes open",
            face_count=1,
            metrics={"left_ear": left_ear, "right_ear": right_ear},
        )

    return FaceQualityResult(
        ok=True,
        face_count=1,
        metrics={
            "brightness": brightness,
            "face_size_ratio": size_ratio,
            "center_offset_x": offset_x,
            "center_offset_y": offset_y,
            "sharpness": lap_var,
            "left_ear": left_ear,
            "right_ear": right_ear,
        },
    )


def assess_image_bytes(content: bytes) -> FaceQualityResult:
    try:
        img = decode_image(content)
    except ValueError as exc:
        return FaceQualityResult(
            ok=False, code="invalid_image", gate="decode", message=str(exc)
        )
    return assess_image(img)
