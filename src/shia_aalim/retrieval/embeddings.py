"""Embedding providers.

A tiny :class:`EmbeddingProvider` protocol lets any backend plug in. The default
:class:`HashingEmbedder` is a deterministic, dependency-free feature-hashing
embedder over Arabic-normalised word + character n-grams. It is intentionally
modest — good enough to make the retrieval pipeline work, be tested, and serve
as a baseline — but production deployments should swap in a real semantic model
(BGE-M3, E5, Jina, Nomic, …) which share this same interface.

Benchmark hooks for those models live in ``docs/architecture.md`` and
``shia_aalim.evaluation``.
"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol, Sequence, runtime_checkable

from ..ingestion.normalize import normalize_for_search, tokens


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Anything that can turn text into a fixed-length vector."""

    dim: int

    def embed(self, text: str) -> list[float]:
        ...

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        ...


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity of two equal-length vectors (0.0 if either is zero)."""
    if len(a) != len(b):
        raise ValueError(f"vector length mismatch: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _char_ngrams(text: str, n: int = 3) -> list[str]:
    text = normalize_for_search(text).replace(" ", "_")
    if len(text) < n:
        return [text] if text else []
    return [text[i : i + n] for i in range(len(text) - n + 1)]


class HashingEmbedder:
    """Deterministic feature-hashing embedder (no dependencies, no training).

    Combines whole-word tokens and character tri-grams so it is partly robust to
    morphological variation in Arabic. Vectors are L2-normalised.
    """

    def __init__(self, dim: int = 512, *, use_char_ngrams: bool = True) -> None:
        if dim <= 0:
            raise ValueError("dim must be positive")
        self.dim = dim
        self.use_char_ngrams = use_char_ngrams

    def _bucket(self, feature: str) -> tuple[int, float]:
        h = hashlib.md5(feature.encode("utf-8")).digest()
        idx = int.from_bytes(h[:4], "big") % self.dim
        sign = 1.0 if h[4] & 1 else -1.0  # signed hashing reduces collisions
        return idx, sign

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        features = list(tokens(text))
        if self.use_char_ngrams:
            features += _char_ngrams(text, 3)
        for feat in features:
            idx, sign = self._bucket(feat)
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]
