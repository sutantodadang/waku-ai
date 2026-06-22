"""Embeddings for hybrid catalog retrieval — OpenAI-compatible or Ollama."""
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


def _embed_openai(texts: list[str]) -> Optional[list[list[float]]]:
    if not settings.openai_api_key:
        return None
    url = f"{settings.openai_base_url.rstrip('/')}/embeddings"
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                url,
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={"model": settings.embed_model, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()
            return [row["embedding"] for row in data["data"]]
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        logger.error("OpenAI embeddings failed: %s", exc)
        return None


def _embed_ollama(texts: list[str]) -> Optional[list[list[float]]]:
    url = f"{settings.ollama_base_url.rstrip('/')}/api/embeddings"
    vectors: list[list[float]] = []
    try:
        with httpx.Client(timeout=60.0) as client:
            for text in texts:
                resp = client.post(url, json={"model": settings.ollama_embed_model, "prompt": text})
                resp.raise_for_status()
                vectors.append(resp.json()["embedding"])
        return vectors
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        logger.error("Ollama embeddings failed: %s", exc)
        return None


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts. Raises RuntimeError if the provider is unavailable."""
    if not texts:
        return []
    vectors = _embed_openai(texts) if settings.use_openai else _embed_ollama(texts)
    if vectors is None:
        raise RuntimeError("Embedding provider unavailable")
    return vectors


if __name__ == "__main__":
    assert abs(cosine([1.0, 2.0], [1.0, 2.0]) - 1.0) < 1e-9
    assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0
    print("embeddings self-check OK")
