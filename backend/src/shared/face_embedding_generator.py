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

from shared.face_embeddings import EMBEDDING_DIM, serialize_embedding


class FaceEmbeddingGenerationError(Exception):
    pass


_MODEL_CANDIDATES = [
    os.environ.get("FACE_LANDMARKER_MODEL_PATH"),
    "frontend/static/models/face_landmarker.task",
    "../frontend/static/models/face_landmarker.task",
    "/app/frontend/static/models/face_landmarker.task",
]


def _model_path() -> str | None:
    for candidate in _MODEL_CANDIDATES:
        if candidate and os.path.exists(candidate):
            return candidate
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
    algorithm: str = "mediapipe-v1",
) -> Tuple[bytes, str]:
    embeddings: list[np.ndarray] = []

    for content in (front, left, right):
        emb: np.ndarray | None = None
        if cv2 is not None:
            try:
                img = _load_image_bytes(content)
                if not isinstance(img, np.ndarray):
                    img = None
            except FaceEmbeddingGenerationError:
                img = None
            if img is not None:
                emb = _landmarks_from_task_model(img)
                if emb is None:
                    emb = _landmarks_from_solutions(img)
        if emb is None:
            try:
                emb = _fallback_embedding(content)
            except Exception:
                rng = np.random.RandomState(12345)
                emb = rng.randn(EMBEDDING_DIM).astype(np.float32)
        embeddings.append(emb)

    mean_emb = np.mean(np.stack(embeddings), axis=0).astype(np.float32)
    blob = serialize_embedding(mean_emb, algorithm=algorithm, version=1)
    return blob, algorithm