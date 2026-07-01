"""Embeddings for hybrid catalog retrieval — HuggingFace Inference only.

Pinned to a single provider on purpose: mixing providers/models yields vectors
in incompatible spaces (even at equal dims), which silently corrupts cosine
similarity. If HF is unavailable, embed_texts raises and the backend degrades
to keyword-only retrieval (non-blocking)."""
import logging
import math
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity. Returns 0.0 for a zero vector or length mismatch."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _embed_hf(texts: list[str]) -> Optional[list[list[float]]]:
    """HuggingFace Inference feature-extraction. Returns one vector per text
    (sentence-transformers models pool to 2D: list[list[float]])."""
    if not settings.hf_api_key:
        return None
    url = (f"{settings.hf_embed_base_url.rstrip('/')}/hf-inference/models/"
           f"{settings.hf_embed_model}/pipeline/feature-extraction")
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                url,
                headers={"Authorization": f"Bearer {settings.hf_api_key}"},
                json={"inputs": texts, "options": {"wait_for_model": True}},
            )
            resp.raise_for_status()
            data = resp.json()
            # sentence-transformers → 2D. Guard against a single-text 1D response.
            if data and isinstance(data[0], (int, float)):
                data = [data]
            return data
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        logger.error("HuggingFace embeddings failed: %s", exc)
        return None


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts via HuggingFace. Raises RuntimeError if unavailable.

    No cross-provider fallback — see module docstring."""
    if not texts:
        return []
    vectors = _embed_hf(texts)
    if vectors is None:
        raise RuntimeError("Embedding provider unavailable (HuggingFace)")
    return vectors


if __name__ == "__main__":
    assert abs(cosine([1.0, 2.0], [1.0, 2.0]) - 1.0) < 1e-9
    assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0
    print("embeddings self-check OK")
