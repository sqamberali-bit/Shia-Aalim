"""Retrieval: embeddings, vector storage and grounded retrieval.

The reference implementations here are pure-stdlib so the whole pipeline runs
with zero installs. Real providers (BGE/Jina/E5 embeddings; Qdrant/Chroma/
Weaviate stores) plug in behind the same small protocols — see
``docs/architecture.md``.
"""

from .embeddings import EmbeddingProvider, HashingEmbedder, cosine
from .retriever import RetrievalResult, Retriever
from .vectorstore import InMemoryVectorStore, VectorStore

__all__ = [
    "EmbeddingProvider",
    "HashingEmbedder",
    "cosine",
    "VectorStore",
    "InMemoryVectorStore",
    "Retriever",
    "RetrievalResult",
]
