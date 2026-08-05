"""Vector storage.

:class:`VectorStore` is the pluggable interface; :class:`InMemoryVectorStore` is
the dependency-light reference implementation. For real workloads swap in
Qdrant / Chroma / Weaviate / Milvus behind the same three methods.

Search is a dense scan over all vectors. With numpy installed (the normal
case) the vectors live in one ``float32`` matrix and a query is a single
matrix-vector product — ~milliseconds for hundreds of thousands of documents
and ~8x less memory than Python lists. Without numpy the same scan falls back
to pure Python (correct, but O(seconds) at large scale). All embedders
L2-normalise their vectors, so the dot product IS the cosine similarity; the
zero vector (empty text) scores 0 either way, exactly as ``cosine`` does.
"""

from __future__ import annotations

from array import array
from typing import Optional, Protocol, Sequence

from ..models import Document
from .embeddings import EmbeddingProvider, cosine

try:  # numpy is the fast path; the pure-Python fallback keeps the package runnable without it
    import numpy as _np
except ImportError:  # pragma: no cover - exercised via the fallback test
    _np = None


def dense_topk(
    vecs: Sequence[Sequence[float]],
    docs: Sequence[Document],
    query_vec: Sequence[float],
    k: int,
    matrix=None,
) -> tuple[list[tuple[Document, float]], object]:
    """Top-k documents by dot product (== cosine for normalised vectors).

    Returns ``(results, matrix)`` where ``matrix`` is the numpy matrix used —
    pass it back in on the next call to avoid rebuilding it. ``matrix`` is
    ``None`` on the pure-Python path.
    """
    if not docs:
        return [], matrix
    k = min(k, len(docs))
    if _np is not None:
        if matrix is None or getattr(matrix, "shape", (0,))[0] != len(docs):
            matrix = _np.asarray(vecs, dtype=_np.float32)
        q = _np.asarray(query_vec, dtype=_np.float32)
        scores = matrix @ q
        top = _np.argpartition(scores, -k)[-k:]
        top = top[_np.argsort(scores[top])[::-1]]
        return [(docs[i], float(scores[i])) for i in top], matrix
    scored = [(doc, cosine(query_vec, vec)) for doc, vec in zip(docs, vecs)]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:k], None


class VectorStore(Protocol):
    def add(self, docs: list[Document]) -> None:
        ...

    def search(self, query: str, *, k: int = 5) -> list[tuple[Document, float]]:
        ...

    def __len__(self) -> int:
        ...


class InMemoryVectorStore:
    """Dense cosine search over in-memory embeddings.

    Vectors are held compactly (``array('f')``) and scanned via numpy when
    available (see module docstring). Correct and simple; swap in an ANN index
    for very large corpora.
    """

    def __init__(self, embedder: EmbeddingProvider) -> None:
        self.embedder = embedder
        self._docs: list[Document] = []
        self._vecs: list[array] = []
        self._ids: set[str] = set()
        self._matrix = None  # numpy cache, rebuilt after adds

    def add(self, docs: list[Document]) -> None:
        for doc in docs:
            if doc.id in self._ids:
                continue
            self._ids.add(doc.id)
            self._docs.append(doc)
            self._vecs.append(array("f", self.embedder.embed(doc.text)))
        self._matrix = None

    def search(self, query: str, *, k: int = 5) -> list[tuple[Document, float]]:
        qv = self.embedder.embed(query)
        results, self._matrix = dense_topk(self._vecs, self._docs, qv, k, self._matrix)
        return results

    def __len__(self) -> int:
        return len(self._docs)
