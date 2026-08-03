from __future__ import annotations

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float32]
EmbeddingInput = list[float] | FloatArray


def l2_normalize_vector(vector: EmbeddingInput) -> FloatArray:
    array = np.asarray(vector, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(array))
    return array if norm <= 0 else array / norm


def cosine_similarity(vector_a: EmbeddingInput, vector_b: EmbeddingInput) -> float:
    a = l2_normalize_vector(vector_a)
    b = l2_normalize_vector(vector_b)
    if a.shape != b.shape:
        raise ValueError(f"embedding dimensions differ: {a.shape[0]} != {b.shape[0]}")
    return float(np.dot(a, b))


__all__ = ["cosine_similarity", "l2_normalize_vector"]
