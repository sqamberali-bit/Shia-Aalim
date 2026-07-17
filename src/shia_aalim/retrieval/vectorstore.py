"""Vector storage.

:class:`VectorStore` is the pluggable interface; :class:`InMemoryVectorStore` is
a dependency-free brute-force reference implementation. For real workloads swap
in Qdrant / Chroma / Weaviate / Milvus behind the same three methods.
"""

from __future__ import annotations

from typing import Protocol

from ..models import Document
from .embeddings import EmbeddingProvider, cosine


class VectorStore(Protocol):
    def add(self, docs: list[Document]) -> None:
        ...

    def search(self, query: str, *, k: int = 5) -> list[tuple[Document, float]]:
        ...

    def __len__(self) -> int:
        ...


class InMemoryVectorStore:
    """Brute-force cosine search over in-memory embeddings.

    Correct and simple; O(N) per query. Fine for tens of thousands of chunks
    and for tests. Replace with an ANN index for large corpora.
    """

    def __init__(self, embedder: EmbeddingProvider) -> None:
        self.embedder = embedder
        self._docs: list[Document] = []
        self._vecs: list[list[float]] = []
        self._ids: set[str] = set()

    def add(self, docs: list[Document]) -> None:
        for doc in docs:
            if doc.id in self._ids:
                continue
            self._ids.add(doc.id)
            self._docs.append(doc)
            self._vecs.append(self.embedder.embed(doc.text))

    def search(self, query: str, *, k: int = 5) -> list[tuple[Document, float]]:
        if not self._docs:
            return []
        qv = self.embedder.embed(query)
        scored = [(doc, cosine(qv, vec)) for doc, vec in zip(self._docs, self._vecs)]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]

    def __len__(self) -> int:
        return len(self._docs)
