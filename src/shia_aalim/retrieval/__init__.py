"""Retrieval: embeddings, vector storage and grounded retrieval.

The reference implementations here are pure-stdlib so the whole pipeline runs
with zero installs. Real providers (BGE/Jina/E5 embeddings; Qdrant/Chroma/
Weaviate stores) plug in behind the same small protocols — see
``docs/architecture.md``.
"""

from .embeddings import (
    EmbeddingProvider,
    HashingEmbedder,
    SentenceTransformerEmbedder,
    TfidfHashingEmbedder,
    cosine,
    fit_if_needed,
    make_embedder,
)
from .index import PersistentVectorStore, build_persistent_index, embedder_signature
from .retriever import RetrievalResult, Retriever
from .vectorstore import InMemoryVectorStore, VectorStore

__all__ = [
    "EmbeddingProvider",
    "HashingEmbedder",
    "TfidfHashingEmbedder",
    "SentenceTransformerEmbedder",
    "make_embedder",
    "fit_if_needed",
    "cosine",
    "VectorStore",
    "InMemoryVectorStore",
    "PersistentVectorStore",
    "build_persistent_index",
    "embedder_signature",
    "Retriever",
    "RetrievalResult",
]
