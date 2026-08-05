"""Persistent vector store — embed once, reuse across runs.

Re-embedding a large corpus (~230k documents) on every process start is
wasteful, and with a semantic model it is the dominant cost.
:class:`PersistentVectorStore` caches each document's vector on disk keyed by
the document id, so a second run over the same corpus + embedder does **no**
embedding at all.

It implements the same ``add`` / ``search`` / ``__len__`` surface as
:class:`~shia_aalim.retrieval.vectorstore.InMemoryVectorStore`, so it drops into
:class:`~shia_aalim.retrieval.retriever.Retriever` unchanged. Search is a dense
scan — a single numpy matrix-vector product when numpy is available (see
``vectorstore``), pure-Python cosine otherwise.

Memory notes: vectors are held as compact ``array('f')`` (float32) both in the
cache dict and the search list — ~8x smaller than Python float lists — and new
documents are embedded in bounded batches so startup never materialises the
whole corpus's vectors as Python lists at once.

The on-disk cache stores only ``{id: vector}`` plus an embedder *signature*; if
the signature changes (different model/dim), the cache is ignored and rebuilt,
so stale vectors can never be silently mixed with a new embedder.
"""

from __future__ import annotations

import pickle
from array import array
from pathlib import Path

from ..models import Document
from .embeddings import EmbeddingProvider, fit_if_needed
from .vectorstore import dense_topk

_EMBED_BATCH = 1024  # bound the transient list-of-lists from embed_batch


def embedder_signature(embedder: EmbeddingProvider) -> str:
    """Identity of an embedder for cache invalidation (class + model + dim)."""
    model = getattr(embedder, "model_name", "")
    return f"{type(embedder).__name__}:{model}:{getattr(embedder, 'dim', '?')}"


class PersistentVectorStore:
    def __init__(self, embedder: EmbeddingProvider, cache_path: str | Path) -> None:
        self.embedder = embedder
        self.cache_path = Path(cache_path)
        self._docs: list[Document] = []
        self._vecs: list[array] = []
        self._ids: set[str] = set()
        self._matrix = None  # numpy cache, rebuilt after adds
        self._cache: dict[str, array] = self._load_cache()

    def _load_cache(self) -> dict[str, array]:
        if not self.cache_path.exists():
            return {}
        try:
            blob = pickle.loads(self.cache_path.read_bytes())
        except Exception:  # noqa: BLE001 - corrupt/old cache => rebuild
            return {}
        if blob.get("signature") != embedder_signature(self.embedder):
            return {}  # different embedder: ignore stale vectors
        out: dict[str, array] = {}
        for k, v in blob.get("vectors", {}).items():
            out[k] = v if isinstance(v, array) else array("f", v)
        return out

    def add(self, docs: list[Document]) -> None:
        """Add documents, embedding only those not already cached on disk.

        If the embedder needs fitting (TF-IDF), it is fit on the full batch of
        *new* texts before embedding. Embedding runs in bounded batches and
        each vector is stored compactly straight away.
        """
        pending = [d for d in docs if d.id not in self._ids]
        to_embed = [d for d in pending if d.id not in self._cache]
        if to_embed:
            fit_if_needed(self.embedder, [d.text for d in to_embed])
            for start in range(0, len(to_embed), _EMBED_BATCH):
                chunk = to_embed[start : start + _EMBED_BATCH]
                new_vecs = self.embedder.embed_batch([d.text for d in chunk])
                for d, v in zip(chunk, new_vecs):
                    self._cache[d.id] = array("f", v)
        for d in pending:
            self._ids.add(d.id)
            self._docs.append(d)
            self._vecs.append(self._cache[d.id])
        self._matrix = None

    def save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        blob = {
            "signature": embedder_signature(self.embedder),
            "vectors": dict(self._cache),
        }
        self.cache_path.write_bytes(pickle.dumps(blob, protocol=pickle.HIGHEST_PROTOCOL))

    @property
    def embedded_count(self) -> int:
        return len(self._cache)

    def search(self, query: str, *, k: int = 5) -> list[tuple[Document, float]]:
        qv = self.embedder.embed(query)
        results, self._matrix = dense_topk(self._vecs, self._docs, qv, k, self._matrix)
        return results

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
