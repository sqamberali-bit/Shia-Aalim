"""Grounded retrieval with confidence-aware ranking and multi-source support.

The retriever wraps a :class:`~shia_aalim.retrieval.vectorstore.VectorStore` and
adds the parts the charter cares about:

* **Confidence-aware ranking** — a passage's final score blends semantic
  similarity with the *confidence* of its source, so a well-attested passage
  outranks a marginally-more-similar unverified one.
* **Evidence-type filtering** — retrieve only Quran, only Hadith, etc.
* **Multi-source consensus** — :meth:`consensus` groups results by how many
  distinct sources support a point, feeding the hallucination-prevention layer.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from ..models import ConfidenceLevel, Document, EvidenceType
from .vectorstore import VectorStore

# How much a source's confidence nudges its ranking (0 = pure similarity).
_CONFIDENCE_BONUS = {
    ConfidenceLevel.HIGH: 0.15,
    ConfidenceLevel.MEDIUM: 0.07,
    ConfidenceLevel.LOW: 0.0,
    ConfidenceLevel.UNVERIFIED: -0.10,
}


@dataclass
class RetrievalResult:
    document: Document
    similarity: float
    score: float  # similarity + confidence adjustment

    @property
    def citation_ref(self) -> str:
        return self.document.citation.reference_string()


class Retriever:
    def __init__(self, store: VectorStore) -> None:
        self.store = store

    def retrieve(
        self,
        query: str,
        *,
        k: int = 5,
        evidence_types: Optional[list[EvidenceType]] = None,
        min_confidence: ConfidenceLevel = ConfidenceLevel.UNVERIFIED,
        oversample: int = 4,
    ) -> list[RetrievalResult]:
        """Return the top-``k`` results after filtering and confidence re-ranking.

        ``oversample`` widens the initial vector search before filtering so that
        type/confidence filters do not starve the final list.
        """
        raw = self.store.search(query, k=max(k * oversample, k))
        results: list[RetrievalResult] = []
        for doc, sim in raw:
            if evidence_types and doc.evidence_type not in evidence_types:
                continue
            if doc.confidence.rank < min_confidence.rank:
                continue
            adjusted = sim + _CONFIDENCE_BONUS.get(doc.confidence, 0.0)
            results.append(RetrievalResult(document=doc, similarity=sim, score=adjusted))
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:k]

    def consensus(
        self, query: str, *, k: int = 8, min_similarity: float = 0.15
    ) -> dict[str, list[RetrievalResult]]:
        """Group retrieved passages by source id to gauge multi-source support.

        A point corroborated by several *distinct* sources is more trustworthy
        than one resting on a single passage. Returns ``{source_id: [results]}``
        for results clearing ``min_similarity``.
        """
        grouped: dict[str, list[RetrievalResult]] = defaultdict(list)
        for res in self.retrieve(query, k=k):
            if res.similarity < min_similarity:
                continue
            grouped[res.document.citation.source_id].append(res)
        return dict(grouped)
