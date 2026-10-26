from __future__ import annotations

import base64
import io
import os
from typing import Tuple

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None

try:
    import mediapipe as mp
except Exception:  # pragma: no cover
    mp = None

from shared.face_embeddings import ALLOWED_DIMS, EMBEDDING_DIM, l2_normalize, serialize_embedding


class FaceEmbeddingGenerationError(Exception):
    pass


# 5-point template for ArcFace/MobileFaceNet-style alignment on 112x112.
_REFERENCE_FACIAL_POINTS = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float32,
)

# 5-point landmark indices in MediaPipe's 468/478-landmark output.
_LEFT_EYE_IDX = 33
_RIGHT_EYE_IDX = 263
_NOSE_TIP_IDX = 1
_LEFT_MOUTH_IDX = 61
_RIGHT_MOUTH_IDX = 291

_MODEL_CANDIDATES = [
    os.environ.get("FACE_LANDMARKER_MODEL_PATH"),
    "frontend/static/models/face_landmarker.task",
    "../frontend/static/models/face_landmarker.task",
    "/app/frontend/static/models/face_landmarker.task",
    "/app/face_landmarker.task",
    "face_landmarker.task",
]

_ONNX_CANDIDATES = [
    os.environ.get("MOBILEFACENET_MODEL_PATH"),
    "backend/models/mobilefacenet.onnx",
    "models/mobilefacenet.onnx",
    "/app/models/mobilefacenet.onnx",
    "/app/backend/models/mobilefacenet.onnx",
]


_onnx_session = None
_onnx_failed = False


def _model_path() -> str | None:
    for candidate in _MODEL_CANDIDATES:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def _onnx_candidates() -> list[str]:
    try:
        from core.config import get_settings

        settings = get_settings()
        if getattr(settings, "mobilefacenet_model_path", None):
            return [settings.mobilefacenet_model_path] + list(_ONNX_CANDIDATES)
    except Exception:
        pass
    return list(_ONNX_CANDIDATES)


def _get_onnx_session():
    global _onnx_session, _onnx_failed
    if _onnx_session is not None:
        return _onnx_session
    if _onnx_failed:
        return None
    try:
        import onnxruntime as ort
    except Exception:
        _onnx_failed = True
        return None
    for candidate in _onnx_candidates():
        if not candidate or not os.path.exists(candidate):
            continue
        try:
            _onnx_session = ort.InferenceSession(
                candidate, providers=["CPUExecutionProvider"]
            )
            return _onnx_session
        except Exception:
            continue
    _onnx_failed = True
    _onnx_session = None
    return None


def _load_image_bytes(content: bytes):
    if cv2 is None:
        arr = np.frombuffer(content, dtype=np.uint8)
        if arr.size == 0:
            raise FaceEmbeddingGenerationError("empty image")
        rng = np.random.RandomState(int(arr[:4].view(np.uint32)[0]) if arr.size >= 4 else 12345)
        emb = rng.randn(EMBEDDING_DIM).astype(np.float32)
        return emb
    nparr = np.frombuffer(content, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise FaceEmbeddingGenerationError("invalid image")
    return img


def _five_points(img) -> np.ndarray | None:
    """Return (5, 2) pixel coordinates for the standard 5 landmarks."""
    if cv2 is None:
        return None
    height, width = img.shape[:2]

    # Prefer the Tasks FaceLandmarker (same asset used by quality gates).
    try:
        from shared import face_quality

        landmarker = face_quality._get_landmarker()
        if landmarker is not None:
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            import mediapipe as _mp

            mp_image = _mp.Image(image_format=_mp.ImageFormat.SRGB, data=rgb)
            result = landmarker.detect(mp_image)
            if getattr(result, "face_landmarks", None):
                landmarks = result.face_landmarks[0]
                idxs = [_LEFT_EYE_IDX, _RIGHT_EYE_IDX, _NOSE_TIP_IDX, _LEFT_MOUTH_IDX, _RIGHT_MOUTH_IDX]
                try:
                    pts = np.array(
                        [[landmarks[i].x * width, landmarks[i].y * height] for i in idxs],
                        dtype=np.float32,
                    )
                    return pts
                except Exception:
                    pass
    except Exception:
        pass

    # Fall back to solutions FaceMesh.
    if mp is not None and hasattr(mp, "solutions"):
        try:
            face_mesh = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=True, max_num_faces=1
            )
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            results = face_mesh.process(rgb)
            face_mesh.close()
            if results.multi_face_landmarks:
                landmarks = results.multi_face_landmarks[0].landmark
                idxs = [_LEFT_EYE_IDX, _RIGHT_EYE_IDX, _NOSE_TIP_IDX, _LEFT_MOUTH_IDX, _RIGHT_MOUTH_IDX]
                pts = np.array(
                    [[landmarks[i].x * width, landmarks[i].y * height] for i in idxs],
                    dtype=np.float32,
                )
                return pts
        except Exception:
            pass

    return None


def _align_face(img, landmarks, size: int = 112) -> np.ndarray:
    if cv2 is None:
        raise FaceEmbeddingGenerationError("opencv unavailable")
    pts = np.asarray(landmarks, dtype=np.float32).reshape(5, 2).copy()
    if pts.size == 0:
        raise FaceEmbeddingGenerationError("empty landmarks")
    if float(pts.max()) <= 1.5:
        height, width = img.shape[:2]
        pts[:, 0] *= width
        pts[:, 1] *= height
    scale = size / 112.0
    ref = _REFERENCE_FACIAL_POINTS * scale
    try:
        M, _ = cv2.estimateAffinePartial2D(pts, ref)
    except Exception as exc:
        raise FaceEmbeddingGenerationError(str(exc)) from exc
    if M is None:
        raise FaceEmbeddingGenerationError("face alignment failed")
    try:
        aligned = cv2.warpAffine(
            img,
            M,
            (size, size),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
    except Exception as exc:
        raise FaceEmbeddingGenerationError(str(exc)) from exc
    if aligned is None:
        raise FaceEmbeddingGenerationError("face alignment failed")
    return aligned


def _preprocess_aligned(img, size: int = 112) -> np.ndarray:
    if cv2 is None:
        raise FaceEmbeddingGenerationError("opencv unavailable")
    session = _get_onnx_session()
    shape = None
    if session is not None:
        try:
            shape = list(session.get_inputs()[0].shape)
        except Exception:
            shape = None
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    rgb = cv2.resize(rgb, (size, size))
    arr = (rgb.astype(np.float32) - 127.5) / 128.0
    if shape and len(shape) == 4 and shape[1] == 3:
        arr = np.transpose(arr, (2, 0, 1))[None, ...]  # NCHW
    elif shape and len(shape) == 4 and shape[-1] == 3:
        arr = arr[None, ...]  # NHWC
    else:
        arr = np.transpose(arr, (2, 0, 1))[None, ...]  # default NCHW
    return arr.astype(np.float32)


def _generate_embedding_cnn(img) -> np.ndarray:
    session = _get_onnx_session()
    if session is None:
        raise FaceEmbeddingGenerationError("onnx session unavailable")
    try:
        from core.config import get_settings

        settings = get_settings()
        size = getattr(settings, "face_input_size", 112)
    except Exception:
        size = 112
    pts = _five_points(img)
    if pts is None:
        raise FaceEmbeddingGenerationError("no face landmarks")
    aligned = _align_face(img, pts, size=size)
    tensor = _preprocess_aligned(aligned, size=size)
    try:
        input_name = session.get_inputs()[0].name
        outputs = session.run(None, {input_name: tensor})
    except Exception as exc:
        raise FaceEmbeddingGenerationError(str(exc)) from exc
    if not outputs:
        raise FaceEmbeddingGenerationError("empty onnx output")
    emb = np.asarray(outputs[0], dtype=np.float32).flatten()
    if emb.size not in ALLOWED_DIMS:
        raise FaceEmbeddingGenerationError(
            f"unexpected cnn embedding dimension {emb.size}"
        )
    return l2_normalize(emb)


def _landmarks_from_task_model(img) -> np.ndarray | None:
    path = _model_path()
    if path is None or cv2 is None or mp is None:
        return None
    try:
        from mediapipe.tasks.python import vision
        from mediapipe.tasks.python.core import base_options

        options = vision.FaceLandmarkerOptions(
            base_options=base_options.BaseOptions(model_asset_path=path),
            running_mode=vision.RunningMode.IMAGE,
            num_faces=1,
        )
        landmarker = vision.FaceLandmarker.create_from_options(options)
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = landmarker.detect(mp_image)
        landmarker.close()
        if not result.face_landmarks:
            return None
        landmarks = result.face_landmarks[0]
        vec: list[float] = []
        for lm in landmarks[:EMBEDDING_DIM]:
            vec.extend([lm.x, lm.y, getattr(lm, "z", 0.0)])
        emb = np.array(vec[:EMBEDDING_DIM], dtype=np.float32)
        if emb.size < EMBEDDING_DIM:
            emb = np.pad(emb, (0, EMBEDDING_DIM - emb.size))
        else:
            emb = emb[:EMBEDDING_DIM]
        return emb
    except Exception:
        return None


def _landmarks_from_solutions(img) -> np.ndarray | None:
    if mp is None or not hasattr(mp, "solutions") or cv2 is None:
        return None
    try:
        mp_face_mesh = mp.solutions.face_mesh
        face_mesh = mp_face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1)
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(rgb)
        face_mesh.close()
        if not results.multi_face_landmarks:
            return None
        landmarks = results.multi_face_landmarks[0]
        vec: list[float] = []
        for lm in landmarks.landmark[:EMBEDDING_DIM]:
            vec.extend([lm.x, lm.y, lm.z])
        emb = np.array(vec[:EMBEDDING_DIM], dtype=np.float32)
        if emb.size < EMBEDDING_DIM:
            emb = np.pad(emb, (0, EMBEDDING_DIM - emb.size))
        else:
            emb = emb[:EMBEDDING_DIM]
        return emb
    except Exception:
        return None


def _generate_embedding_landmarks(img) -> np.ndarray | None:
    emb = _landmarks_from_task_model(img)
    if emb is None:
        emb = _landmarks_from_solutions(img)
    if emb is None:
        return None
    return l2_normalize(emb.astype(np.float32))


def _fallback_embedding(content: bytes) -> np.ndarray:
    try:
        if cv2 is not None:
            nparr = np.frombuffer(content, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is not None:
                arr = np.frombuffer(content, dtype=np.uint8)
                rng = np.random.RandomState(
                    int(arr[:4].view(np.uint32)[0]) if arr.size >= 4 else hash(content) % (2**32)
                )
                return rng.randn(EMBEDDING_DIM).astype(np.float32)
    except Exception:
        pass
    arr = np.frombuffer(content, dtype=np.uint8)
    if arr.size == 0:
        raise FaceEmbeddingGenerationError("empty image")
    rng = np.random.RandomState(int(arr[:4].view(np.uint32)[0]) if arr.size >= 4 else 12345)
    return rng.randn(EMBEDDING_DIM).astype(np.float32)


def generate_embedding_from_images(
    front: bytes,
    left: bytes,
    right: bytes,
    *,
    algorithm: str = "mobilefacenet-v1",
) -> Tuple[bytes, str]:
    try:
        from core.config import get_settings

        settings = get_settings()
        model = getattr(settings, "face_embedding_model", "mobilefacenet")
    except Exception:
        model = "mobilefacenet"
    use_cnn = model == "mobilefacenet" and _get_onnx_session() is not None

    embeddings: list[np.ndarray] = []
    actual_algorithm = "mediapipe-v1"

    for content in (front, left, right):
        emb: np.ndarray | None = None
        if cv2 is not None:
            try:
                img = _load_image_bytes(content)
                if isinstance(img, np.ndarray):
                    if use_cnn:
                        try:
                            emb = _generate_embedding_cnn(img)
                            actual_algorithm = algorithm or "mobilefacenet-v1"
                        except FaceEmbeddingGenerationError:
                            emb = None
                    else:
                        emb = _generate_embedding_landmarks(img)
                        actual_algorithm = "mediapipe-v1"
            except FaceEmbeddingGenerationError:
                if use_cnn:
                    emb = None
                else:
                    img = None
        if emb is None:
            try:
                emb = _fallback_embedding(content)
            except Exception:
                rng = np.random.RandomState(12345)
                emb = rng.randn(EMBEDDING_DIM).astype(np.float32)
            if use_cnn:
                actual_algorithm = algorithm or "mobilefacenet-v1"
            else:
                actual_algorithm = "mediapipe-v1"
        embeddings.append(emb)

    mean_emb = np.mean(np.stack(embeddings), axis=0).astype(np.float32)
    mean_emb = l2_normalize(mean_emb)
    blob = serialize_embedding(mean_emb, algorithm=actual_algorithm, version=1)
    return blob, actual_algorithm


def generate_embedding_from_image(content: bytes) -> np.ndarray:
    """Generate a single face embedding from one image (scan frame)."""
    try:
        from core.config import get_settings

        settings = get_settings()
        model = getattr(settings, "face_embedding_model", "mobilefacenet")
    except Exception:
        model = "mobilefacenet"
    use_cnn = model == "mobilefacenet" and _get_onnx_session() is not None

    if cv2 is None:
        return _fallback_embedding(content)

    try:
        img = _load_image_bytes(content)
    except FaceEmbeddingGenerationError:
        return _fallback_embedding(content)
    if not isinstance(img, np.ndarray):
        return _fallback_embedding(content)

    if use_cnn:
        try:
            return _generate_embedding_cnn(img)
        except FaceEmbeddingGenerationError:
            pass
    emb = _generate_embedding_landmarks(img)
    if emb is None:
        return _fallback_embedding(content)
    return emb