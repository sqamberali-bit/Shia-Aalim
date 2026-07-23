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
from collections import Counter
from typing import Iterable, Optional, Protocol, Sequence, runtime_checkable

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


def _features(text: str, *, use_char_ngrams: bool = True) -> list[str]:
    """Whole-word tokens (prefixed) plus character tri-grams — the shared feature
    space for the hashing embedders. Word features are prefixed so they never
    collide with a char-trigram of the same string."""
    feats = [f"w:{t}" for t in tokens(text)]
    if use_char_ngrams:
        feats += [f"c:{g}" for g in _char_ngrams(text, 3)]
    return feats


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


class TfidfHashingEmbedder:
    """IDF-weighted feature-hashing embedder — a dependency-free, corpus-fitted
    upgrade over :class:`HashingEmbedder`.

    Rare, discriminative features (e.g. "purification", the trigram "kin") get
    high weight; ubiquitous ones are damped. Still lexical (not semantic), but a
    large, measurable retrieval improvement over blind hashing — and it runs
    anywhere with no model download. Call :meth:`fit` on the corpus first
    (``build_index`` does this automatically); unfitted, it degrades gracefully
    to unit IDF.
    """

    def __init__(self, dim: int = 2048, *, use_char_ngrams: bool = True) -> None:
        if dim <= 0:
            raise ValueError("dim must be positive")
        self.dim = dim
        self.use_char_ngrams = use_char_ngrams
        self._idf: dict[str, float] = {}
        self._default_idf: float = 1.0
        self.fitted: bool = False

    def fit(self, texts: Iterable[str]) -> "TfidfHashingEmbedder":
        df: Counter[str] = Counter()
        n = 0
        for text in texts:
            n += 1
            for feat in set(_features(text, use_char_ngrams=self.use_char_ngrams)):
                df[feat] += 1
        if n == 0:
            return self
        self._idf = {f: math.log((n + 1) / (d + 1)) + 1.0 for f, d in df.items()}
        # An unseen feature is maximally rare → highest idf.
        self._default_idf = math.log((n + 1) / 1) + 1.0
        self.fitted = True
        return self

    def _bucket(self, feature: str) -> tuple[int, float]:
        h = hashlib.md5(feature.encode("utf-8")).digest()
        idx = int.from_bytes(h[:4], "big") % self.dim
        sign = 1.0 if h[4] & 1 else -1.0
        return idx, sign

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        counts = Counter(_features(text, use_char_ngrams=self.use_char_ngrams))
        for feat, tf in counts.items():
            idf = self._idf.get(feat, self._default_idf) if self.fitted else 1.0
            weight = (1.0 + math.log(tf)) * idf  # sublinear tf × idf
            idx, sign = self._bucket(feat)
            vec[idx] += sign * weight
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class SentenceTransformerEmbedder:
    """Semantic embedder backed by ``sentence-transformers`` (BGE-M3, E5, …).

    This is the production retrieval upgrade: true semantic similarity instead of
    lexical overlap. It needs the model weights, which are downloaded from the
    HuggingFace Hub on first use (or supplied via a local path / cache), so it
    runs wherever the Hub — or a pre-downloaded model — is reachable. Everything
    is imported lazily; importing this module never requires torch.

    Example::

        emb = SentenceTransformerEmbedder("BAAI/bge-m3")
        store = InMemoryVectorStore(emb)   # or PersistentVectorStore

    ``BAAI/bge-m3`` is a strong multilingual (incl. Arabic) default; benchmark it
    against E5-multilingual / Jina-v3 with ``scripts/benchmark_retrieval.py``.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        *,
        device: Optional[str] = None,
        normalize: bool = True,
        batch_size: int = 32,
        query_prefix: str = "",
        cache_folder: Optional[str] = None,
    ) -> None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional heavy dep
            raise RuntimeError(
                "SentenceTransformerEmbedder needs sentence-transformers + a model "
                "download — `pip install shia-aalim[embeddings]` and run where the "
                "HuggingFace Hub (or a local model path) is reachable."
            ) from exc
        self.model_name = model_name
        self._model = SentenceTransformer(model_name, device=device, cache_folder=cache_folder)
        self.dim = int(self._model.get_sentence_embedding_dimension())
        self.normalize = normalize
        self.batch_size = batch_size
        self.query_prefix = query_prefix  # some models want an instruction prefix

    def embed(self, text: str) -> list[float]:
        v = self._model.encode(
            self.query_prefix + text, normalize_embeddings=self.normalize
        )
        return v.tolist()

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        vs = self._model.encode(
            list(texts), normalize_embeddings=self.normalize, batch_size=self.batch_size
        )
        return [v.tolist() for v in vs]


def fit_if_needed(embedder: object, texts: Iterable[str]) -> None:
    """Fit an embedder on the corpus if it exposes an (unfitted) ``fit`` method.

    Lets index builders stay embedder-agnostic: TF-IDF learns its IDF here;
    stateless embedders (hashing, sentence-transformers) are left untouched.
    """
    fit = getattr(embedder, "fit", None)
    if callable(fit) and not getattr(embedder, "fitted", False):
        fit(texts)


def make_embedder(spec: str = "tfidf", *, dim: int = 2048):
    """Build an embedder from a short spec string (for config/CLI selection).

    * ``"hashing"`` — the dependency-free baseline (unweighted feature hashing).
    * ``"tfidf"`` — dependency-free IDF-weighted hashing (the runnable default).
    * ``"st:<model>"`` — semantic, e.g. ``"st:BAAI/bge-m3"`` (needs the extras +
      a reachable model). ``"sentence-transformers:<model>"`` also works.
    """
    spec = spec.strip()
    if spec in ("hashing", "hash"):
        return HashingEmbedder(dim=dim)
    if spec in ("tfidf", "tf-idf"):
        return TfidfHashingEmbedder(dim=dim)
    for prefix in ("st:", "sentence-transformers:"):
        if spec.startswith(prefix):
            return SentenceTransformerEmbedder(spec[len(prefix):])
    raise ValueError(
        f"unknown embedder spec: {spec!r} "
        "(expected 'hashing', 'tfidf', or 'st:<model>')"
    )
