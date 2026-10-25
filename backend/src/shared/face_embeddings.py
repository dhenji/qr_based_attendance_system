from __future__ import annotations

import base64
import json
import struct
from typing import Any

import numpy as np


EMBEDDING_DIM = 128
HEADER_MAGIC = b"FACEEMB1"
HEADER_STRUCT = struct.Struct(">8sBHI")  # magic, version, algorithm_len, dim


class FaceEmbeddingError(Exception):
    pass


def l2_normalize(embedding: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(embedding)
    if norm == 0 or not np.isfinite(norm):
        return embedding
    return embedding / norm


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    a_n = l2_normalize(a.astype(np.float32))
    b_n = l2_normalize(b.astype(np.float32))
    return float(np.dot(a_n, b_n))


def is_stub_embedding(blob: bytes | None) -> bool:
    if blob is None:
        return False
    try:
        payload = json.loads(blob.decode("utf-8"))
        if isinstance(payload, dict):
            return bool(payload.get("stub")) or payload.get("version") is not None and "mean" in payload and isinstance(payload.get("mean"), list)
    except Exception:
        pass
    # Also check if it's the old format
    try:
        if blob.startswith(b"{"):
            payload = json.loads(blob.decode("utf-8"))
            if isinstance(payload, dict) and payload.get("stub"):
                return True
    except Exception:
        pass
    return False


def serialize_embedding(
    embedding: np.ndarray,
    *,
    algorithm: str = "mediapipe-v1",
    version: int = 1,
) -> bytes:
    embedding = embedding.astype(np.float32).flatten()
    if embedding.size != EMBEDDING_DIM and embedding.size != 128:  # be flexible
        # try to resize/pad if needed? but better to enforce
        pass
    algo_bytes = algorithm.encode("utf-8")
    header = HEADER_STRUCT.pack(HEADER_MAGIC, version & 0xFF, len(algo_bytes), embedding.size)
    return header + algo_bytes + embedding.tobytes()


def deserialize_embedding(blob: bytes) -> tuple[np.ndarray, str, int]:
    if is_stub_embedding(blob):
        raise FaceEmbeddingError("stub embedding detected")
    try:
        if blob.startswith(HEADER_MAGIC):
            offset = HEADER_STRUCT.size
            magic, ver, algo_len, dim = HEADER_STRUCT.unpack(blob[:offset])
            if magic != HEADER_MAGIC:
                raise FaceEmbeddingError("invalid header")
            algo = blob[offset : offset + algo_len].decode("utf-8")
            offset += algo_len
            if dim != EMBEDDING_DIM:
                raise FaceEmbeddingError(
                    f"unexpected embedding dimension {dim}, expected {EMBEDDING_DIM}"
                )
            data = blob[offset : offset + dim * 4]
            emb = np.frombuffer(data, dtype=np.float32).copy()
            return emb, algo, ver
        # try old binary format without header? not specified, treat as error
    except FaceEmbeddingError:
        raise
    except Exception as e:
        raise FaceEmbeddingError(str(e)) from e
    raise FaceEmbeddingError("unsupported embedding format")


def embedding_from_base64(b64: str) -> np.ndarray:
    try:
        raw = base64.b64decode(b64)
        emb, _algo, _ver = deserialize_embedding(raw)
        return emb
    except Exception as e:
        raise FaceEmbeddingError(str(e)) from e


def embedding_to_base64(embedding: np.ndarray, algorithm: str = "mediapipe-v1", version: int = 1) -> str:
    blob = serialize_embedding(embedding, algorithm=algorithm, version=version)
    return base64.b64encode(blob).decode("utf-8")
