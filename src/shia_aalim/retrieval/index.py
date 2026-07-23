"""Persistent vector store — embed once, reuse across runs.

Re-embedding a large corpus (the knowledge base is ~101k documents) on every
process start is wasteful, and with a semantic model it is the dominant cost.
:class:`PersistentVectorStore` caches each document's vector on disk keyed by the
document id, so a second run over the same corpus + embedder does **no**
embedding at all.

It implements the same ``add`` / ``search`` / ``__len__`` surface as
:class:`~shia_aalim.retrieval.vectorstore.InMemoryVectorStore`, so it drops into
:class:`~shia_aalim.retrieval.retriever.Retriever` unchanged. Search is
brute-force cosine (correct and simple); for very large corpora move to an ANN
index / vector DB — the interface is identical.

The on-disk cache stores only ``{id: vector}`` plus an embedder *signature*; if
the signature changes (different model/dim), the cache is ignored and rebuilt,
so stale vectors can never be silently mixed with a new embedder. Vectors are
stored compactly via ``array('f', …)``.
"""

from __future__ import annotations

import pickle
from array import array
from pathlib import Path
from typing import Optional

from ..models import Document
from .embeddings import EmbeddingProvider, cosine, fit_if_needed


def embedder_signature(embedder: EmbeddingProvider) -> str:
    """Identity of an embedder for cache invalidation (class + model + dim)."""
    model = getattr(embedder, "model_name", "")
    return f"{type(embedder).__name__}:{model}:{getattr(embedder, 'dim', '?')}"


class PersistentVectorStore:
    def __init__(self, embedder: EmbeddingProvider, cache_path: str | Path) -> None:
        self.embedder = embedder
        self.cache_path = Path(cache_path)
        self._docs: list[Document] = []
        self._vecs: list[list[float]] = []
        self._ids: set[str] = set()
        self._cache: dict[str, list[float]] = self._load_cache()

    def _load_cache(self) -> dict[str, list[float]]:
        if not self.cache_path.exists():
            return {}
        try:
            blob = pickle.loads(self.cache_path.read_bytes())
        except Exception:  # noqa: BLE001 - corrupt/old cache => rebuild
            return {}
        if blob.get("signature") != embedder_signature(self.embedder):
            return {}  # different embedder: ignore stale vectors
        return {k: list(v) for k, v in blob.get("vectors", {}).items()}

    def add(self, docs: list[Document]) -> None:
        """Add documents, embedding only those not already cached on disk.

        If the embedder needs fitting (TF-IDF), it is fit on the full batch of
        *new* texts before embedding.
        """
        pending = [d for d in docs if d.id not in self._ids]
        to_embed = [d for d in pending if d.id not in self._cache]
        if to_embed:
            fit_if_needed(self.embedder, [d.text for d in to_embed])
            new_vecs = self.embedder.embed_batch([d.text for d in to_embed])
            for d, v in zip(to_embed, new_vecs):
                self._cache[d.id] = v
        for d in pending:
            self._ids.add(d.id)
            self._docs.append(d)
            self._vecs.append(self._cache[d.id])

    def save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        blob = {
            "signature": embedder_signature(self.embedder),
            "vectors": {k: array("f", v) for k, v in self._cache.items()},
        }
        self.cache_path.write_bytes(pickle.dumps(blob, protocol=pickle.HIGHEST_PROTOCOL))

    @property
    def embedded_count(self) -> int:
        return len(self._cache)

    def search(self, query: str, *, k: int = 5) -> list[tuple[Document, float]]:
        if not self._docs:
            return []
        qv = self.embedder.embed(query)
        scored = [(d, cosine(qv, v)) for d, v in zip(self._docs, self._vecs)]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]

    def __len__(self) -> int:
        return len(self._docs)


def build_persistent_index(
    docs: list[Document],
    embedder: EmbeddingProvider,
    cache_path: str | Path,
    *,
    save: bool = True,
) -> PersistentVectorStore:
    store = PersistentVectorStore(embedder, cache_path)
    store.add(docs)
    if save:
        store.save()
    return store
