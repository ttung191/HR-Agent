from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache

from app.core.config import get_settings

TOKEN_RE = re.compile(r"[a-zA-ZÀ-ỹ0-9+#._/-]+")


class HashingEmbeddingBackend:
    def __init__(self, dimension: int = 384):
        self.dimension = dimension
        self.model_name = f"hashing-{dimension}"

    def encode(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dimension
            tokens = TOKEN_RE.findall((text or "").lower())
            if not tokens:
                vectors.append(vector)
                continue
            for token in tokens:
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                idx = int.from_bytes(digest[:4], "big") % self.dimension
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                weight = 1.0 + min(len(token), 12) / 12.0
                vector[idx] += sign * weight
            norm = math.sqrt(sum(item * item for item in vector)) or 1.0
            vectors.append([item / norm for item in vector])
        return vectors


class SentenceTransformerBackend:
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        probe = self.model.encode(["ping"], normalize_embeddings=True)
        self.dimension = len(probe[0])

    def encode(self, texts: list[str]) -> list[list[float]]:
        result = self.model.encode(texts, normalize_embeddings=True)
        return [row.tolist() for row in result]


@lru_cache
def get_embedding_backend():
    settings = get_settings()
    if settings.embedding_backend == "hashing":
        return HashingEmbeddingBackend(dimension=settings.embedding_dimension)

    if settings.embedding_backend == "sentence-transformers":
        return SentenceTransformerBackend(settings.embedding_model_name)

    try:
        return SentenceTransformerBackend(settings.embedding_model_name)
    except Exception:
        return HashingEmbeddingBackend(dimension=settings.embedding_dimension)
