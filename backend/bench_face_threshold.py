"""Threshold tuning helper for MobileFaceNet/SFace embeddings.

Usage:
    PYTHONPATH=src python bench_face_threshold.py --same-dir ./same --diff-dir ./diff

Each directory should contain face images (one face per image). The script
computes embeddings with the same server-side pipeline used for enrollment
and reports cosine-similarity statistics for same-person vs different-person
pairs, plus a suggested threshold.
"""

from __future__ import annotations

import argparse
import itertools
import os
from pathlib import Path

import numpy as np

from shared.face_embedding_generator import generate_embedding_from_image
from shared.face_embeddings import cosine_similarity


def _embeddings(directory: Path) -> list[np.ndarray]:
    out: list[np.ndarray] = []
    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        data = path.read_bytes()
        try:
            emb = generate_embedding_from_image(data)
        except Exception as exc:  # pragma: no cover - diagnostic only
            print(f"skip {path.name}: {exc}")
            continue
        out.append(emb)
    return out


def _pair_scores(embeddings: list[np.ndarray]) -> list[float]:
    scores = []
    for a, b in itertools.combinations(embeddings, 2):
        scores.append(cosine_similarity(a, b))
    return scores


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--same-dir", type=Path, required=True)
    parser.add_argument("--diff-dir", type=Path, required=True)
    args = parser.parse_args()

    same_embs = _embeddings(args.same_dir)
    diff_embs = _embeddings(args.diff_dir)

    if len(same_embs) < 2 or len(diff_embs) < 2:
        raise SystemExit("Need at least 2 images in each directory")

    same_scores = _pair_scores(same_embs)
    diff_scores = _pair_scores(diff_embs)

    print("same-person pairs:", len(same_scores))
    print(f"  min={min(same_scores):.4f} mean={np.mean(same_scores):.4f} max={max(same_scores):.4f}")
    print("different-person pairs:", len(diff_scores))
    print(f"  min={min(diff_scores):.4f} mean={np.mean(diff_scores):.4f} max={max(diff_scores):.4f}")

    suggested = (min(same_scores) + max(diff_scores)) / 2.0
    print(f"suggested FACE_MATCH_THRESHOLD (midpoint): {suggested:.4f}")
    print("review band suggestion: set FACE_REVIEW_BAND_LOW ~0.05 below threshold")


if __name__ == "__main__":
    os.environ.setdefault("DEBUG", "true")
    os.environ.setdefault("JWT_SECRET", "test-secret-0123456789abcdef-0123456789")
    main()